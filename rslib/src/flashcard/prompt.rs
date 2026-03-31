// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Prompt templates for LLM flashcard generation.
//!
//! This module provides functions to generate prompts for Basic (Q&A)
//! and Cloze (fill-in-the-blank) flashcard formats.

use serde::{Deserialize, Serialize};

use super::models::{Flashcard, SourceType};

/// Format for flashcard generation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FlashcardFormat {
    /// Basic question/answer format with front and back
    Basic,
    /// Cloze deletion format with {{c1::text}} syntax
    Cloze,
}

impl Default for FlashcardFormat {
    fn default() -> Self {
        FlashcardFormat::Basic
    }
}

/// Target card count based on content length.
#[derive(Debug, Clone)]
pub struct CardCount {
    /// Minimum cards to generate
    pub min: usize,
    /// Maximum cards to generate
    pub max: usize,
    /// Target cards based on word count
    pub target: usize,
}

impl CardCount {
    /// Calculate card count from word count.
    ///
    /// Approximately 1 card per 100 words, with min 1 and max 50.
    pub fn from_word_count(word_count: usize) -> Self {
        let target = (word_count / 100).max(1).min(50);
        CardCount {
            min: 1,
            max: 50,
            target,
        }
    }
}

/// Configuration for prompt generation.
#[derive(Debug, Clone)]
pub struct PromptConfig {
    /// Format for generated flashcards
    pub format: FlashcardFormat,
    /// Subject focus for the flashcards
    pub subject_focus: Option<String>,
    /// Whether to include tag suggestions in the response
    pub include_tags: bool,
}

impl Default for PromptConfig {
    fn default() -> Self {
        PromptConfig {
            format: FlashcardFormat::Basic,
            subject_focus: None,
            include_tags: true,
        }
    }
}

/// Generate a system prompt for Basic (Q&A) flashcard format.
pub fn basic_system_prompt(config: &PromptConfig) -> String {
    let mut prompt = String::from(
        r#"You are a flashcard generator for spaced repetition learning (Anki).
Generate clear, concise question-answer flashcard pairs from the provided content.

Rules:
- Each card should test ONE specific concept
- Questions should be precise and unambiguous
- Answers should be concise but complete
- Avoid yes/no questions; prefer "what", "how", "why", "explain"
"#,
    );

    // Add card count guidance
    prompt.push_str(&format!(
        "\n- Generate approximately 1 card per 100 words of content (minimum 1, maximum 50)" 
    ));

    // Add subject focus if provided
    if let Some(ref focus) = config.subject_focus {
        prompt.push_str(&format!(
            "\n\nSUBJECT FOCUS: {}\nOnly generate cards relevant to this subject. Ignore content not related to this focus area.",
            focus
        ));
    }

    // Add tags guidance if enabled
    if config.include_tags {
        prompt.push_str(
            r#"

Response Format:
Return ONLY a JSON array of objects with "front", "back", and "tags" keys.
Tags should include source type, content keywords (2-4 relevant words), and "generated" tag.
Example: [{"front": "What is X?", "back": "X is...", "tags": ["source-url", "keyword1", "keyword2", "generated"]}]"#
        );
    } else {
        prompt.push_str(
            r#"

Response Format:
Return ONLY a JSON array of objects with "front" and "back" keys.
Example: [{"front": "What is X?", "back": "X is..."}]"#
        );
    }

    prompt
}

/// Generate a system prompt for Cloze deletion flashcard format.
pub fn cloze_system_prompt(config: &PromptConfig) -> String {
    let mut prompt = String::from(
        r#"You are a flashcard generator for spaced repetition learning (Anki).
Generate fill-in-the-blank (Cloze) flashcards from the provided content.

Rules:
- Use {{c1::text}} syntax for cloze deletions
- Each card should have ONE clear cloze deletion
- The text around the cloze should provide enough context
- Cloze deletions should hide key terms, definitions, or important facts
- Number cloze deletions sequentially ({{c1::}}, {{c2::}}, etc.)
"#,
    );

    // Add subject focus if provided
    if let Some(ref focus) = config.subject_focus {
        prompt.push_str(&format!(
            "\n\nSUBJECT FOCUS: {}\nOnly generate cards relevant to this subject. Ignore content not related to this focus area.",
            focus
        ));
    }

    // Add tags guidance if enabled
    if config.include_tags {
        prompt.push_str(
            r#"

Response Format:
Return ONLY a JSON array of objects with "text", "tags", and optionally "back_extra" keys.
The text field should contain the cloze deletions.
Tags should include source type, content keywords (2-4 relevant words), and "generated" tag.
Example: [{"text": "Rust is a {{c1::systems}} programming language.", "tags": ["source-url", "rust", "programming", "generated"], "back_extra": ""}]"#
        );
    } else {
        prompt.push_str(
            r#"

Response Format:
Return ONLY a JSON array of objects with "text" key.
Example: [{"text": "Rust is a {{c1::systems}} programming language."}]"#
        );
    }

    prompt
}

