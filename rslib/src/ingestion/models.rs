// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Data models for content ingestion.
//!
//! These structs represent the raw content extracted from various sources
//! before it's processed by the LLM for flashcard generation.

use serde::{Deserialize, Serialize};

use crate::flashcard::SourceType;

/// Represents the raw content extracted from a source.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Content {
    /// The extracted text content
    pub text: String,
    /// The type of source this content came from
    pub source_type: SourceType,
    /// The source URL/path if applicable
    pub source_url: Option<String>,
    /// Estimated word count
    pub word_count: usize,
    /// Content preview (first ~500 characters)
    pub preview: String,
}

impl Content {
    /// Create new Content with all fields populated.
    pub fn new(text: String, source_type: SourceType, source_url: Option<String>) -> Self {
        let word_count = text.split_whitespace().count();
        let preview = text.chars().take(500).collect::<String>();
        Content {
            text,
            source_type,
            source_url,
            word_count,
            preview,
        }
    }

    /// Create Content from plain text.
    pub fn from_text(text: impl Into<String>) -> Self {
        Self::new(text.into(), SourceType::Text, None)
    }

    /// Create Content from a URL.
    pub fn from_url(text: impl Into<String>, url: impl Into<String>) -> Self {
        Self::new(text.into(), SourceType::Url, Some(url.into()))
    }

    /// Create Content from audio file transcription.
    pub fn from_audio(text: impl Into<String>, path: impl Into<String>) -> Self {
        Self::new(text.into(), SourceType::Audio, Some(path.into()))
    }

    /// Create Content from video file transcription.
    pub fn from_video(text: impl Into<String>, path: impl Into<String>) -> Self {
        Self::new(text.into(), SourceType::Video, Some(path.into()))
    }

    /// Check if content is empty.
    pub fn is_empty(&self) -> bool {
        self.text.trim().is_empty()
    }

    /// Get content length in characters.
    pub fn len_chars(&self) -> usize {
        self.text.chars().count()
    }
}

impl Default for Content {
    fn default() -> Self {
        Self::from_text("")
    }
}

/// Result of content ingestion operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestionResult {
    /// The extracted content
    pub content: Content,
    /// Whether the ingestion was successful
    pub success: bool,
    /// Error message if ingestion failed
    pub error: Option<String>,
}

impl IngestionResult {
    /// Create a successful ingestion result.
    pub fn success(content: Content) -> Self {
        IngestionResult {
            content,
            success: true,
            error: None,
        }
    }

    /// Create a failed ingestion result.
    pub fn failure(error: impl Into<String>) -> Self {
        IngestionResult {
            content: Content::default(),
            success: false,
            error: Some(error.into()),
        }
    }
}

/// Configuration for content ingestion services.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestionConfig {
    /// Gemini API key for content extraction
    pub gemini_api_key: Option<String>,
    /// Maximum content size in characters
    pub max_content_size: usize,
    /// Timeout for API requests in seconds
    pub request_timeout_secs: u64,
}

impl Default for IngestionConfig {
    fn default() -> Self {
        IngestionConfig {
            gemini_api_key: None,
            max_content_size: 100_000,
            request_timeout_secs: 30,
        }
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn test_content_from_text() {
        let content = Content::from_text("This is a test document about Rust programming.");
        assert_eq!(content.source_type, SourceType::Text);
        assert!(content.source_url.is_none());
        // Note: "programming." counts as one word with trailing punctuation
        assert_eq!(content.word_count, 8);
    }

    #[test]
    fn test_content_from_url() {
        let content = Content::from_url(
            "Article content here",
            "https://example.com/article",
        );
        assert_eq!(content.source_type, SourceType::Url);
        assert_eq!(content.source_url.as_deref(), Some("https://example.com/article"));
    }

    #[test]
    fn test_content_preview_truncation() {
        let long_text = "a".repeat(1000);
        let content = Content::from_text(long_text);
        assert_eq!(content.preview.len(), 500);
    }

    #[test]
    fn test_content_is_empty() {
        let empty = Content::from_text("");
        assert!(empty.is_empty());
        let non_empty = Content::from_text("Hello");
        assert!(!non_empty.is_empty());
    }

    #[test]
    fn test_ingestion_result_success() {
        let content = Content::from_text("Test content");
        let result = IngestionResult::success(content.clone());
        assert!(result.success);
        assert!(result.error.is_none());
        assert_eq!(result.content.text, "Test content");
    }

    #[test]
    fn test_ingestion_result_failure() {
        let result = IngestionResult::failure("Network error");
        assert!(!result.success);
        assert_eq!(result.error.as_deref(), Some("Network error"));
    }

    #[test]
    fn test_ingestion_config_defaults() {
        let config = IngestionConfig::default();
        assert!(config.gemini_api_key.is_none());
        assert_eq!(config.max_content_size, 100_000);
        assert_eq!(config.request_timeout_secs, 30);
    }
}
