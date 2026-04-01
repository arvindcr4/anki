// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Local SQLite storage for LLM-generated flashcards.
//!
//! This module provides storage for flashcards before they are synced to Anki.

use std::path::Path;

use rusqlite::params;
use rusqlite::Connection;
use rusqlite::Result as SqliteResult;

use crate::error::AnkiError;
use crate::error::Result;
use crate::flashcard::Flashcard;
use crate::flashcard::SourceType;

/// Sync status for a generated flashcard.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SyncStatus {
    /// Card is pending sync to Anki.
    Pending,
    /// Card has been successfully synced to Anki.
    Synced,
    /// Card sync failed.
    Failed,
}

impl SyncStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            SyncStatus::Pending => "pending",
            SyncStatus::Synced => "synced",
            SyncStatus::Failed => "failed",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "pending" => Some(SyncStatus::Pending),
            "synced" => Some(SyncStatus::Synced),
            "failed" => Some(SyncStatus::Failed),
            _ => None,
        }
    }
}

impl std::fmt::Display for SyncStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// A stored flashcard with metadata.
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct StoredCard {
    /// Unique identifier for the card.
    pub id: i64,
    /// Front content of the card.
    pub front: String,
    /// Back content of the card.
    pub back: String,
    /// Source URL if applicable.
    pub source_url: Option<String>,
    /// Type of source content.
    pub source_type: SourceType,
    /// Creation timestamp (Unix epoch seconds).
    pub created_at: i64,
    /// Current sync status.
    pub sync_status: SyncStatus,
    /// Tags associated with the card (stored as comma-separated string).
    pub tags: String,
}

impl StoredCard {
    /// Convert to a Flashcard struct.
    pub fn into_flashcard(self) -> Flashcard {
        Flashcard {
            front: self.front,
            back: self.back,
            tags: if self.tags.is_empty() {
                Vec::new()
            } else {
                self.tags.split('\x1f').map(|s| s.to_string()).collect()
            },
            source_type: self.source_type,
            source_url: self.source_url,
        }
    }

    /// Get tags as a vector.
    pub fn tags_vec(&self) -> Vec<String> {
        if self.tags.is_empty() {
            Vec::new()
        } else {
            self.tags.split('\x1f').map(|s| s.to_string()).collect()
        }
    }
}

/// Storage for LLM-generated flashcards.
#[allow(dead_code)]
pub struct GeneratedCardStorage {
    db: Connection,
}

#[allow(dead_code)]
impl GeneratedCardStorage {
    /// Open or create a generated cards database at the given path.
    pub fn open_or_create(path: &Path) -> Result<Self> {
        let db = Connection::open(path)?;
        db.execute_batch(include_str!("schema.sql"))?;
        Ok(GeneratedCardStorage { db })
    }

    /// Close the database connection.
    pub fn close(self) {
        drop(self.db);
    }

    /// Add a new flashcard to storage.
    /// Returns the ID of the inserted card.
    pub fn add_card(&self, card: &Flashcard) -> Result<i64> {
        let tags = card.tags.join("\x1f");
        let source_type = match &card.source_type {
            SourceType::Text => "text",
            SourceType::Url => "url",
            SourceType::Audio => "audio",
            SourceType::Video => "video",
            SourceType::Code => "code",
        };
        let created_at = chrono::Utc::now().timestamp();

        self.db
            .execute(
                include_str!("add.sql"),
                params![
                    &card.front,
                    &card.back,
                    &card.source_url,
                    source_type,
                    created_at,
                    SyncStatus::Pending.as_str(),
                    &tags,
                ],
            )
            .map_err(|e| AnkiError::from(e))?;

        Ok(self.db.last_insert_rowid())
    }

    /// Get a card by ID.
    pub fn get_card(&self, id: i64) -> Result<Option<StoredCard>> {
        let mut stmt = self.db.prepare_cached(include_str!("get.sql"))?;
        let mut rows = stmt.query([id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(row_to_stored_card(row)?))
        } else {
            Ok(None)
        }
    }

