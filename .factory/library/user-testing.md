# User Testing

## Testing Surface

This mission integrates LLM flashcard generation into Anki. Testing requires:

### LLM APIs

- **MiniMax API**: Requires valid API key (MINIMAX_API_KEY)
- **Gemini API**: Requires valid API key (GEMINI_API_KEY)

### AnkiConnect

- Anki Desktop running with AnkiConnect addon installed
- AnkiConnect listens on localhost:8765
- If Anki not running, offline queue should be tested

## Content Types to Test

1. **URL Input**: Paste URL, verify content extracted, flashcards generated
2. **Audio File**: Upload .mp3/.wav/.m4a, verify transcription
3. **Video File**: Upload .mp4/.mov/.avi, verify audio extracted + transcribed
4. **Text Input**: Paste/type text, verify flashcards generated

## Card Format Verification

- Basic cards: Front/Back Q&A format
- Cloze cards: {{c1::cloze}} syntax
- Tags auto-generated from content keywords
- Card count approximately 1 per 100 words

## Error Scenarios

- Invalid API keys → specific error message
- Network timeout → retry button
- Invalid URL → validation error
- Unsupported file format → clear error
- AnkiConnect unavailable → offline indicator

## Resource Cost Classification

| Content Type      | Cost   | Time | API Calls                                 |
| ----------------- | ------ | ---- | ----------------------------------------- |
| Text (<500 words) | Low    | ~5s  | 1 MiniMax                                 |
| URL               | Medium | ~10s | 1 Gemini (urlContext)                     |
| Audio (1 min)     | Medium | ~15s | 2 Gemini (upload + transcribe)            |
| Video (1 min)     | High   | ~30s | 3+ Gemini (upload + extract + transcribe) |
