---
name: qt-worker
description: Qt GUI implementation for source picker, card review, and deck selection in aqt
---

# Qt Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features that touch the Qt GUI layer:

- Source picker (URL, File, Text input)
- Card review list with edit/delete
- Deck selection dialog
- Error message display
- Integration with Rust/Python backend

## Required Skills

None required for this worker type - uses Qt/Python tooling directly.

## Work Procedure

1. **Understand the existing codebase**
   - Review aqt/ for existing UI patterns
   - Check how widgets are structured
   - Review how aqt embeds web components
   - Look at how PyQt is used for dialogs

2. **Write tests first (TDD)**
   - Create pytest files for Qt components
   - Use pytest-qt for widget testing
   - Tests MUST fail before implementation (red phase)
   - Cover enabled/disabled states, input validation

3. **Implement the feature**
   - Follow Qt conventions (object names, signals/slots)
   - Use appropriate Qt widgets (QLineEdit, QPushButton, QVBoxLayout, etc.)
   - Set object names for testing (setObjectName())
   - Handle user input validation
   - Follow Anki's styling if applicable

4. **Verify**
   - Run `python -m pytest` for the module
   - Verify object names are correct
   - Run `ninja check:svelte` if TypeScript/Svelte changes

5. **Manual verification**
   - All input types work (URL paste, file picker, text area)
   - Edit dialog opens and saves changes
   - Delete confirmation appears
   - Error messages display correctly

## Example Handoff

```json
{
    "salientSummary": "Implemented QuickIntakeFrame with URL, File, and Text input tabs. URL tab has QLineEdit with clipboard paste support. File tab uses QFileDialog for audio/video selection. Text tab has QTextEdit for direct input. All inputs trigger content ingestion via backend.",
    "whatWasImplemented": "Created QuickIntakeFrame in aqt/quickintake.py. Three tabs via QTabWidget: UrlTab (QLineEdit with paste button), FileTab (QPushButton + QFileDialog filtering audio/video), TextTab (QTextEdit). Each tab has 'Generate' button that calls pylib.ankiconnect. ContentRouter. Added drag-drop support on FileTab.",
    "whatWasLeftUndone": "",
    "verification": {
        "commandsRun": [
            {
                "command": "python -m pytest aqt/tests/test_quickintake.py -v",
                "exitCode": 0,
                "observation": "All 15 UI tests pass"
            },
            {
                "command": "python -m pytest aqt/tests/test_card_review.py -v",
                "exitCode": 0,
                "observation": "All 9 card review tests pass"
            }
        ],
        "interactiveChecks": [
            {
                "action": "Open QuickIntakeFrame, paste URL, click Generate",
                "observed": "URL tab active, content shows in card preview"
            },
            {
                "action": "Click File tab, click Choose File, select audio",
                "observed": "File path displayed, audio format validated"
            },
            {
                "action": "Drag audio file onto File tab",
                "observed": "File path auto-populated"
            }
        ]
    },
    "tests": {
        "added": [
            {
                "file": "aqt/tests/test_quickintake.py",
                "cases": [
                    "test_url_input_basic",
                    "test_url_input_clipboard",
                    "test_file_input_dialog",
                    "test_file_input_validation",
                    "test_text_input_basic",
                    "test_drag_drop_file"
                ]
            },
            {
                "file": "aqt/tests/test_card_review.py",
                "cases": [
                    "test_list_populates",
                    "test_edit_dialog_opens",
                    "test_delete_confirms"
                ]
            }
        ]
    },
    "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Need changes to backend API
- UI design needs clarification
- Styling conventions unclear
- Significant scope change needed
