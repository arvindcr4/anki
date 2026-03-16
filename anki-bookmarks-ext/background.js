import { AnkiConnect } from "./lib/anki-connect.js";
import { ContentExtractor } from "./lib/content-extractor.js";
import { FlashcardGenerator } from "./lib/flashcard-generator.js";

// State
let processing = false;
let progress = { current: 0, total: 0, status: "idle", cards: 0, errors: [] };

// Settings split: sync for preferences, local for secrets + large data
const SYNC_DEFAULTS = {
    provider: "claude",
    model: "",
    ankiUrl: "http://localhost:8765",
    deckName: "auto",
    modelName: "Basic",
    subjectPrompt: "",
    selectedFolders: [],
    defaultMode: "auto",
};

const LOCAL_DEFAULTS = {
    apiKey: "",
    processedUrls: [],
};

async function getSettings() {
    const [syncData, localData] = await Promise.all([
        chrome.storage.sync.get(SYNC_DEFAULTS),
        chrome.storage.local.get(LOCAL_DEFAULTS),
    ]);

    const merged = { ...SYNC_DEFAULTS, ...LOCAL_DEFAULTS, ...syncData, ...localData };

    // Fallback: check if apiKey was saved to sync storage (migration path)
    if (!merged.apiKey) {
        const syncFallback = await chrome.storage.sync.get({ apiKey: "" });
        if (syncFallback.apiKey) {
            merged.apiKey = syncFallback.apiKey;
            // Migrate to local storage
            await chrome.storage.local.set({ apiKey: syncFallback.apiKey });
            await chrome.storage.sync.remove("apiKey");
        }
    }

    return merged;
}

// Get bookmarks from selected folders (or all if none selected)
async function getBookmarks(selectedFolders) {
    const tree = await chrome.bookmarks.getTree();
    const bookmarks = [];

    function walk(nodes, parentTitle = "", parentSelected = false) {
        for (const node of nodes) {
            if (node.url) {
                if (
                    node.url.startsWith("http://")
                    || node.url.startsWith("https://")
                ) {
                    bookmarks.push({
                        id: node.id,
                        title: node.title || node.url,
                        url: node.url,
                        folder: parentTitle,
                        dateAdded: node.dateAdded,
                    });
                }
            }
            if (node.children) {
                const folderName = node.title || "Root";
                const isSelected = parentSelected
                    || selectedFolders.length === 0
                    || selectedFolders.includes(node.id);
                if (isSelected) {
                    walk(node.children, folderName, true);
                } else {
                    walk(node.children, folderName, false);
                }
            }
        }
    }

    walk(tree);
    return bookmarks;
}

// Resolve the deck name for a bookmark
// Priority: 1) subject prompt → deck name, 2) bookmark folder, 3) fallback "Bookmarks"
async function resolveDeckName(bookmark, settings, anki) {
    // If user set an explicit deck name (not "auto"), use it
    if (settings.deckName && settings.deckName !== "auto") {
        return settings.deckName;
    }

    // Try to derive from subject prompt
    if (settings.subjectPrompt) {
        const deckFromSubject = sanitizeDeckName(settings.subjectPrompt);
        // Check if a matching deck already exists
        const existing = await anki.findMatchingDeck(deckFromSubject);
        return existing || deckFromSubject;
    }

    // Derive from bookmark folder
    if (bookmark.folder && bookmark.folder !== "Root") {
        const deckFromFolder = sanitizeDeckName(bookmark.folder);
        const existing = await anki.findMatchingDeck(deckFromFolder);
        return existing || deckFromFolder;
    }

    return "Bookmarks";
}

// Clean a string into a valid Anki deck name
function sanitizeDeckName(str) {
    return str
        .replace(/[^\w\s-]/g, "") // remove special chars
        .replace(/\s+/g, " ") // normalize whitespace
        .trim()
        .substring(0, 60) // reasonable length
        || "Bookmarks";
}

// Process a single bookmark
async function processBookmark(bookmark, generator, anki, settings) {
    try {
        // Extract content (auto-detect or forced mode)
        let result;
        if (settings.defaultMode === "auto") {
            result = await ContentExtractor.extract(bookmark.url);
        } else {
            result = await ContentExtractor.extractAs(
                bookmark.url,
                settings.defaultMode,
            );
        }

        if (result.error || !result.content) {
            return {
                url: bookmark.url,
                mode: result.mode,
                error: result.error || "No content extracted",
                cards: 0,
            };
        }

        // Generate flashcards
        const cards = await generator.generate({
            title: result.title,
            text: result.content,
            url: bookmark.url,
        });

        if (cards.length === 0) {
            return { url: bookmark.url, mode: result.mode, error: null, cards: 0 };
        }

        // Resolve deck name (auto or explicit)
        const deckName = await resolveDeckName(bookmark, settings, anki);

        // Sync to Anki
        const syncResult = await anki.addNotes(
            deckName,
            cards,
            settings.modelName,
        );
        return {
            url: bookmark.url,
            mode: result.mode,
            deck: deckName,
            error: null,
            cards: syncResult.added,
        };
    } catch (e) {
        return { url: bookmark.url, mode: "unknown", error: e.message, cards: 0 };
    }
}

