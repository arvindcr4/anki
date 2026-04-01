// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Content ingestion service for LLM flashcard generation.
//!
//! This service handles ingesting content from URLs, audio files,
//! video files, and plain text for flashcard generation.

use std::path::Path;

use crate::error::Result;
use crate::ingestion::api::GeminiClient;
use crate::ingestion::models::Content;
use crate::ingestion::models::IngestionConfig;
use crate::ingestion::models::IngestionResult;

/// Content ingestion service.
///
/// Handles extracting content from various sources for flashcard generation.
#[derive(Clone)]
pub struct IngestionService {
    config: IngestionConfig,
    gemini_client: Option<GeminiClient>,
}

impl IngestionService {
    /// Create a new IngestionService with the given configuration.
    pub fn new(config: IngestionConfig) -> Self {
        let gemini_client = config
            .gemini_api_key
            .as_ref()
            .map(|key| GeminiClient::new(key.clone()));

        IngestionService {
            config,
            gemini_client,
        }
    }

    /// Create a new IngestionService with API key.
    pub fn with_api_key(api_key: impl Into<String>) -> Self {
        let mut config = IngestionConfig::default();
        config.gemini_api_key = Some(api_key.into());
        Self::new(config)
    }

    /// Check if the service is configured with a Gemini API key.
    pub fn is_configured(&self) -> bool {
        self.gemini_client.is_some()
    }

    /// Ingest content from a URL using Gemini's urlContext.
    ///
    /// Extracts and summarizes the content from the given URL.
    pub async fn ingest_url(&self, url: &str) -> IngestionResult {
        let client = match &self.gemini_client {
            Some(client) => client,
            None => return IngestionResult::failure("Gemini API key not configured"),
        };

        match client.extract_url_context(url, "gemini-2.0-flash").await {
            Ok(response) => {
                let content = Content::from_url(response.text, url);
                IngestionResult::success(content)
            }
            Err(e) => IngestionResult::failure(format!("Failed to extract URL content: {:?}", e)),
        }
    }

    /// Ingest content from an audio file using Gemini Files API.
    ///
    /// Uploads the audio file and returns transcription.
    pub async fn ingest_audio(&self, file_path: &Path) -> IngestionResult {
        let file_path_str = file_path.to_string_lossy().into_owned();

        // Check file exists
        if !file_path.exists() {
            return IngestionResult::failure(format!("Audio file not found: {}", file_path_str));
        }

        let client = match &self.gemini_client {
            Some(client) => client,
            None => return IngestionResult::failure("Gemini API key not configured"),
        };

        // Upload the audio file
        match client.upload_file(&file_path_str).await {
            Ok(upload_response) => {
                let file_uri = upload_response.file.uri;

                // Generate transcription from the uploaded file
                let transcription_prompt = "Transcribe this audio file exactly. Include all spoken words. If there are multiple speakers, indicate speaker changes if possible.";

                match client
                    .generate_content_with_file("gemini-2.0-flash", &file_uri, transcription_prompt)
                    .await
                {
                    Ok(response) => {
                        let text = extract_text_from_response(&response);
                        let content = Content::from_audio(text, &file_path_str);
                        IngestionResult::success(content)
                    }
                    Err(e) => IngestionResult::failure(format!("Transcription failed: {:?}", e)),
                }
            }
            Err(e) => IngestionResult::failure(format!("Upload failed: {:?}", e)),
        }
    }

    /// Ingest content from a video file by extracting audio and transcribing.
    ///
    /// Uses ffmpeg to extract audio from video, then transcribes via Gemini.
    pub async fn ingest_video(&self, file_path: &Path) -> IngestionResult {
        let file_path_str = file_path.to_string_lossy().into_owned();

        // Check file exists
        if !file_path.exists() {
            return IngestionResult::failure(format!("Video file not found: {}", file_path_str));
        }

        // Extract audio from video using ffmpeg
        let temp_audio = match extract_audio_from_video(&file_path_str) {
            Ok(path) => path,
            Err(e) => return IngestionResult::failure(format!("Audio extraction failed: {}", e)),
        };

        // Process audio for transcription
        let client = match &self.gemini_client {
            Some(client) => client,
            None => {
                let _ = tokio::fs::remove_file(&temp_audio).await;
                return IngestionResult::failure("Gemini API key not configured");
            }
        };

        // Upload the extracted audio
        match client.upload_file(&temp_audio).await {
            Ok(upload_response) => {
                let file_uri = upload_response.file.uri;

                // Clean up temp audio file
                let _ = tokio::fs::remove_file(&temp_audio).await;

                // Generate transcription
                let transcription_prompt =
                    "Transcribe this video's audio exactly. Include all spoken words.";

                match client
                    .generate_content_with_file("gemini-2.0-flash", &file_uri, transcription_prompt)
                    .await
                {
                    Ok(response) => {
                        let text = extract_text_from_response(&response);
                        let content = Content::from_video(text, &file_path_str);
                        IngestionResult::success(content)
                    }
                    Err(e) => IngestionResult::failure(format!("Transcription failed: {:?}", e)),
                }
            }
            Err(e) => {
                let _ = tokio::fs::remove_file(&temp_audio).await;
                IngestionResult::failure(format!("Upload failed: {:?}", e))
            }
        }
    }