    /// List all cards with optional filtering.
    pub fn list_cards(&self) -> Result<Vec<StoredCard>> {
        let mut stmt = self.db.prepare_cached(include_str!("list.sql"))?;
        let rows: Vec<std::result::Result<StoredCard, _>> =
            stmt.query_map([], row_to_stored_card)?.collect();
        rows.into_iter().map(|r| r.map_err(Into::into)).collect()
    }

    /// List cards by sync status.
    pub fn list_by_sync_status(&self, status: SyncStatus) -> Result<Vec<StoredCard>> {
        let mut stmt = self.db.prepare_cached(include_str!("list_by_status.sql"))?;
        let rows: Vec<std::result::Result<StoredCard, _>> = stmt
            .query_map([status.as_str()], row_to_stored_card)?
            .collect();
        rows.into_iter().map(|r| r.map_err(Into::into)).collect()
    }

    /// List cards by source type.
    pub fn list_by_source_type(&self, source_type: SourceType) -> Result<Vec<StoredCard>> {
        let source_type_str = match source_type {
            SourceType::Text => "text",
            SourceType::Url => "url",
            SourceType::Audio => "audio",
            SourceType::Video => "video",
            SourceType::Code => "code",
        };
        let mut stmt = self.db.prepare_cached(include_str!("list_by_source.sql"))?;
        let rows: Vec<std::result::Result<StoredCard, _>> = stmt
            .query_map([source_type_str], row_to_stored_card)?
            .collect();
        rows.into_iter().map(|r| r.map_err(Into::into)).collect()
    }

    /// Update card front/back content.
    pub fn update_card(&self, id: i64, front: &str, back: &str) -> Result<bool> {
        let rows_affected: i64 = self
            .db
            .execute(include_str!("update.sql"), params![front, back, id])?
            .try_into()
            .unwrap_or(0);
        Ok(rows_affected > 0)
    }

    /// Update sync status for a card.
    pub fn update_sync_status(&self, id: i64, status: SyncStatus) -> Result<bool> {
        let rows_affected: i64 = self
            .db
            .execute(
                include_str!("update_status.sql"),
                params![status.as_str(), id],
            )?
            .try_into()
            .unwrap_or(0);
        Ok(rows_affected > 0)
    }

    /// Delete a card by ID.
    pub fn delete_card(&self, id: i64) -> Result<bool> {
        let rows_affected: i64 = self
            .db
            .execute(include_str!("delete.sql"), [id])?
            .try_into()
            .unwrap_or(0);
        Ok(rows_affected > 0)
    }

    /// Count cards by sync status.
    pub fn count_by_status(&self, status: SyncStatus) -> Result<i64> {
        let count: i64 = self.db.query_row(
            include_str!("count_by_status.sql"),
            [status.as_str()],
            |row| row.get(0),
        )?;
        Ok(count)
    }

    /// Get all pending cards.
    pub fn pending_cards(&self) -> Result<Vec<StoredCard>> {
        self.list_by_sync_status(SyncStatus::Pending)
    }

    /// Get all failed cards.
    pub fn failed_cards(&self) -> Result<Vec<StoredCard>> {
        self.list_by_sync_status(SyncStatus::Failed)
    }

    /// Get all synced cards.
    pub fn synced_cards(&self) -> Result<Vec<StoredCard>> {
        self.list_by_sync_status(SyncStatus::Synced)
    }
}

fn row_to_stored_card(row: &rusqlite::Row) -> SqliteResult<StoredCard> {
    let source_type_str: String = row.get(4)?;
    let source_type = match source_type_str.as_str() {
        "text" => SourceType::Text,
        "url" => SourceType::Url,
        "audio" => SourceType::Audio,
        "video" => SourceType::Video,
        "code" => SourceType::Code,
        other => {
            tracing::warn!("Unknown source_type in generated_card DB: {:?}, defaulting to Text", other);
            SourceType::Text
        }
    };

    let sync_status_str: String = row.get(6)?;
    let sync_status = match SyncStatus::from_str(&sync_status_str) {
        Some(s) => s,
        None => {
            tracing::warn!("Unknown sync_status in generated_card DB: {:?}, defaulting to Pending", sync_status_str);
            SyncStatus::Pending
        }
    };

    Ok(StoredCard {
        id: row.get(0)?,
        front: row.get(1)?,
        back: row.get(2)?,
        source_url: row.get(3)?,
        source_type,
        created_at: row.get(5)?,
        sync_status,
        tags: row.get(7)?,
    })
}

