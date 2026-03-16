# Local Anki Server

Standalone AnkiConnect-compatible server backed by SQLite. Zero external dependencies — just Python 3.8+.

## Quick Start

```bash
python anki_server.py
```

Server runs at `http://127.0.0.1:8765` — the same URL as AnkiConnect, so the Chrome extension works out of the box.

## Options

```bash
python anki_server.py --port 9000        # custom port
python anki_server.py --db ~/cards.db    # custom database location
python anki_server.py --export deck.apkg # export to .apkg and exit
```

## API

Implements the AnkiConnect protocol (version 6). Supported actions:

| Action            | Description                                   |
| ----------------- | --------------------------------------------- |
| `version`         | Returns `6`                                   |
| `deckNames`       | List all deck names                           |
| `deckNamesAndIds` | Deck names → IDs mapping                      |
| `createDeck`      | Create a new deck                             |
| `deleteDecks`     | Delete decks and their cards                  |
| `modelNames`      | List note model names                         |
| `addNote`         | Add a single note                             |
| `addNotes`        | Add multiple notes (with duplicate detection) |
| `findNotes`       | Search notes by deck, tag, or field text      |
| `notesInfo`       | Get full note details                         |
| `multi`           | Batch multiple actions                        |
| `sync`            | No-op (for compatibility)                     |

### HTTP Endpoints

| Method | Path                | Description                       |
| ------ | ------------------- | --------------------------------- |
| POST   | `/`                 | AnkiConnect API                   |
| GET    | `/health`           | Server stats (deck/note counts)   |
| GET    | `/export`           | Download all cards as `.apkg`     |
| GET    | `/export?deck=Name` | Download specific deck as `.apkg` |

### Example

```bash
# Test connection
curl -s localhost:8765 -X POST \
  -d '{"action": "version", "version": 6}' | python -m json.tool

# List decks
curl -s localhost:8765 -X POST \
  -d '{"action": "deckNames", "version": 6}' | python -m json.tool

# Export to .apkg
curl -o cards.apkg http://localhost:8765/export
```

## Storage

Cards are stored in a local SQLite database (`anki_cards.db` by default). The database supports:

- **Duplicate detection**: per-deck checksums prevent duplicate cards
- **WAL mode**: safe for concurrent reads
- **Thread-safe**: all DB access is mutex-locked

## Exporting to Anki

1. Run `python anki_server.py --export cards.apkg`
2. Open Anki desktop → File → Import → select `cards.apkg`

Or use the HTTP endpoint: `curl -o cards.apkg http://localhost:8765/export`