    /// Ingest plain text content directly.
    ///
    /// The text is wrapped in a Content struct and returned for LLM processing.
    pub fn ingest_text(&self, text: &str) -> IngestionResult {
        if text.trim().is_empty() {
            return IngestionResult::failure("Text content is empty");
        }

        if text.chars().count() > self.config.max_content_size {
            return IngestionResult::failure(format!(
                "Text exceeds maximum size of {} characters",
                self.config.max_content_size
            ));
        }

        let content = Content::from_text(text);
        IngestionResult::success(content)
    }

    /// Get a preview of the content without full extraction.
    ///
    /// For URLs, returns a preview of what would be extracted.
    /// For text, returns the first 500 characters.
    pub fn preview(&self, source: &str, source_type: crate::flashcard::SourceType) -> String {
        match source_type {
            crate::flashcard::SourceType::Text => source.chars().take(500).collect::<String>(),
            crate::flashcard::SourceType::Url => {
                format!("URL: {}", source)
            }
            crate::flashcard::SourceType::Audio => {
                format!("Audio file: {}", source)
            }
            crate::flashcard::SourceType::Video => {
                format!("Video file: {}", source)
            }
            crate::flashcard::SourceType::Code => source.chars().take(500).collect::<String>(),
        }
    }
}

/// Extract audio from video file using ffmpeg.
fn extract_audio_from_video(video_path: &str) -> Result<String> {
    use std::process::Command;

    let temp_dir = std::env::temp_dir();
    let output_path = temp_dir.join(format!(
        "anki_video_extract_{}.wav",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis()
    ));

    let output_path_str = output_path.to_string_lossy().to_string();

    let output = Command::new("ffmpeg")
        .args([
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            &output_path_str,
        ])
        .output()
        .map_err(|e| crate::error::AnkiError::NetworkError {
            source: crate::error::NetworkError {
                info: format!("Failed to run ffmpeg: {}", e),
                kind: crate::error::NetworkErrorKind::Other,
            },
        })?;

    if output.status.success() {
        Ok(output_path_str)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(crate::error::AnkiError::NetworkError {
            source: crate::error::NetworkError {
                info: format!("ffmpeg extraction failed: {}", stderr),
                kind: crate::error::NetworkErrorKind::Other,
            },
        })
    }
}

/// Extract text from Gemini GenerateContentResponse.
fn extract_text_from_response(response: &crate::ingestion::api::GenerateContentResponse) -> String {
    response
        .candidates
        .as_ref()
        .and_then(|c| c.first())
        .and_then(|candidate| candidate.content.as_ref())
        .and_then(|content| content.parts.as_ref())
        .and_then(|parts| parts.first())
        .and_then(|part| part.text.as_ref())
        .cloned()
        .unwrap_or_default()
}

#[cfg(test)]
mod test {
    use std::path::PathBuf;

    use super::*;

    #[test]
    fn test_ingestion_service_creation() {
        let service = IngestionService::with_api_key("test-key");
        assert!(service.is_configured());
    }

    #[test]
    fn test_ingestion_service_unconfigured() {
        let config = IngestionConfig::default();
        let service = IngestionService::new(config);
        assert!(!service.is_configured());
    }

    #[test]
    fn test_ingestion_text_empty() {
        let service = IngestionService::with_api_key("test-key");
        let result = service.ingest_text("");
        assert!(!result.success);
    }

    #[test]
    fn test_ingestion_text_success() {
        let service = IngestionService::with_api_key("test-key");
        let result = service.ingest_text("This is sample text content.");
        assert!(result.success);
        assert_eq!(
            result.content.source_type,
            crate::flashcard::SourceType::Text
        );
    }

    #[test]
    fn test_preview_text() {
        let service = IngestionService::with_api_key("test-key");
        let preview = service.preview("Short text", crate::flashcard::SourceType::Text);
        assert_eq!(preview, "Short text");
    }

    #[test]
    fn test_preview_url() {
        let service = IngestionService::with_api_key("test-key");
        let preview = service.preview("https://example.com", crate::flashcard::SourceType::Url);
        assert!(preview.contains("example.com"));
    }

    #[test]
    fn test_preview_long_text_truncation() {
        let service = IngestionService::with_api_key("test-key");
        let long_text = "a".repeat(1000);
        let preview = service.preview(&long_text, crate::flashcard::SourceType::Text);
        assert_eq!(preview.len(), 500);
    }

    #[test]
    fn test_extract_text_from_response() {
        let response = crate::ingestion::api::GenerateContentResponse {
            candidates: Some(vec![crate::ingestion::api::Candidate {
                content: Some(crate::ingestion::api::ContentData {
                    parts: Some(vec![crate::ingestion::api::Part {
                        text: Some("Test transcription".to_string()),
                        inline_data: None,
                        file_data: None,
                    }]),
                }),
            }]),
        };
        let text = extract_text_from_response(&response);
        assert_eq!(text, "Test transcription");
    }

    #[test]
    fn test_extract_text_from_empty_response() {
        let response = crate::ingestion::api::GenerateContentResponse { candidates: None };
        let text = extract_text_from_response(&response);
        assert_eq!(text, "");
    }
}
