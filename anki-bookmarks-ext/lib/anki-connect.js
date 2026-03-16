// Anki server API wrapper — supports AnkiConnect and custom servers
// URL and API format are fully configurable

export class AnkiConnect {
    constructor(config = {}) {
        this.url = config.url || "http://localhost:8765";
        this.format = config.format || "anki-connect";
    }

    async invoke(action, params = {}) {
        const body = this.format === "anki-connect"
            ? { action, version: 6, params }
            : { action, params };

        const response = await fetch(this.url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        const result = await response.json();
        if (result.error) {
            throw new Error(`Anki server: ${result.error}`);
        }
        return result.result;
    }

    async getDecks() {
        return await this.invoke("deckNames");
    }

    // Find a deck that matches the given name (case-insensitive, partial match)
    // Returns exact match first, then substring match, then null
    async findMatchingDeck(name) {
        const decks = await this.getDecks();
        const lower = name.toLowerCase();

        // Exact match (case-insensitive)
        const exact = decks.find((d) => d.toLowerCase() === lower);
        if (exact) { return exact; }

        // Substring match
        const partial = decks.find(
            (d) => d.toLowerCase().includes(lower) || lower.includes(d.toLowerCase()),
        );
        if (partial) { return partial; }

        return null;
    }

    async ensureDeck(deckName) {
        const decks = await this.invoke("deckNames");
        if (!decks.includes(deckName)) {
            await this.invoke("createDeck", { deck: deckName });
        }
    }

    async addNotes(deckName, cards, modelName = "Basic") {
        await this.ensureDeck(deckName);
        const notes = cards.map((card) => ({
            deckName,
            modelName,
            fields: {
                Front: card.front,
                Back: card.back,
            },
            options: {
                allowDuplicate: false,
                duplicateScope: "deck",
            },
            tags: card.tags || ["bookmark-import"],
        }));

        const results = await this.invoke("addNotes", { notes });
        const added = results.filter((id) => id !== null).length;
        const dupes = results.filter((id) => id === null).length;
        return { added, duplicates: dupes, total: results.length };
    }

    async ping() {
        try {
            const version = await this.invoke("version");
            return { ok: true, version };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    }
}
