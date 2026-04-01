// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Gemini API client for content extraction.
//!
//! This module provides HTTP client functionality for interacting with
//! the Gemini API for URL context extraction, file uploads, and text
//! generation.

use std::time::Duration;

use reqwest::Client;
use serde::Deserialize;
use serde::Serialize;

use crate::error::AnkiError;
use crate::error::Result;

/// Gemini API base URL
const GEMINI_API_BASE: &str = "https://generativelanguage.googleapis.com";

/// Gemini API client for content extraction.
#[derive(Clone)]
pub struct GeminiClient {
    client: Client,
    api_key: String,
}

impl GeminiClient {
    /// Create a new Gemini client with the given API key.
    pub fn new(api_key: impl Into<String>) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("Failed to create HTTP client");
        GeminiClient {
            client,
            api_key: api_key.into(),
        }
    }

    /// Extract content from a URL using Gemini's urlContext tool.
    pub async fn extract_url_context(&self, url: &str, model: &str) -> Result<UrlContextResponse> {
        let url_context = self.call_url_context_api(url, model).await?;

        Ok(url_context)
    }

    /// Upload a file to Gemini for processing.
    pub async fn upload_file(&self, file_path: &str) -> Result<UploadResponse> {
        let file_content =
            tokio::fs::read(file_path)
                .await
                .map_err(|e| AnkiError::FileIoError {
                    source: anki_io::FileIoError {
                        path: file_path.into(),
                        op: anki_io::FileOp::Read,
                        source: e,
                    },
                })?;

        let _file_name = std::path::Path::new(file_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("file")
            .to_string();

        let mime_type = guess_mime_type(file_path);

        let upload_url = format!(
            "{}/upload/v1beta/files?uploadType=media&mimeType={}",
            GEMINI_API_BASE,
            urlencoding::encode(&mime_type)
        );

        let response = self
            .client
            .post(&upload_url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", mime_type)
            .body(file_content)
            .send()
            .await?;

        if response.status().is_success() {
            let upload_resp: UploadResponse = response.json().await?;
            Ok(upload_resp)
        } else {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            Err(AnkiError::NetworkError {
                source: crate::error::NetworkError {
                    info: format!("Upload failed: {} - {}", status, body),
                    kind: crate::error::NetworkErrorKind::Other,
                },
            })
        }
    }

    /// Generate content using Gemini with a file reference.
    pub async fn generate_content_with_file(
        &self,
        model: &str,
        file_uri: &str,
        prompt: &str,
    ) -> Result<GenerateContentResponse> {
        let request = GenerateContentRequest {
            contents: vec![ContentPart {
                parts: vec![Part {
                    text: Some(prompt.to_string()),
                    inline_data: None,
                    file_data: Some(FileData {
                        mime_type: "audio/*".to_string(),
                        file_uri: file_uri.to_string(),
                    }),
                }],
            }],
        };

        let request_body = serde_json::to_string(&request).map_err(|e| AnkiError::JsonError {
            info: e.to_string(),
        })?;

        let url = format!(
            "{}/v1beta/models/{}:generateContent?key={}",
            GEMINI_API_BASE, model, self.api_key
        );

        let response = self
            .client
            .post(&url)
            .header("Content-Type", "application/json")
            .body(request_body)
            .send()
            .await?;

        if response.status().is_success() {
            let gen_resp: GenerateContentResponse = response.json().await?;
            Ok(gen_resp)
        } else {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            Err(AnkiError::NetworkError {
                source: crate::error::NetworkError {
                    info: format!("Generation failed: {} - {}", status, body),
                    kind: crate::error::NetworkErrorKind::Other,
                },
            })
        }
    }

    async fn call_url_context_api(&self, url: &str, _model: &str) -> Result<UrlContextResponse> {
        // Build URL for the Gemini urlContext tool
        // Note: In production, this would call the actual Gemini API
        // For now, we implement a simple fetch as placeholder
        let fetch_url = format!(
            "{}/v1beta/{}:generateContent?key={}",
            GEMINI_API_BASE, "models/gemini-2.0-flash", self.api_key
        );

        let request_body = serde_json::json!({
            "contents": [{
                "parts": [{
                    "text": format!("Extract and summarize the content from this URL: {}", url)
                }]
            }]
        });

        let response = self
            .client
            .post(&fetch_url)
            .header("Content-Type", "application/json")
            .body(request_body.to_string())
            .send()
            .await?;

        if response.status().is_success() {
            let gen_resp: GenerateContentResponse = response.json().await?;
            // Extract text from response
            let text = gen_resp
                .candidates
                .as_ref()
                .and_then(|c| c.first())
                .and_then(|candidate| candidate.content.as_ref())
                .and_then(|content| content.parts.as_ref())
                .and_then(|parts| parts.first())
                .and_then(|part| part.text.as_ref())
                .cloned()
                .unwrap_or_default();

            Ok(UrlContextResponse { text })
        } else {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            Err(AnkiError::NetworkError {
                source: crate::error::NetworkError {
                    info: format!("URL extraction failed: {} - {}", status, body),
                    kind: crate::error::NetworkErrorKind::Other,
                },
            })
        }
    }
}

// API Request/Response types

#[derive(Debug, Serialize, Deserialize)]
struct GenerateContentRequest {
    contents: Vec<ContentPart>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentPart {
    pub parts: Vec<Part>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Part {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub inline_data: Option<InlineData>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_data: Option<FileData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InlineData {
    pub mime_type: String,
    pub data: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileData {
    pub mime_type: String,
    pub file_uri: String,
}

/// Response from URL context extraction.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UrlContextResponse {
    pub text: String,
}

/// Response from file upload.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UploadResponse {
    pub file: FileInfo,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileInfo {
    pub name: String,
    pub uri: String,
    pub mime_type: String,
}

/// Response from content generation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenerateContentResponse {
    #[serde(default)]
    pub candidates: Option<Vec<Candidate>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candidate {
    #[serde(default)]
    pub content: Option<ContentData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentData {
    #[serde(default)]
    pub parts: Option<Vec<Part>>,
}

/// Guess MIME type from file extension.
fn guess_mime_type(path: &str) -> String {
    let ext = std::path::Path::new(path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    match ext.as_str() {
        "mp3" | "mpeg" => "audio/mpeg",
        "mp4" => "video/mp4",
        "wav" => "audio/wav",
        "ogg" => "audio/ogg",
        "m4a" => "audio/mp4",
        "webm" => "audio/webm",
        "flac" => "audio/flac",
        "aac" => "audio/aac",
        "pdf" => "application/pdf",
        "txt" => "text/plain",
        "html" | "htm" => "text/html",
        _ => "application/octet-stream",
    }
    .to_string()
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn test_mime_type_detection() {
        assert_eq!(guess_mime_type("audio.mp3"), "audio/mpeg");
        assert_eq!(guess_mime_type("video.mp4"), "video/mp4");
        assert_eq!(guess_mime_type("file.wav"), "audio/wav");
        assert_eq!(guess_mime_type("unknown.xyz"), "application/octet-stream");
    }

    #[test]
    fn test_gemini_client_creation() {
        let client = GeminiClient::new("test-api-key");
        assert_eq!(client.api_key, "test-api-key");
    }
}
