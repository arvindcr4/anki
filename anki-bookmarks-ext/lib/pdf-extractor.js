// PDF text extraction — lightweight approach that parses raw PDF byte streams
// Works in service workers without DOM or pdf.js dependency

export class PdfExtractor {
    // Extract text from a PDF ArrayBuffer using basic stream parsing
    static extractText(buffer) {
        const bytes = new Uint8Array(buffer);
        const text = [];

        // Strategy 1: Find and decode text objects between BT/ET markers
        const content = PdfExtractor.bytesToLatin1(bytes);
        const textBlocks = PdfExtractor.extractTextBlocks(content);
        if (textBlocks.length > 0) {
            return textBlocks.join(" ");
        }

        // Strategy 2: Extract from decoded streams
        const streams = PdfExtractor.extractStreams(bytes);
        for (const stream of streams) {
            const streamText = PdfExtractor.extractTextBlocks(stream);
            text.push(...streamText);
        }

        return text.join(" ").replace(/\s+/g, " ").trim();
    }

    // Convert bytes to Latin1 string for text scanning
    static bytesToLatin1(bytes) {
        let result = "";
        for (let i = 0; i < bytes.length; i++) {
            result += String.fromCharCode(bytes[i]);
        }
        return result;
    }

    // Extract text from BT...ET blocks using Tj, TJ, ', " operators
    static extractTextBlocks(content) {
        const blocks = [];
        const btEtRegex = /BT\s([\s\S]*?)ET/g;
        let match;

        while ((match = btEtRegex.exec(content)) !== null) {
            const block = match[1];
            const texts = [];

            // Tj operator: (text) Tj
            const tjRegex = /\(([^)]*)\)\s*Tj/g;
            let tjMatch;
            while ((tjMatch = tjRegex.exec(block)) !== null) {
                texts.push(PdfExtractor.decodePdfString(tjMatch[1]));
            }

            // TJ operator: [(text) num (text) ...] TJ
            const tjArrayRegex = /\[([\s\S]*?)\]\s*TJ/g;
            let tjArrMatch;
            while ((tjArrMatch = tjArrayRegex.exec(block)) !== null) {
                const inner = tjArrMatch[1];
                const strRegex = /\(([^)]*)\)/g;
                let strMatch;
                while ((strMatch = strRegex.exec(inner)) !== null) {
                    texts.push(PdfExtractor.decodePdfString(strMatch[1]));
                }
            }

            // ' and " operators
            const quoteRegex = /\(([^)]*)\)\s*['"]/g;
            let qMatch;
            while ((qMatch = quoteRegex.exec(block)) !== null) {
                texts.push(PdfExtractor.decodePdfString(qMatch[1]));
            }

            if (texts.length > 0) {
                blocks.push(texts.join(""));
            }
        }

        return blocks;
    }

    // Decode PDF string escapes
    static decodePdfString(str) {
        return str
            .replace(/\\n/g, "\n")
            .replace(/\\r/g, "\r")
            .replace(/\\t/g, "\t")
            .replace(/\\\(/g, "(")
            .replace(/\\\)/g, ")")
            .replace(/\\\\/g, "\\")
            .replace(/\\(\d{1,3})/g, (_, oct) => String.fromCharCode(parseInt(oct, 8)));
    }

    // Decompress FlateDecode streams using DecompressionStream API
    // PDF uses raw DEFLATE (no zlib header), so we try both variants
    static async inflateAsync(bytes) {
        // Try raw deflate first (most PDF FlateDecode streams)
        for (const format of ["deflate-raw", "deflate"]) {
            try {
                const ds = new DecompressionStream(format);
                const writer = ds.writable.getWriter();
                writer.write(bytes);
                writer.close();

                const reader = ds.readable.getReader();
                const chunks = [];
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) { break; }
                    chunks.push(value);
                }

                const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
                const result = new Uint8Array(totalLength);
                let offset = 0;
                for (const chunk of chunks) {
                    result.set(chunk, offset);
                    offset += chunk.length;
                }
                return result;
            } catch {
                continue;
            }
        }
        return null;
    }

    // Decompress FlateDecode streams (most common PDF compression)
    static extractStreams(bytes) {
        // Not used directly — extractTextAsync handles decompression
        return [];
    }

    // Full async extraction with DecompressionStream support
    static async extractTextAsync(buffer) {
        const bytes = new Uint8Array(buffer);
        const content = PdfExtractor.bytesToLatin1(bytes);

        // First try direct text extraction
        const directText = PdfExtractor.extractTextBlocks(content);
        if (directText.length > 5) {
            return directText.join(" ").replace(/\s+/g, " ").trim();
        }

        // Try decompressing streams
        const text = [];
        const streamRegex = /stream\r?\n/g;
        let sMatch;
        while ((sMatch = streamRegex.exec(content)) !== null) {
            const start = sMatch.index + sMatch[0].length;
            const endIdx = content.indexOf("endstream", start);
            if (endIdx === -1) { continue; }

            const streamBytes = bytes.slice(start, endIdx);
            const inflated = await PdfExtractor.inflateAsync(streamBytes);
            if (inflated) {
                const decoded = PdfExtractor.bytesToLatin1(inflated);
                const blocks = PdfExtractor.extractTextBlocks(decoded);
                text.push(...blocks);
            }
        }

        const result = text.join(" ").replace(/\s+/g, " ").trim();

        // Truncate to ~10000 chars for LLM context
        if (result.length > 10000) {
            return result.substring(0, 10000) + "...";
        }

        return result;
    }

    // Detect if a URL likely points to a PDF
    static isPdfUrl(url) {
        const lower = url.toLowerCase();
        return (
            lower.endsWith(".pdf")
            || lower.includes(".pdf?")
            || lower.includes("/pdf/")
            || lower.includes("type=pdf")
        );
    }

    // Detect PDF from response headers
    static isPdfResponse(response) {
        const ct = response.headers.get("content-type") || "";
        return ct.includes("application/pdf");
    }
}
