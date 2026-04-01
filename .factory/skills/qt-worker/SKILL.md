---
name: qt-worker
description: Use when implementing or testing Qt GUI changes under qt/aqt/, such as source capture, card review, deck selection, and other desktop flows.
---

# Qt Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features that touch the Qt GUI layer:

- Source-first capture surfaces (file/URL intake, drag/drop, LLM preview actions)
- Card review list with edit/delete
- Deck selection dialog
- Error message display
- Integration with Rust/Python backend

## Required Skills

None required for this worker type - uses Qt/Python tooling directly.

## Work Procedure

1. **Understand the existing codebase**
   - Review qt/aqt/ for existing UI patterns
   - Check how widgets are structured
   - Review how qt/aqt embeds web components
   - Look at how PyQt is used for dialogs

2. **Write tests first (TDD)**
   - Create pytest files in qt/tests/ for Qt components
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
   - Run `./ninja check:pytest:aqt` for repo-native Qt test execution
   - Verify object names are correct
   - Run `ninja check:svelte` if TypeScript/Svelte changes

5. **Manual verification**
   - All source inputs work (URL paste, file picker, drag/drop)
   - Edit dialog opens and saves changes
   - Delete confirmation appears
   - Error messages display correctly

## Example Handoff

```json
{
    "salientSummary": "Implemented the source-first QuickIntakeFrame in qt/aqt/addcards.py with file/URL capture, deck and note-type context chips, drag-drop, and preview-first LLM actions before writing notes.",
    "whatWasImplemented": "Updated qt/aqt/addcards.py to add QuickIntakeFrame with Choose files, Paste URL, Connect Codex, LLM setup, and Organize note actions. Added quickIntake* object names for styling/tests, drag-drop handling, and status labels that guide Summarize, Q&A, and Cloze previews before any note fields are written.",
    "whatWasLeftUndone": "",
    "verification": {
        "commandsRun": [
            {
                "command": "./ninja check:pytest:aqt",
                "exitCode": 0,
                "observation": "Qt pytest suite passes, including quick intake widget coverage for action visibility, drag-drop, and status-label updates"
            },
            {
                "command": "./tools/dmypy",
                "exitCode": 0,
                "observation": "Python type checking passes for the Qt-side changes after the quick intake updates"
            }
        ],
        "interactiveChecks": [
            {
                "action": "Open Add Cards, click Paste URL, and confirm the quick intake source preview updates",
                "observed": "Quick intake banner shows the pasted URL summary and prompts the next preview action"
            },
            {
                "action": "Click Choose files and select an audio or PDF source",
                "observed": "Selected source summary appears and the intake frame updates its status labels"
            },
            {
                "action": "Drag a file onto QuickIntakeFrame",
                "observed": "Drag styling activates and the dropped source is accepted into the preview flow"
            }
        ]
    },
    "tests": {
        "added": [
            {
                "file": "qt/tests/test_addcards.py",
                "cases": [
                    "test_quick_intake_actions_present",
                    "test_paste_url_updates_preview",
                    "test_choose_files_updates_status",
                    "test_drag_drop_source",
                    "test_llm_preview_actions_require_source"
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
