// Generates flashcards from text using LLM APIs (Claude, OpenAI, or Gemini)

export class FlashcardGenerator {
    constructor(config) {
        this.provider = config.provider || "claude";
        this.apiKey = config.apiKey;
        this.model = config.model || this.defaultModel();
        this.subjectPrompt = config.subjectPrompt || "";
    }

    defaultModel() {
        switch (this.provider) {
            case "claude":
                return "claude-sonnet-4-20250514";
            case "openai":
                return "gpt-4o-mini";
            case "gemini":
                return "gemini-3-flash-preview";
            default:
                return "claude-sonnet-4-20250514";
        }
    }

    async generate(pageContent) {
        const { title, text, url } = pageContent;
        if (!text || text.length < 50) {
            return [];
        }

        const systemPrompt = `You are a flashcard generator for spaced repetition learning (Anki).
Generate clear, concise question-answer flashcard pairs from the provided content.

Rules:
- Each card should test ONE specific concept
- Questions should be precise and unambiguous
- Answers should be concise but complete
- Avoid yes/no questions; prefer "what", "how", "why", "explain"
- Generate 3-10 cards depending on content density
- Focus on key facts, concepts, and relationships

${
            this.subjectPrompt
                ? `SUBJECT FOCUS: ${this.subjectPrompt}\nOnly generate cards relevant to this subject. Ignore content not related to this focus area.`
                : ""
        }

Respond ONLY with a JSON array of objects with "front" and "back" keys.
Example: [{"front": "What is X?", "back": "X is..."}]`;

        const userMessage = `Page: ${title}\nURL: ${url}\n\nContent:\n${text}`;

        try {
            let cards;
            switch (this.provider) {
                case "openai":
                    cards = await this.callOpenAI(systemPrompt, userMessage);
                    break;
                case "gemini":
                    cards = await this.callGemini(systemPrompt, userMessage);
                    break;
                default:
                    cards = await this.callClaude(systemPrompt, userMessage);
                    break;
            }

            return cards.map((c) => ({
                ...c,
                tags: ["bookmark-import", this.slugify(title)],
            }));
        } catch (e) {
            console.error("Flashcard generation failed:", e);
            throw e;
        }
    }

    async callClaude(systemPrompt, userMessage) {
        const response = await fetch("https://api.anthropic.com/v1/messages", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "x-api-key": this.apiKey,
                "anthropic-version": "2023-06-01",
                "anthropic-dangerous-direct-browser-access": "true",
            },
            body: JSON.stringify({
                model: this.model,
                max_tokens: 4096,
                system: systemPrompt,
                messages: [{ role: "user", content: userMessage }],
            }),
        });

        if (!response.ok) {
            throw new Error(`Claude API returned ${response.status}`);
        }

        const data = await response.json();
        const text = data.content[0].text;
        return this.parseJSON(text);
    }

    async callOpenAI(systemPrompt, userMessage) {
        const response = await fetch("https://api.openai.com/v1/chat/completions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${this.apiKey}`,
            },
            body: JSON.stringify({
                model: this.model,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: userMessage },
                ],
                temperature: 0.3,
            }),
        });

        if (!response.ok) {
            throw new Error(`OpenAI API returned ${response.status}`);
        }

        const data = await response.json();
        const text = data.choices[0].message.content;
        return this.parseJSON(text);
    }

    async callGemini(systemPrompt, userMessage) {
        const url =
            `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;

        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                systemInstruction: {
                    parts: [{ text: systemPrompt }],
                },
                contents: [
                    {
                        role: "user",
                        parts: [{ text: userMessage }],
                    },
                ],
                generationConfig: {
                    temperature: 0.3,
                    maxOutputTokens: 4096,
                },
            }),
        });

        if (!response.ok) {
            throw new Error(`Gemini API returned ${response.status}`);
        }

        const data = await response.json();
        const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!text) { throw new Error("Empty response from Gemini"); }
        return this.parseJSON(text);
    }

    parseJSON(text) {
        // Extract JSON array from response (handles markdown code blocks)
        const match = text.match(/\[[\s\S]*\]/);
        if (!match) { throw new Error("No JSON array found in LLM response"); }
        const cards = JSON.parse(match[0]);
        if (!Array.isArray(cards)) { throw new Error("Response is not an array"); }
        return cards.filter((c) => c.front && c.back);
    }

    slugify(str) {
        return str
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "")
            .substring(0, 30);
    }
}
