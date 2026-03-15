# Autoresearch: Codex connection affordance in Anki Add Cards

## Objective
Add an obvious way to connect Codex in the Add Cards LLM workspace. The source-first flow is now visible, but provider setup is still generic. The user specifically wants Codex surfaced as a first-class connection path so the workspace feels built for the current LLM era instead of an abstract future integration.

## Metrics
- **Primary**: `codex_connect_score` (unitless, higher is better)
- **Secondary**: `syntax_ok`, `front_center_affordance`, `env_detection`, `codex_status_surface`

## How to Run
`./autoresearch.sh`

The script performs a fast Python syntax check and scores whether Add Cards exposes a Codex-specific connection flow:
- visible `Connect Codex` affordance in the banner
- visible `Codex connection` status surface
- explicit connection handler in Python
- environment detection for `OPENAI_API_KEY`
- Codex-specific guidance in the UI/doc copy

## Files in Scope
- `qt/aqt/addcards.py`
- `docs/llm-intake-ux.md`
- `autoresearch.md` / `autoresearch.sh` / `autoresearch.ideas.md`

## Off Limits
- Scheduling / FSRS logic
- Rust backend / storage layer
- Real provider/network integration
- New runtime dependencies

## Constraints
- Keep Codex setup inline and front-and-center.
- Reuse existing status surfaces rather than opening a large wizard.
- Preserve the classic manual editing path.
- Fast checks must pass after every kept experiment.

## What's Been Tried
- Added a source-first quick-intake banner.
- Added visible LLM workspace actions and a source preview loop.
- Added gating so LLM actions only activate after a source is captured.
- Current gap: provider setup is still generic. There is no explicit Codex connection button or Codex-specific readiness state.
