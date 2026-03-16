// Lightweight HTML → Markdown converter (no DOM required, works in service workers)

export function htmlToMarkdown(html) {
    let md = html;

    // Remove script, style, nav, footer, header, aside
    md = md.replace(/<script[\s\S]*?<\/script>/gi, "");
    md = md.replace(/<style[\s\S]*?<\/style>/gi, "");
    md = md.replace(/<nav[\s\S]*?<\/nav>/gi, "");
    md = md.replace(/<footer[\s\S]*?<\/footer>/gi, "");
    md = md.replace(/<aside[\s\S]*?<\/aside>/gi, "");
    md = md.replace(/<!--[\s\S]*?-->/g, "");

    // Prefer article/main content if present
    const articleMatch = md.match(/<article[^>]*>([\s\S]*?)<\/article>/i)
        || md.match(/<main[^>]*>([\s\S]*?)<\/main>/i);
    if (articleMatch) {
        md = articleMatch[1];
    }

    // Headings
    md = md.replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, "\n# $1\n");
    md = md.replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, "\n## $1\n");
    md = md.replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, "\n### $1\n");
    md = md.replace(/<h4[^>]*>([\s\S]*?)<\/h4>/gi, "\n#### $1\n");
    md = md.replace(/<h5[^>]*>([\s\S]*?)<\/h5>/gi, "\n##### $1\n");
    md = md.replace(/<h6[^>]*>([\s\S]*?)<\/h6>/gi, "\n###### $1\n");

    // Bold and italic
    md = md.replace(/<(strong|b)[^>]*>([\s\S]*?)<\/\1>/gi, "**$2**");
    md = md.replace(/<(em|i)[^>]*>([\s\S]*?)<\/\1>/gi, "*$2*");

    // Links
    md = md.replace(/<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, "[$2]($1)");

    // Images
    md = md.replace(
        /<img[^>]*alt="([^"]*)"[^>]*src="([^"]*)"[^>]*\/?>/gi,
        "![$1]($2)",
    );
    md = md.replace(
        /<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*\/?>/gi,
        "![$2]($1)",
    );

    // Code blocks
    md = md.replace(
        /<pre[^>]*><code[^>]*>([\s\S]*?)<\/code><\/pre>/gi,
        "\n```\n$1\n```\n",
    );
    md = md.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, "`$1`");

    // Blockquotes
    md = md.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (_, inner) => {
        return inner
            .split("\n")
            .map((line) => `> ${line.trim()}`)
            .join("\n");
    });

    // Lists
    md = md.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, "- $1\n");
    md = md.replace(/<\/?[ou]l[^>]*>/gi, "\n");

    // Paragraphs and line breaks
    md = md.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, "\n$1\n");
    md = md.replace(/<br\s*\/?>/gi, "\n");
    md = md.replace(/<hr\s*\/?>/gi, "\n---\n");

    // Tables (basic support)
    md = md.replace(/<table[\s\S]*?<\/table>/gi, (table) => {
        const rows = [];
        const rowMatches = table.match(/<tr[\s\S]*?<\/tr>/gi) || [];
        for (const row of rowMatches) {
            const cells = [];
            const cellMatches = row.match(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi) || [];
            for (const cell of cellMatches) {
                const text = cell.replace(/<[^>]+>/g, "").trim();
                cells.push(text);
            }
            rows.push("| " + cells.join(" | ") + " |");
        }
        if (rows.length > 0) {
            // Add header separator after first row
            const colCount = (rows[0].match(/\|/g) || []).length - 1;
            const sep = "| " + Array(colCount).fill("---").join(" | ") + " |";
            rows.splice(1, 0, sep);
        }
        return "\n" + rows.join("\n") + "\n";
    });

    // Strip remaining HTML tags
    md = md.replace(/<[^>]+>/g, "");

    // Decode HTML entities
    md = md
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, "\"")
        .replace(/&#39;/g, "'")
        .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n)))
        .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCharCode(parseInt(n, 16)));

    // Clean up whitespace
    md = md.replace(/\n{3,}/g, "\n\n").trim();

    return md;
}

// Extract page title from HTML
export function extractTitle(html) {
    const match = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    if (!match) { return null; }
    return match[1]
        .replace(/<[^>]+>/g, "")
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, "\"")
        .replace(/&#39;/g, "'")
        .trim();
}