// Main processing pipeline
async function processBookmarks(onlyNew = true) {
    if (processing) { return progress; }
    processing = true;
    progress = {
        current: 0,
        total: 0,
        status: "starting",
        cards: 0,
        errors: [],
    };
    broadcastProgress();

    try {
        const settings = await getSettings();

        if (!settings.apiKey) {
            throw new Error(
                "No LLM API key configured. Open extension settings to set up.",
            );
        }

        // Init Anki client
        const anki = new AnkiConnect({
            url: settings.ankiUrl,
        });
        const ping = await anki.ping();
        if (!ping.ok) {
            throw new Error(
                `Cannot connect to Anki server at ${settings.ankiUrl}. Is it running?`,
            );
        }

        // Init flashcard generator
        const generator = new FlashcardGenerator({
            provider: settings.provider,
            apiKey: settings.apiKey,
            model: settings.model,
            subjectPrompt: settings.subjectPrompt,
        });

        // Get bookmarks
        progress.status = "Reading bookmarks...";
        broadcastProgress();
        const bookmarks = await getBookmarks(settings.selectedFolders);

        // Filter already-processed if onlyNew
        const processedSet = new Set(settings.processedUrls || []);
        const toProcess = onlyNew
            ? bookmarks.filter((b) => !processedSet.has(b.url))
            : bookmarks;

        progress.total = toProcess.length;
        broadcastProgress();

        if (toProcess.length === 0) {
            progress.status = "done";
            broadcastProgress();
            processing = false;
            return progress;
        }

        // Process sequentially (respect API rate limits)
        const newProcessed = [...(settings.processedUrls || [])];
        for (const bookmark of toProcess) {
            progress.current++;
            const shortTitle = bookmark.title.substring(0, 50);
            progress.status = `[${progress.current}/${progress.total}] ${shortTitle}`;
            broadcastProgress();

            const result = await processBookmark(
                bookmark,
                generator,
                anki,
                settings,
            );
            progress.cards += result.cards;

            if (result.error) {
                progress.errors.push({
                    url: bookmark.url,
                    mode: result.mode,
                    error: result.error,
                });
            }

            newProcessed.push(bookmark.url);

            // Save progress every 5 bookmarks (to local storage — no quota issues)
            if (progress.current % 5 === 0) {
                await chrome.storage.local.set({ processedUrls: newProcessed });
            }

            // Rate limit delay
            await new Promise((r) => setTimeout(r, 1500));
        }

        await chrome.storage.local.set({ processedUrls: newProcessed });
        progress.status = "done";
        broadcastProgress();
    } catch (e) {
        progress.status = `error: ${e.message}`;
        broadcastProgress();
    } finally {
        processing = false;
    }

    return progress;
}

function broadcastProgress() {
    chrome.runtime
        .sendMessage({ type: "progress", data: progress })
        .catch(() => {});
}

// Get bookmark folder tree for UI
async function getBookmarkFolders() {
    const tree = await chrome.bookmarks.getTree();
    const folders = [];

    function walk(nodes, depth = 0) {
        for (const node of nodes) {
            if (node.children) {
                folders.push({
                    id: node.id,
                    title: node.title || "Root",
                    depth,
                    count: node.children.filter((c) => c.url).length,
                });
                walk(node.children, depth + 1);
            }
        }
    }

    walk(tree);
    return folders;
}

// Message handler
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    switch (msg.type) {
        case "start":
            processBookmarks(msg.onlyNew !== false).then(sendResponse);
            return true;

        case "startAll":
            processBookmarks(false).then(sendResponse);
            return true;

        case "getProgress":
            sendResponse(progress);
            return false;

        case "getFolders":
            getBookmarkFolders().then(sendResponse);
            return true;

        case "saveSubject":
            chrome.storage.sync.set({ subjectPrompt: msg.value }).then(() => {
                sendResponse({ ok: true });
            });
            return true;

        case "saveSecrets":
            chrome.storage.local.set({
                apiKey: msg.apiKey,
            }).then(() => {
                sendResponse({ ok: true });
            });
            return true;

        case "getSecrets":
            chrome.storage.local.get(LOCAL_DEFAULTS).then(sendResponse);
            return true;

        case "resetProcessed":
            chrome.storage.local.set({ processedUrls: [] }).then(() => {
                sendResponse({ ok: true });
            });
            return true;

        case "getDecks":
            getSettings().then((s) => {
                const anki = new AnkiConnect({
                    url: s.ankiUrl,
                });
                anki.getDecks().then((decks) => sendResponse({ decks }))
                    .catch((e) => sendResponse({ decks: [], error: e.message }));
            });
            return true;

        case "testAnki":
            getSettings().then((s) => {
                const anki = new AnkiConnect({ url: s.ankiUrl });
                anki.ping().then(sendResponse);
            });
            return true;
    }
});