#[cfg(test)]
mod test {
    use tempfile::tempdir;

    use super::*;

    fn temp_storage() -> (GeneratedCardStorage, tempfile::TempDir) {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test_cards.db");
        let storage = GeneratedCardStorage::open_or_create(&path).unwrap();
        (storage, dir)
    }

    #[test]
    fn test_add_card() {
        let (storage, _dir) = temp_storage();
        let card = Flashcard::new("What is Rust?", "A systems programming language.")
            .with_tags(vec!["programming".into(), "rust".into()])
            .with_source_type(SourceType::Url)
            .with_source_url("https://rust-lang.org");

        let id = storage.add_card(&card).unwrap();
        assert!(id > 0);
    }

    #[test]
    fn test_get_card() {
        let (storage, _dir) = temp_storage();
        let card = Flashcard::new("What is Rust?", "A systems programming language.")
            .with_source_type(SourceType::Text);

        let id = storage.add_card(&card).unwrap();
        let retrieved = storage.get_card(id).unwrap().unwrap();

        assert_eq!(retrieved.front, "What is Rust?");
        assert_eq!(retrieved.back, "A systems programming language.");
        assert_eq!(retrieved.sync_status, SyncStatus::Pending);
    }

    #[test]
    fn test_update_card() {
        let (storage, _dir) = temp_storage();
        let card = Flashcard::new("What is Rust?", "A systems programming language.")
            .with_source_type(SourceType::Text);

        let id = storage.add_card(&card).unwrap();
        let updated = storage
            .update_card(id, "What is Rust?", "A programming language for safety.")
            .unwrap();

        assert!(updated);
        let retrieved = storage.get_card(id).unwrap().unwrap();
        assert_eq!(retrieved.back, "A programming language for safety.");
    }

    #[test]
    fn test_delete_card() {
        let (storage, _dir) = temp_storage();
        let card = Flashcard::new("What is Rust?", "A systems programming language.")
            .with_source_type(SourceType::Text);

        let id = storage.add_card(&card).unwrap();
        let deleted = storage.delete_card(id).unwrap();

        assert!(deleted);
        assert!(storage.get_card(id).unwrap().is_none());
    }

    #[test]
    fn test_update_sync_status() {
        let (storage, _dir) = temp_storage();
        let card = Flashcard::new("What is Rust?", "A systems programming language.")
            .with_source_type(SourceType::Text);

        let id = storage.add_card(&card).unwrap();

        // Pending -> Failed
        let updated = storage.update_sync_status(id, SyncStatus::Failed).unwrap();
        assert!(updated);
        let retrieved = storage.get_card(id).unwrap().unwrap();
        assert_eq!(retrieved.sync_status, SyncStatus::Failed);

        // Failed -> Synced
        let updated = storage.update_sync_status(id, SyncStatus::Synced).unwrap();
        assert!(updated);
        let retrieved = storage.get_card(id).unwrap().unwrap();
        assert_eq!(retrieved.sync_status, SyncStatus::Synced);
    }

