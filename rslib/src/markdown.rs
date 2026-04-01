// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use pulldown_cmark::html;
use pulldown_cmark::Parser;

pub(crate) fn render_markdown(markdown: &str) -> String {
    let mut buf = String::with_capacity(markdown.len());
    let parser = Parser::new(markdown);
    html::push_html(&mut buf, parser);
    buf
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_text() {
        assert_eq!(render_markdown("hello"), "<p>hello</p>\n");
    }

    #[test]
    fn bold() {
        assert_eq!(
            render_markdown("**bold**"),
            "<p><strong>bold</strong></p>\n"
        );
    }

    #[test]
    fn italic() {
        assert_eq!(render_markdown("*italic*"), "<p><em>italic</em></p>\n");
    }

    #[test]
    fn heading() {
        assert_eq!(render_markdown("# Title"), "<h1>Title</h1>\n");
    }

    #[test]
    fn link() {
        let result = render_markdown("[text](http://example.com)");
        assert!(result.contains("<a"));
        assert!(result.contains("http://example.com"));
    }

    #[test]
    fn empty() {
        assert_eq!(render_markdown(""), "");
    }

    #[test]
    fn multiline() {
        let result = render_markdown("line1\n\nline2");
        assert!(result.contains("line1"));
        assert!(result.contains("line2"));
    }
}
