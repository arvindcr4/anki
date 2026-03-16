// Options page controller

const $ = (sel) => document.querySelector(sel);

// Sync fields (non-sensitive preferences)
const SYNC_FIELDS = {
    provider: { el: "#provider", default: "claude" },
    model: { el: "#model", default: "" },
    ankiUrl: { el: "#anki-url", default: "http://localhost:8765" },
    deckName: { el: "#deck-name", default: "auto" },
    modelName: { el: "#model-name", default: "Basic" },
    defaultMode: { el: "#default-mode", default: "auto" },
    subjectPrompt: { el: "#subject-prompt", default: "" },
};

// Local fields (secrets — never synced via Google)
const LOCAL_FIELDS = {
    apiKey: { el: "#api-key", default: "" },
};

// Load settings
async function loadSettings() {
    const syncDefaults = {};
    for (const [key, f] of Object.entries(SYNC_FIELDS)) {
        syncDefaults[key] = f.default;
    }
    syncDefaults.selectedFolders = [];

    const localDefaults = {};
    for (const [key, f] of Object.entries(LOCAL_FIELDS)) {
        localDefaults[key] = f.default;
    }

    const [syncData, localData] = await Promise.all([
        chrome.storage.sync.get(syncDefaults),
        chrome.storage.local.get(localDefaults),
    ]);

    for (const [key, f] of Object.entries(SYNC_FIELDS)) {
        const el = $(f.el);
        if (el) { el.value = syncData[key] !== undefined ? syncData[key] : f.default; }
    }

    for (const [key, f] of Object.entries(LOCAL_FIELDS)) {
        const el = $(f.el);
        if (el) { el.value = localData[key] !== undefined ? localData[key] : f.default; }
    }

    loadFolders(syncData.selectedFolders || []);
}

// Save settings
async function saveSettings() {
    const syncSettings = {};
    for (const [key, f] of Object.entries(SYNC_FIELDS)) {
        const el = $(f.el);
        if (el) { syncSettings[key] = el.value; }
    }

    // Gather selected folders
    const checked = document.querySelectorAll(".folder-checkbox:checked");
    syncSettings.selectedFolders = Array.from(checked).map((cb) => cb.value);

    const localSettings = {};
    for (const [key, f] of Object.entries(LOCAL_FIELDS)) {
        const el = $(f.el);
        if (el) { localSettings[key] = el.value; }
    }

    try {
        await chrome.storage.sync.set(syncSettings);
        await chrome.storage.local.set(localSettings);

        // Verify the API key was actually persisted
        const verify = await chrome.storage.local.get({ apiKey: "" });
        const keyLen = verify.apiKey ? verify.apiKey.length : 0;

        if (localSettings.apiKey && keyLen === 0) {
            $("#save-status").textContent = "Error: API key failed to save!";
            $("#save-status").style.color = "#dc2626";
        } else {
            $("#save-status").textContent = keyLen > 0
                ? `Saved! (API key: ${keyLen} chars)`
                : "Saved!";
            $("#save-status").style.color = "#16a34a";
        }
    } catch (e) {
        $("#save-status").textContent = `Save failed: ${e.message}`;
        $("#save-status").style.color = "#dc2626";
    }

    setTimeout(() => {
        $("#save-status").textContent = "";
    }, 3000);
}

// Load bookmark folders into checklist
async function loadFolders(selectedFolders) {
    const folderList = $("#folder-list");
    folderList.textContent = "Loading...";

    chrome.runtime.sendMessage({ type: "getFolders" }, (folders) => {
        if (!folders || folders.length === 0) {
            folderList.textContent = "No bookmark folders found";
            return;
        }

        const selectedSet = new Set(selectedFolders);
        folderList.textContent = "";

        for (const f of folders) {
            const label = document.createElement("label");
            label.className = "folder-item";
            label.style.paddingLeft = f.depth * 16 + "px";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "folder-checkbox";
            checkbox.value = f.id;
            checkbox.checked = selectedSet.has(f.id);

            const name = document.createElement("span");
            name.textContent = f.title;

            const count = document.createElement("span");
            count.className = "count";
            count.textContent = `(${f.count} bookmarks)`;

            label.appendChild(checkbox);
            label.appendChild(name);
            label.appendChild(count);
            folderList.appendChild(label);
        }
    });
}

// Test Anki connection
$("#test-anki").addEventListener("click", () => {
    const resultEl = $("#anki-test-result");
    resultEl.textContent = "Testing...";
    resultEl.className = "test-result";

    chrome.runtime.sendMessage({ type: "testAnki" }, (result) => {
        if (result && result.ok) {
            resultEl.textContent = `Connected (v${result.version})`;
            resultEl.className = "test-result ok";
        } else {
            resultEl.textContent = `Failed: ${result?.error || "unknown error"}`;
            resultEl.className = "test-result fail";
        }
    });
});

// Reset processed URLs
$("#reset-processed").addEventListener("click", () => {
    if (confirm("This will re-process all bookmarks on the next run. Continue?")) {
        chrome.runtime.sendMessage({ type: "resetProcessed" }, () => {
            alert("Processed URL list has been cleared.");
        });
    }
});

// Save button
$("#save").addEventListener("click", saveSettings);

// Load existing Anki decks into the datalist
function loadDeckSuggestions() {
    chrome.runtime.sendMessage({ type: "getDecks" }, (result) => {
        const datalist = document.getElementById("deck-suggestions");
        if (!datalist) { return; }
        datalist.textContent = "";

        // Always offer "auto" as first option
        const autoOpt = document.createElement("option");
        autoOpt.value = "auto";
        autoOpt.textContent = "auto (derive from subject/folder)";
        datalist.appendChild(autoOpt);

        if (result && result.decks) {
            for (const deck of result.decks) {
                const opt = document.createElement("option");
                opt.value = deck;
                datalist.appendChild(opt);
            }
        }
    });
}

// Refresh decks button
$("#refresh-decks").addEventListener("click", loadDeckSuggestions);

// Init
loadSettings();
loadDeckSuggestions();