/// Generate a user message prompt with the content.
pub fn user_message(title: Option<&str>, source_url: Option<&str>, content: &str) -> String {
    let mut message = String::new();

    if let Some(title) = title {
        message.push_str(&format!("Title: {}\n", title));
    }

    if let Some(url) = source_url {
        message.push_str(&format!("Source: {}\n", url));
    }

    message.push_str("\nContent:\n");
    message.push_str(content);

    message
}

/// Extract keywords from content for tag generation.
///
/// Returns 2-4 relevant keywords from the content.
pub fn extract_keywords(content: &str, min_word_len: usize) -> Vec<String> {
    let stop_words: Vec<&str> = vec![
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "should", "could", "may", "might", "must", "can", "this", "that", "these",
        "those", "it", "its", "as", "if", "then", "than", "so", "not", "no",
        "yes", "all", "any", "each", "every", "both", "few", "more", "most",
        "other", "some", "such", "only", "own", "same", "than", "too", "very",
    ];

    let words: Vec<&str> = content
        .split(|c: char| !c.is_alphanumeric())
        .filter(|w| w.len() >= min_word_len)
        .filter(|w| !stop_words.contains(&w.to_lowercase().as_str()))
        .collect();

    // Count word frequency
    let mut freq: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for word in &words {
        let lower = word.to_lowercase();
        *freq.entry(lower).or_insert(0) += 1;
    }

    // Sort by frequency and take top keywords
    let mut sorted: Vec<(String, usize)> = freq.into_iter().collect();
    sorted.sort_by(|a, b| b.1.cmp(&a.1));

    sorted
        .into_iter()
        .take(4)
        .map(|(word, _)| word)
        .collect()
}

/// Generate tags for a flashcard based on source type and content.
pub fn generate_tags(source_type: SourceType, content: &str) -> Vec<String> {
    let mut tags = vec!["generated".to_string()];

    // Add source type tag
    let source_tag = match source_type {
        SourceType::Text => "source-text",
        SourceType::Url => "source-url",
        SourceType::Audio => "source-audio",
        SourceType::Video => "source-video",
        SourceType::Code => "source-code",
    };
    tags.push(source_tag.to_string());

    // Add content keywords
    let keywords = extract_keywords(content, 4);
    for keyword in keywords.into_iter().take(3) {
        tags.push(keyword);
    }

    tags
}

