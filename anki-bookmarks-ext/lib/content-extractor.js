// Unified content extractor — auto-detects HTML vs PDF and extracts accordingly

import { extractTitle, htmlToMarkdown } from "./html-to-markdown.js";
import { PdfExtractor } from "./pdf-extractor.js";

export class ContentExtractor {
    // Extract content from a URL, auto-detecting type
    // Returns { url, title, content, mode: "html"|"pdf", error? }
    static async extract(url) {
        try {
            const isPdfByUrl = PdfExtractor.isPdfUrl(url);

            const response = await fetch(url, {
                credentials: "omit",
                headers: {
                    "User-Agent": "Mozilla/5.0 (compatible; AnkiBookmarks/1.0)",
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const isPdf = isPdfByUrl || PdfExtractor.isPdfResponse(response);

            if (isPdf) {
                return await ContentExtractor.extractPdf(response, url);
            } else {
                return await ContentExtractor.extractHtml(response, url);
            }
        } catch (e) {
            return { url, title: url, content: "", mode: "html", error: e.message };
        }
    }

    // Force a specific mode
    static async extractAs(url, mode) {
        try {
            const response = await fetch(url, {
                credentials: "omit",
                headers: {
                    "User-Agent": "Mozilla/5.0 (compatible; AnkiBookmarks/1.0)",
                },
            });
            if (!response.ok) { throw new Error(`HTTP ${response.status}`); }

            if (mode === "pdf") {
                return await ContentExtractor.extractPdf(response, url);
            } else {
                return await ContentExtractor.extractHtml(response, url);
            }
        } catch (e) {
            return { url, title: url, content: "", mode, error: e.message };
        }
    }

    static async extractHtml(response, url) {
        const html = await response.text();
        const title = extractTitle(html) || url;
        const markdown = htmlToMarkdown(html);

        // Truncate to ~10000 chars for LLM context
        const content = markdown.length > 10000
            ? markdown.substring(0, 10000) + "\n\n...[truncated]"
            : markdown;

        return { url, title, content, mode: "html" };
    }

    static async extractPdf(response, url) {
        const buffer = await response.arrayBuffer();
        const text = await PdfExtractor.extractTextAsync(buffer);
        const title = ContentExtractor.titleFromUrl(url);

        if (!text || text.length < 20) {
            return {
                url,
                title,
                content: "",
                mode: "pdf",
                error: "Could not extract text from PDF (may be image-based)",
            };
        }

        return { url, title, content: text, mode: "pdf" };
    }

    static titleFromUrl(url) {
        try {
            const path = new URL(url).pathname;
            const filename = path.split("/").pop() || path;
            return decodeURIComponent(filename.replace(/\.pdf$/i, "")).replace(
                /[-_]/g,
                " ",
            );
        } catch {
            return url;
        }
    }
}
