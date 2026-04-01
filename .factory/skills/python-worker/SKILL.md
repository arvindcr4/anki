---
name: python-worker
description: Python implementation for AnkiConnect sync and offline queue in pylib
---

# Python Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features that touch the Python layer:

- AnkiConnect HTTP client
- Offline queue for failed syncs
- Python wrapper around Rust services
- Configuration management

## Required Skills

None required for this worker type - uses Python tooling directly.

## Work Procedure

1. **Understand the existing codebase**
   - Review pylib/rsbridge for how Rust API is exposed
   - Check pylib/anki/ for existing patterns
   - Review how Python calls into Rust via protobuf
   - Look at existing error handling in pylib

2. **Write tests first (TDD)**
   - Create pytest files in pylib/tests/ or appropriate location
   - Tests MUST fail before implementation (red phase)
   - Mock AnkiConnect responses for unit tests
   - Cover connection refused, rate limits, API errors

3. **Implement the feature**
   - Use requests library for HTTP calls
   - Follow Python conventions in pylib (snake_case methods)
   - Handle connection errors gracefully
   - Log appropriately for debugging

4. **Verify**
   - Run `python -m pytest` for the module
   - Run `./tools/dmypy` for type checking
   - Test with actual AnkiConnect if available

5. **Manual verification**
   - Start Anki with AnkiConnect addon
   - Verify card appears in selected deck
   - Test offline queue with Anki closed

## Example Handoff

```json
{
    "salientSummary": "Implemented AnkiConnect HTTP client with deck discovery, note creation, and error handling. Added offline queue that persists failed syncs to SQLite and auto-retries when connection restored.",
    "whatWasImplemented": "Created AnkiConnectClient in pylib/anki/ankiconnect.py. Methods: discover() pings localhost:8765, get_decks() fetches deckNames, add_note(front, back, deck) creates note. OfflineQueue in pylib/anki/offline_queue.py persists to SQLite, auto-retries every 60s when AnkiConnect available.",
    "whatWasLeftUndone": "",
    "verification": {
        "commandsRun": [
            {
                "command": "python -m pytest pylib/tests/test_ankiconnect.py -v",
                "exitCode": 0,
                "observation": "All 8 AnkiConnect tests pass including mock_connection_refused"
            },
            {
                "command": "python -m pytest pylib/tests/test_offline_queue.py -v",
                "exitCode": 0,
                "observation": "All 5 queue tests pass including test_fifo_order"
            }
        ],
        "interactiveChecks": [
            {
                "action": "Start Anki with addon, generate card, verify appears in selected deck",
                "observed": "Card created with correct front/back in 'LLM Cards' deck"
            }
        ]
    },
    "tests": {
        "added": [
            {
                "file": "pylib/tests/test_ankiconnect.py",
                "cases": [
                    "test_discover_success",
                    "test_discover_connection_refused",
                    "test_get_decks_empty",
                    "test_add_note_basic",
                    "test_rate_limit_429"
                ]
            },
            {
                "file": "pylib/tests/test_offline_queue.py",
                "cases": [
                    "test_queue_persists_across_restart",
                    "test_fifo_order",
                    "test_auto_retry_on_connection"
                ]
            }
        ]
    },
    "discoveredIssues": []
}
```

## When to Return to Orchestrator

- AnkiConnect addon behavior differs from documentation
- Need changes to Rust layer API
- Configuration format needs user decision
- Significant scope change needed