/// Parse JSON response into flashcards.
///
/// Handles both Basic and Cloze format responses.
pub fn parse_flashcards_json(json_str: &str) -> Result<Vec<Flashcard>, String> {
    // Try to extract JSON array from the response (may be wrapped in markdown code blocks)
    let json_str = json_str.trim();
    let json_str = if json_str.starts_with("```json") {
        json_str
            .strip_prefix("```json")
            .unwrap()
            .trim_start()
    } else if json_str.starts_with("```") {
        json_str
            .strip_prefix("```")
            .unwrap()
            .trim_start()
    } else {
        json_str
    };

    let json_str = if let Some(rest) = json_str.strip_suffix("```") {
        rest
    } else {
        json_str
    };

    // Find JSON array
    let start = json_str.find('[').ok_or("No JSON array found in response")?;
    let end = json_str.rfind(']').ok_or("No closing bracket found in response")?;
    let json_str = &json_str[start..=end];

    let items: Vec<serde_json::Value> =
        serde_json::from_str(json_str).map_err(|e| format!("Failed to parse JSON: {}", e))?;

    let mut flashcards = Vec::new();
    for item in items {
        if let (Some(front), Some(back)) = (item.get("front"), item.get("back")) {
            let front = front.as_str().unwrap_or("").to_string();
            let back = back.as_str().unwrap_or("").to_string();

            if !front.is_empty() && !back.is_empty() {
                let tags: Vec<String> = item
                    .get("tags")
                    .and_then(|t| t.as_array())
                    .map(|arr| {
                        arr.iter()
                            .filter_map(|v| v.as_str().map(String::from))
                            .collect()
                    })
                    .unwrap_or_default();

                let card = Flashcard::new(front, back).with_tags(tags);
                flashcards.push(card);
            }
        }
    }

    if flashcards.is_empty() {
        return Err("No valid flashcards found in response".to_string());
    }

    Ok(flashcards)
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn test_basic_system_prompt_default() {
        let config = PromptConfig::default();
        let prompt = basic_system_prompt(&config);
        assert!(prompt.contains("question-answer"));
        assert!(prompt.contains("JSON"));
        assert!(prompt.contains("front"));
        assert!(prompt.contains("back"));
    }

    #[test]
    fn test_basic_system_prompt_with_subject() {
        let config = PromptConfig {
            format: FlashcardFormat::Basic,
            subject_focus: Some("Rust programming".to_string()),
            include_tags: true,
        };
        let prompt = basic_system_prompt(&config);
        assert!(prompt.contains("SUBJECT FOCUS"));
        assert!(prompt.contains("Rust programming"));
    }

    #[test]
    fn test_cloze_system_prompt_default() {
        let config = PromptConfig::default();
        let prompt = cloze_system_prompt(&config);
        assert!(prompt.contains("Cloze"));
        assert!(prompt.contains("{{c1::"));
        assert!(prompt.contains("JSON"));
    }

    #[test]
    fn test_user_message_with_title_and_url() {
        let msg = user_message(Some("Test Title"), Some("https://example.com"), "Test content");
        assert!(msg.contains("Title: Test Title"));
        assert!(msg.contains("Source: https://example.com"));
        assert!(msg.contains("Test content"));
    }

    #[test]
    fn test_user_message_minimal() {
        let msg = user_message(None, None, "Just content");
        assert!(msg.contains("Just content"));
        assert!(!msg.contains("Title:"));
        assert!(!msg.contains("Source:"));
    }

    #[test]
    fn test_extract_keywords_basic() {
        let content = "Rust is a systems programming language focused on safety and performance. Rust memory model prevents bugs.";
        let keywords = extract_keywords(content, 4);
        // Should contain rust, systems, programming, language, safety, performance, memory, model, prevents, bugs
        assert!(keywords.contains(&"rust".to_string()) || keywords.contains(&"rusts".to_string()));
        assert!(keywords.len() <= 4);
    }

    #[test]
    fn test_extract_keywords_stops_common_words() {
        let content = "the quick brown fox jumps over the lazy dog the quick brown";
        let keywords = extract_keywords(&content, 3);
        // "the" should be filtered out as a stop word
        assert!(!keywords.iter().any(|k| k == "the"));
    }

    #[test]
    fn test_card_count_calculation() {
        let count = CardCount::from_word_count(500);
        assert_eq!(count.target, 5); // 500 / 100 = 5
        assert_eq!(count.min, 1);
        assert_eq!(count.max, 50);
    }

    #[test]
    fn test_card_count_min() {
        let count = CardCount::from_word_count(10);
        assert_eq!(count.target, 1); // min should be 1
    }

    #[test]
    fn test_card_count_max() {
        let count = CardCount::from_word_count(10000);
        assert_eq!(count.target, 50); // max should be 50
    }

    #[test]
    fn test_generate_tags_text() {
        let tags = generate_tags(SourceType::Text, "Rust is a programming language");
        assert!(tags.contains(&"source-text".to_string()));
        assert!(tags.contains(&"generated".to_string()));
        // Should have keywords
        assert!(tags.len() >= 3);
    }

    #[test]
    fn test_generate_tags_url() {
        let tags = generate_tags(SourceType::Url, "Python tutorial about web development");
        assert!(tags.contains(&"source-url".to_string()));
        assert!(tags.contains(&"generated".to_string()));
    }

    #[test]
    fn test_generate_tags_audio() {
        let tags = generate_tags(SourceType::Audio, "Machine learning lecture");
        assert!(tags.contains(&"source-audio".to_string()));
    }

    #[test]
    fn test_generate_tags_video() {
        let tags = generate_tags(SourceType::Video, "Data science course");
        assert!(tags.contains(&"source-video".to_string()));
    }

    #[test]
    fn test_parse_flashcards_json_basic() {
        let json = r#"[
            {"front": "What is Rust?", "back": "A systems programming language", "tags": ["generated", "rust"]},
            {"front": "What is ownership?", "back": "Rust's memory management system", "tags": ["generated", "rust", "memory"]}
        ]"#;
        let cards = parse_flashcards_json(json).unwrap();
        assert_eq!(cards.len(), 2);
        assert_eq!(cards[0].front, "What is Rust?");
        assert_eq!(cards[0].back, "A systems programming language");
    }

    #[test]
    fn test_parse_flashcards_json_with_markdown() {
        let json = r#"```json
        [{"front": "What is Rust?", "back": "A programming language", "tags": ["generated"]}]
        ```"#;
        let cards = parse_flashcards_json(json).unwrap();
        assert_eq!(cards.len(), 1);
    }

    #[test]
    fn test_parse_flashcards_json_empty_array() {
        let json = r#"[]"#;
        let result = parse_flashcards_json(json);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_flashcards_json_invalid() {
        let json = r#"not json at all"#;
        let result = parse_flashcards_json(json);
        assert!(result.is_err());
    }
}
