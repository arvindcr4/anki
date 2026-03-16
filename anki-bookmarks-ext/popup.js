// Popup controller

const $ = (sel) => document.querySelector(sel);

const statusBar = $("#status-bar");
const statusText = $("#status-text");
const subjectInput = $("#subject");
const btnNew = $("#btn-new");
const btnAll = $("#btn-all");
const progressSection = $("#progress-section");
const progressFill = $("#progress-fill");
const progressDetail = $("#progress-detail");
const resultsSection = $("#results");
const cardsCount = $("#cards-count");
const errorList = $("#error-list");
const ankiStatus = $("#anki-status");

// Load saved subject prompt
chrome.storage.sync.get({ subjectPrompt: "", defaultMode: "auto" }, (data) => {
    subjectInput.value = data.subjectPrompt;
});

// Save subject prompt on change (debounced)
let saveTimer;
subjectInput.addEventListener("input", () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
        chrome.runtime.sendMessage({
            type: "saveSubject",
            value: subjectInput.value,
        });
    }, 500);
});

// Check Anki connection
chrome.runtime.sendMessage({ type: "testAnki" }, (result) => {
    if (result && result.ok) {
        ankiStatus.textContent = "Anki connected";
        ankiStatus.className = "anki-badge connected";
    } else {
        ankiStatus.textContent = "Anki offline";
        ankiStatus.className = "anki-badge disconnected";
    }
});

// Process new bookmarks
btnNew.addEventListener("click", () => {
    setButtons(false);
    chrome.runtime.sendMessage({ type: "start", onlyNew: true });
});

// Reprocess all bookmarks
btnAll.addEventListener("click", () => {
    setButtons(false);
    chrome.runtime.sendMessage({ type: "startAll" });
});

// Settings link
$("#open-options").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
});

// Listen for progress updates
chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "progress") {
        updateProgress(msg.data);
    }
});

// Poll progress on open (in case already running)
chrome.runtime.sendMessage({ type: "getProgress" }, (data) => {
    if (data) { updateProgress(data); }
});

function updateProgress(data) {
    switch (true) {
        case data.status === "idle":
            statusBar.className = "status idle";
            statusText.textContent = "Ready — select bookmarks to process";
            progressSection.classList.add("hidden");
            resultsSection.classList.add("hidden");
            setButtons(true);
            break;

        case data.status === "done":
            statusBar.className = "status done";
            statusText.textContent = `Done! ${data.cards} cards created`;
            progressSection.classList.add("hidden");
            resultsSection.classList.remove("hidden");
            cardsCount.textContent = data.cards;
            showErrors(data.errors);
            setButtons(true);
            break;

        case data.status.startsWith("error:"):
            statusBar.className = "status error";
            statusText.textContent = data.status;
            progressSection.classList.add("hidden");
            setButtons(true);
            break;

        default:
            statusBar.className = "status running";
            statusText.textContent = data.status;
            progressSection.classList.remove("hidden");
            const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
            progressFill.style.width = pct + "%";
            progressDetail.textContent = `${data.current}/${data.total} bookmarks · ${data.cards} cards`;
            setButtons(false);
            break;
    }
}

function showErrors(errors) {
    if (!errors || errors.length === 0) {
        errorList.classList.add("hidden");
        return;
    }
    errorList.classList.remove("hidden");
    errorList.textContent = "";
    const toShow = errors.slice(0, 10);
    for (const e of toShow) {
        const shortUrl = e.url.length > 50 ? e.url.substring(0, 50) + "..." : e.url;
        const item = document.createElement("div");
        item.className = "error-item";
        item.textContent = `${e.mode || "?"}: ${shortUrl} — ${e.error}`;
        errorList.appendChild(item);
    }
    if (errors.length > 10) {
        const more = document.createElement("div");
        more.className = "error-item";
        more.textContent = `...and ${errors.length - 10} more`;
        errorList.appendChild(more);
    }
}

function setButtons(enabled) {
    btnNew.disabled = !enabled;
    btnAll.disabled = !enabled;
}
