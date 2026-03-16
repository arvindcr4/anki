# Anki Bookmark Flashcards — Chrome Extension

Auto-extract flashcards from your Chrome bookmarks and sync them to Anki.

## Features

- **Two extraction modes:**
  - **HTML → Markdown** — fetches bookmarked web pages, converts to clean markdown, generates flashcards
  - **PDF → Text** — fetches bookmarked PDFs, extracts text content, generates flashcards
  - **Auto-detect** — automatically chooses the right mode based on URL and Content-Type

- **Configurable subject focus** — set a prompt that guides flashcard generation to your area of study
- **Custom Anki server** — works with AnkiConnect or any custom Anki-compatible server
- **Bookmark folder filtering** — select which bookmark folders to process
- **Duplicate detection** — skips already-processed bookmarks and duplicate cards
- **LLM-powered** — uses Claude or OpenAI to generate high-quality Q&A flashcards

## Setup

### 1. Install the extension

1. Open `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select the `anki-bookmarks-ext` directory

### 2. Configure settings

Click the extension icon → ⚙️ Settings:

- **LLM Provider**: Choose Claude or OpenAI and enter your API key
- **Anki Server**: Set your server URL (default: `http://localhost:8765` for AnkiConnect)
  - For custom servers, select "Custom server" and optionally provide a Bearer token
- **Subject Focus**: Enter a prompt to guide flashcard generation
  - Example: _"Focus on machine learning fundamentals, key algorithms, and mathematical foundations"_
- **Bookmark Folders**: Select which folders to process (or leave all unchecked for everything)

### 3. Anki setup

If using AnkiConnect:

1. Install the [AnkiConnect add-on](https://ankiweb.net/shared/info/2055492159) in Anki
2. Restart Anki
3. The extension will connect to `http://localhost:8765`

If using a custom server:

1. Set the server URL in settings
2. The server must implement `version`, `deckNames`, `createDeck`, and `addNotes` actions

### 4. Generate flashcards

1. Bookmark pages you want to study
2. Click the extension icon
3. Optionally adjust the subject focus
4. Click **"Process New Bookmarks"** to process only unprocessed bookmarks
5. Or click **"Reprocess All"** to regenerate from all bookmarks

## Architecture

```
popup.html/js/css     — Main UI (trigger processing, see progress)
options.html/js/css   — Settings page
background.js         — Service worker (orchestrates the pipeline)
lib/
  anki-connect.js     — Anki server API client
  content-extractor.js — Unified content extraction (auto-detects HTML vs PDF)
  html-to-markdown.js — Regex-based HTML → Markdown converter
  pdf-extractor.js    — Lightweight PDF text extraction (no external deps)
  flashcard-generator.js — LLM-powered flashcard generation
```

## Pipeline

```
Bookmarks → Fetch URL → [HTML→Markdown | PDF→Text] → LLM generates cards → Anki sync
```

## Icons

Replace the placeholder icon references in `icons/` with actual PNG icons:

- `icon16.png` (16×16)
- `icon48.png` (48×48)
- `icon128.png` (128×128)

You can generate these from any icon or use the Anki logo.

## Permissions

- `bookmarks` — read Chrome bookmarks
- `storage` — save settings and processed URL list
- `activeTab` — access current tab (for future features)
- `offscreen` — PDF processing in background
- `<all_urls>` — fetch bookmarked page content
