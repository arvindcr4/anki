// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

pub mod csv;
mod import;
mod json;

use anki_proto::import_export::csv_metadata::DupeResolution;
use anki_proto::import_export::csv_metadata::MatchScope;
use serde::Deserialize;
use serde::Serialize;

use super::LogNote;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ForeignData {
    dupe_resolution: DupeResolution,
    match_scope: MatchScope,
    default_deck: NameOrId,
    default_notetype: NameOrId,
    notes: Vec<ForeignNote>,
    notetypes: Vec<ForeignNotetype>,
    global_tags: Vec<String>,
    updated_tags: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ForeignNote {
    guid: String,
    fields: Vec<Option<String>>,
    tags: Option<Vec<String>>,
    notetype: NameOrId,
    deck: NameOrId,
    cards: Vec<ForeignCard>,
}

#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ForeignCard {
    /// Seconds-based timestamp
    pub due: i64,
    /// In days
    pub interval: u32,
    pub ease_factor: f32,
    pub reps: u32,
    pub lapses: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ForeignNotetype {
    name: String,
    fields: Vec<String>,
    templates: Vec<ForeignTemplate>,
    #[serde(default)]
    is_cloze: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ForeignTemplate {
    name: String,
    qfmt: String,
    afmt: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(untagged)]
pub enum NameOrId {
    Id(i64),
    Name(String),
}

impl Default for NameOrId {
    fn default() -> Self {
        NameOrId::Name(String::new())
    }
}

impl From<String> for NameOrId {
    fn from(s: String) -> Self {
        Self::Name(s)
    }
}

impl std::fmt::Display for NameOrId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            NameOrId::Id(did) => write!(f, "{did}"),
            NameOrId::Name(name) => write!(f, "{name}"),
        }
    }
}

impl ForeignNote {
    pub(crate) fn into_log_note(self) -> LogNote {
        LogNote {
            id: None,
            fields: self
                .fields
                .into_iter()
                .map(Option::unwrap_or_default)
                .collect(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn name_or_id_default_is_empty_name() {
        assert_eq!(NameOrId::default(), NameOrId::Name(String::new()));
    }

    #[test]
    fn name_or_id_from_string() {
        let noi: NameOrId = "test".to_string().into();
        assert_eq!(noi, NameOrId::Name("test".to_string()));
    }

    #[test]
    fn name_or_id_display_name() {
        let noi = NameOrId::Name("My Deck".to_string());
        assert_eq!(format!("{noi}"), "My Deck");
    }

    #[test]
    fn name_or_id_display_id() {
        let noi = NameOrId::Id(42);
        assert_eq!(format!("{noi}"), "42");
    }

    #[test]
    fn name_or_id_serde_roundtrip_name() {
        let noi = NameOrId::Name("hello".to_string());
        let json = serde_json::to_string(&noi).unwrap();
        let back: NameOrId = serde_json::from_str(&json).unwrap();
        assert_eq!(back, noi);
    }

    #[test]
    fn name_or_id_serde_roundtrip_id() {
        let noi = NameOrId::Id(123);
        let json = serde_json::to_string(&noi).unwrap();
        let back: NameOrId = serde_json::from_str(&json).unwrap();
        assert_eq!(back, noi);
    }

    #[test]
    fn foreign_card_default() {
        let card = ForeignCard::default();
        assert_eq!(card.due, 0);
        assert_eq!(card.interval, 0);
        assert_eq!(card.ease_factor, 0.0);
        assert_eq!(card.reps, 0);
        assert_eq!(card.lapses, 0);
    }

    #[test]
    fn foreign_note_into_log_note_with_values() {
        let note = ForeignNote {
            fields: vec![
                Some("front".into()),
                None,
                Some("extra".into()),
            ],
            ..Default::default()
        };
        let log = note.into_log_note();
        assert!(log.id.is_none());
        assert_eq!(log.fields, vec!["front", "", "extra"]);
    }

    #[test]
    fn foreign_note_into_log_note_empty() {
        let note = ForeignNote::default();
        let log = note.into_log_note();
        assert!(log.fields.is_empty());
    }

    #[test]
    fn foreign_data_serde_empty() {
        let data = ForeignData::default();
        let json = serde_json::to_string(&data).unwrap();
        let back: ForeignData = serde_json::from_str(&json).unwrap();
        assert!(back.notes.is_empty());
        assert!(back.notetypes.is_empty());
    }
}
