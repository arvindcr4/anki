# Architecture

## System Overview

LLM-powered flashcard generation integrated into Anki with local storage and AnkiConnect sync.

```
┌─────────────────────────────────────────────────────────────┐
│                         Qt UI (aqt)                          │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │Source Picker│  │ Card Review  │  │Deck Selection │   │
│  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘   │
└─────────┼───────────────────┼────────────────┼─────────────┘
          │                   │                │
          ▼                   ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                   Python Library (pylib)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │ContentRouter│  │LocalStorage │  │AnkiConnect   │   │
│  │(provider    │  │(SQLite)     │  │Client        │   │
│  │ selection)  │  │             │  │              │   │
│  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘   │
└─────────┼───────────────────┼────────────────┼─────────────┘
          │                   │                │
          ▼                   ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                      Rust Core (rslib)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │LLM Providers│  │Ingest Service│  │Flashcard      │   │
│  │(MiniMax,    │  │(URL/Audio/  │  │Models        │   │
│  │ Gemini)      │  │ Video/Text)  │  │              │   │
│  └──────────────┘  └──────────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## LLM Routing

| Content Type | Provider | API Used                                  |
| ------------ | -------- | ----------------------------------------- |
| Plain text   | MiniMax  | OpenAI-compatible /chat/completions       |
| URL          | Gemini   | urlContext tool                           |
| Audio file   | Gemini   | Files API → transcription                 |
| Video file   | Gemini   | Files API → extract audio → transcription |

## Data Flow

1. User selects source type (URL/File/Text)
2. Content ingested → extracted/transcribed
3. LLM generates flashcard JSON
4. Cards saved locally (pending sync status)
5. User reviews/edits/deletes cards
6. User selects target deck
7. Cards synced via AnkiConnect (or queued if unavailable)
8. Sync status updated to "synced"

## Key Design Decisions

- **Local-first**: Cards stored locally before sync
- **Offline-capable**: Failed syncs queued for retry
- **Minimal prompts**: ~1 card per 100 words
- **Both formats**: Basic Q&A and Cloze deletion supported
