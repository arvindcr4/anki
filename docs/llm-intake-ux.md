# LLM-era Add Cards UX

## Friction in the current flow

The current Add Cards window is powerful but discoverability is low for first-run capture. Existing editor drag/drop and URL handling live behind implicit behavior: users must already know to drop onto a field, know which field is active, and know how deck, note type, and tags should be chosen before they start. In an LLM-era workflow, that is backwards. Users now expect to start from source material first — a PDF, article URL, video URL, screenshot, transcript, or document — and let the system help them shape that material into learnable cards.

There are four main friction points in the current flow:

1. **Hidden intake**: drag/drop exists, but it is invisible unless the user guesses correctly.
2. **Tooling split**: source capture, organization, and future LLM setup live in different mental buckets instead of one capture surface.
3. **Weak organizational defaults**: deck, note type, and tags are present, but there is little guidance on how to keep imports tidy.
4. **No explicit LLM foothold**: there is nowhere obvious to attach provider selection, API keys, prompt presets, or source-to-card transformations.

## Design principles

1. **Source-first, not field-first**: the first visual affordance should invite the user to drop or paste what they want to learn from.
2. **One capture surface**: files, URLs, LLM setup, and organization should be reachable from the same visible strip.
3. **Keep the expert path intact**: advanced users should still be able to ignore the new surface and continue typing directly into fields.
4. **Progressive disclosure**: the UI should surface what matters now, while reserving room for richer LLM actions later.
5. **Organization by default**: every captured source should leave behind enough metadata to be triaged later.
6. **Low-latency trust**: actions should feel immediate; slow LLM steps should be optional, explicit, and previewable.

## Proposed interaction model

### 1. Quick intake strip

A dedicated intake strip should sit above the field editor and communicate the core promise in one glance:

- Drop files or paste a URL
- Keep LLM setup visible
- Organize the note while capturing

This strip should accept drag/drop directly and provide explicit buttons for file picking and URL pasting.

### 2. Always-visible context

The strip should echo the current deck and note type so that learners understand where their new cards will land before they press Add.

### 3. Source-aware tagging

Each capture should add lightweight hierarchical tags automatically, such as:

- `capture::inbox`
- `source::file::<stem>`
- `source::web::<host>`
- optional deck and note type tags when the learner wants to lock organization down

These tags are not a replacement for better collection structure, but they provide a low-friction safety net for later cleanup and batching.

### 4. LLM actions as the next layer

The visible LLM entry point should later expand into a right-side sheet or inline popover with:

- provider/model selection
- API key / environment validation
- prompt presets (`summarize`, `extract facts`, `turn into cloze`, `generate Q/A`)
- preview before writing to note fields
- per-source cost/latency estimate

## Future LLM API surface

The future LLM surface should be deliberately constrained so the user does not lose trust.

### Minimal configuration

The first version should expose only:

- provider
- model
- API key / environment status
- default output mode

Avoid surfacing advanced decoding controls until the workflow proves itself.

### Safe generation loop

A trustworthy loop would look like this:

1. User drops a source.
2. Anki extracts text or metadata locally where possible.
3. User chooses an LLM action.
4. Anki shows a structured preview: draft front, draft back, tags, deck, note type.
5. User accepts, edits, or regenerates.

### Clear failure states

If the LLM fails, the source should still remain attached to the note so no capture effort is lost.

## Card organization defaults

A simpler organization model for the LLM era:

- **Deck = destination**: what area of study the card belongs to.
- **Note type = interaction pattern**: basic, cloze, image occlusion, etc.
- **Tags = source and workflow metadata**: where the content came from, whether it is still in triage, and what generation path created it.

Recommended starter defaults:

- `capture::inbox` for every new source-driven note
- `source::web::<host>` or `source::file::<name>` for provenance
- `workflow::llm` once an LLM has touched the note
- `workflow::manual` for notes authored entirely by hand

This keeps the system flexible without forcing a new collection model on existing users.

## What should happen next

1. Keep the quick-intake strip lightweight and reversible.
2. Validate whether source-aware tagging actually reduces inbox chaos.
3. Add preview-first LLM actions instead of full auto-generation.
4. Measure time-to-first-card from dropped source versus the current typed workflow.
5. Consider an eventual dedicated “Learn from source” window if the add-cards prototype proves too cramped.

## Source preview loop

A source-first interface should expose a lightweight **Source preview** surface directly next to the LLM workspace. After a file or URL is captured, the user should immediately see which source is active and what the next step is.

The ideal inline loop is:

1. Capture a file or URL.
2. See a Source preview summary in the Add Cards banner.
3. Choose Summarize, Q&A, or Cloze.
4. Review a preview-first draft before writing into note fields.

This keeps the workflow legible without forcing the learner into a separate wizard.

## Codex connection

If Codex is the preferred provider, the Add Cards banner should expose **Connect Codex** as a first-class affordance instead of hiding provider setup behind a generic settings step. A compact inline status line should answer three questions immediately:

1. Is Codex connected?
2. What credential is missing?
3. Once connected, what action can I take next?

A simple first pass is environment detection for `OPENAI_API_KEY`, paired with preview-first messaging that makes Codex feel like the default path behind Summarize, Q&A, and Cloze.
