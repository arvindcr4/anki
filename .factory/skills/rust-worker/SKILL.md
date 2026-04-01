---
name: rust-worker
description: Rust backend implementation for LLM integration and flashcard models in rslib
---

# Rust Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features that touch the Rust core layer:

- LLM provider abstraction (MiniMax, Gemini)
- Flashcard data models
- Content ingestion services (URL, audio, video, text)
- Local SQLite storage for pending cards
- Prompt generation for flashcard creation

## Required Skills

None required for this worker type - uses Rust tooling directly.

## Work Procedure

1. **Understand the existing codebase**
   - Review relevant code in rslib/ for patterns
   - Check proto/ for existing protobuf definitions
   - Look at error/mod.rs for error handling patterns
   - Review how rslib exposes its API to Python

2. **Write tests first (TDD)**
   - Create test files in the appropriate tests/ module
   - Tests MUST fail before implementation (red phase)
   - Cover happy path + edge cases + error conditions

3. **Implement the feature**
   - Follow Anki's Rust conventions (see CLAUDE.md)
   - Use error/mod.rs's AnkiError/Result and snafu for errors
   - Use rslib/{process,io} for file and process operations
   - Keep implementation minimal to pass the tests

4. **Verify**
   - Run `cargo test --lib` for the module
   - Run `cargo check` to verify compilation
   - Review adjacent code for integration issues
   - Ensure no orphaned processes or test runners

5. **Manual verification**
   - Test with realistic inputs where applicable
   - Verify JSON output format matches spec
   - Check error messages are user-friendly

## Example Handoff

```json
{
    "salientSummary": "Implemented LLM provider abstraction with MiniMaxProvider (OpenAI-compatible) and GeminiProvider (with urlContext and Files API). Added config validation for API keys on startup. Text content routes to MiniMax, multimodal (URL/audio/video) routes to Gemini.",
    "whatWasImplemented": "Created LLM provider trait in rslib with generate_flashcards(content, format) method. MiniMaxProvider uses OpenAI-compatible /chat/completions endpoint. GeminiProvider uses /models/{model}:generateContent with urlContext and Files API. Provider selection logic in ContentRouter based on source_type.",
    "whatWasLeftUndone": "",
    "verification": {
        "commandsRun": [
            {
                "command": "cargo test --lib llm_provider",
                "exitCode": 0,
                "observation": "All 12 provider tests pass"
            },
            {
                "command": "cargo check",
                "exitCode": 0,
                "observation": "No compilation errors"
            }
        ],
        "interactiveChecks": []
    },
    "tests": {
        "added": [
            {
                "file": "rslib/src/llm/tests.rs",
                "cases": [
                    "test_minimax_provider_basic",
                    "test_gemini_provider_with_url",
                    "test_provider_selection_by_content_type",
                    "test_invalid_api_key_error"
                ]
            }
        ]
    },
    "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature requires changes to proto definitions (affects other layers)
- Integration with pylib/aqt is unclear
- API key validation needs user interaction
- Significant scope change needed