    #[test]
    fn test_list_by_status() {
        let (storage, _dir) = temp_storage();

        // Add cards with different statuses
        let card1 = Flashcard::new("Card 1", "Answer 1").with_source_type(SourceType::Text);
        let card2 = Flashcard::new("Card 2", "Answer 2").with_source_type(SourceType::Text);
        let card3 = Flashcard::new("Card 3", "Answer 3").with_source_type(SourceType::Text);

        let id1 = storage.add_card(&card1).unwrap();
        let id2 = storage.add_card(&card2).unwrap();
        let id3 = storage.add_card(&card3).unwrap();

        // Update statuses
        storage.update_sync_status(id2, SyncStatus::Synced).unwrap();
        storage.update_sync_status(id3, SyncStatus::Failed).unwrap();

        let pending = storage.pending_cards().unwrap();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].id, id1);

        let synced = storage.synced_cards().unwrap();
        assert_eq!(synced.len(), 1);
        assert_eq!(synced[0].id, id2);

        let failed = storage.failed_cards().unwrap();
        assert_eq!(failed.len(), 1);
        assert_eq!(failed[0].id, id3);
    }

    #[test]
    fn test_list_by_source_type() {
        let (storage, _dir) = temp_storage();

        let card_url = Flashcard::new("URL Card", "Answer").with_source_type(SourceType::Url);
        let card_audio = Flashcard::new("Audio Card", "Answer").with_source_type(SourceType::Audio);
        let card_text = Flashcard::new("Text Card", "Answer").with_source_type(SourceType::Text);

        storage.add_card(&card_url).unwrap();
        storage.add_card(&card_audio).unwrap();
        storage.add_card(&card_text).unwrap();

        let url_cards = storage.list_by_source_type(SourceType::Url).unwrap();
        assert_eq!(url_cards.len(), 1);

        let audio_cards = storage.list_by_source_type(SourceType::Audio).unwrap();
        assert_eq!(audio_cards.len(), 1);

        let text_cards = storage.list_by_source_type(SourceType::Text).unwrap();
        assert_eq!(text_cards.len(), 1);
    }

    #[test]
    fn test_into_flashcard() {
        let stored = StoredCard {
            id: 1,
            front: "Front".into(),
            back: "Back".into(),
            source_url: Some("https://example.com".into()),
            source_type: SourceType::Url,
            created_at: 1234567890,
            sync_status: SyncStatus::Pending,
            tags: "tag1,tag2,tag3".into(),
        };

        let flashcard = stored.into_flashcard();
        assert_eq!(flashcard.front, "Front");
        assert_eq!(flashcard.back, "Back");
        assert_eq!(flashcard.tags, vec!["tag1", "tag2", "tag3"]);
        assert_eq!(flashcard.source_type, SourceType::Url);
    }

    #[test]
    fn test_sync_status_transitions() {
        let (storage, _dir) = temp_storage();
        let card = Flashcard::new("Card", "Answer").with_source_type(SourceType::Text);
        let id = storage.add_card(&card).unwrap();

        // Verify initial state is pending
        assert_eq!(
            storage.get_card(id).unwrap().unwrap().sync_status,
            SyncStatus::Pending
        );

        // pending -> failed
        storage.update_sync_status(id, SyncStatus::Failed).unwrap();
        assert_eq!(
            storage.get_card(id).unwrap().unwrap().sync_status,
            SyncStatus::Failed
        );

        // failed -> pending (retry)
        storage.update_sync_status(id, SyncStatus::Pending).unwrap();
        assert_eq!(
            storage.get_card(id).unwrap().unwrap().sync_status,
            SyncStatus::Pending
        );

        // pending -> synced
        storage.update_sync_status(id, SyncStatus::Synced).unwrap();
        assert_eq!(
            storage.get_card(id).unwrap().unwrap().sync_status,
            SyncStatus::Synced
        );
    }

    #[test]
    fn test_stored_card_tags_vec() {
        let stored = StoredCard {
            id: 1,
            front: "Front".into(),
            back: "Back".into(),
            source_url: None,
            source_type: SourceType::Text,
            created_at: 0,
            sync_status: SyncStatus::Pending,
            tags: "one,two,three".into(),
        };

        let tags = stored.tags_vec();
        assert_eq!(tags, vec!["one", "two", "three"]);
    }

    #[test]
    fn test_empty_tags() {
        let stored = StoredCard {
            id: 1,
            front: "Front".into(),
            back: "Back".into(),
            source_url: None,
            source_type: SourceType::Text,
            created_at: 0,
            sync_status: SyncStatus::Pending,
            tags: "".into(),
        };

        assert!(stored.tags_vec().is_empty());
    }
}
