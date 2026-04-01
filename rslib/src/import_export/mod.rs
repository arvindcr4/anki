// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

mod gather;
mod insert;
pub mod package;
mod service;
pub mod text;

pub use anki_proto::import_export::import_response::Log as NoteLog;
pub use anki_proto::import_export::import_response::Note as LogNote;
use snafu::Snafu;

use crate::prelude::*;
use crate::text::newlines_to_spaces;
use crate::text::strip_html_preserving_media_filenames;
use crate::text::truncate_to_char_boundary;
use crate::text::CowMapping;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ImportProgress {
    #[default]
    Extracting,
    File,
    Gathering,
    Media(usize),
    MediaCheck(usize),
    Notes(usize),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ExportProgress {
    #[default]
    File,
    Gathering,
    Notes(usize),
    Cards(usize),
    Media(usize),
}

impl Note {
    pub(crate) fn into_log_note(self) -> LogNote {
        let reduce_field = |field: String| {
            let mut reduced = strip_html_preserving_media_filenames(&field)
                .map_cow(newlines_to_spaces)
                .get_owned()
                .unwrap_or(field);
            truncate_to_char_boundary(&mut reduced, 80);
            reduced
        };

        LogNote {
            id: Some(anki_proto::notes::NoteId { nid: self.id.0 }),
            fields: self.into_fields().into_iter().map(reduce_field).collect(),
        }
    }
}

#[derive(Debug, PartialEq, Eq, Clone, Snafu)]
pub enum ImportError {
    Corrupt,
    TooNew,
    MediaImportFailed {
        info: String,
    },
    NoFieldColumn,
    EmptyFile,
    /// Two notetypes could not be merged because one was a regular one and the
    /// other one a cloze notetype.
    NotetypeKindMergeConflict,
}

impl ImportError {
    pub(crate) fn message(&self, tr: &I18n) -> String {
        match self {
            ImportError::Corrupt => tr.importing_the_provided_file_is_not_a(),
            ImportError::TooNew => tr.errors_collection_too_new(),
            ImportError::MediaImportFailed { info } => {
                tr.importing_failed_to_import_media_file(info)
            }
            ImportError::NoFieldColumn => tr.importing_file_must_contain_field_column(),
            ImportError::EmptyFile => tr.importing_file_empty(),
            ImportError::NotetypeKindMergeConflict => {
                tr.importing_cannot_merge_notetypes_of_different_kinds()
            }
        }
        .into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn import_error_message_corrupt() {
        let tr = I18n::template_only();
        let msg = ImportError::Corrupt.message(&tr);
        assert!(!msg.is_empty());
    }

    #[test]
    fn import_error_message_too_new() {
        let tr = I18n::template_only();
        let msg = ImportError::TooNew.message(&tr);
        assert!(!msg.is_empty());
    }

    #[test]
    fn import_error_message_media_failed() {
        let tr = I18n::template_only();
        let msg = ImportError::MediaImportFailed {
            info: "test.mp3".to_string(),
        }
        .message(&tr);
        assert!(!msg.is_empty());
    }

    #[test]
    fn import_error_message_no_field_column() {
        let tr = I18n::template_only();
        let msg = ImportError::NoFieldColumn.message(&tr);
        assert!(!msg.is_empty());
    }

    #[test]
    fn import_error_message_empty_file() {
        let tr = I18n::template_only();
        let msg = ImportError::EmptyFile.message(&tr);
        assert!(!msg.is_empty());
    }

    #[test]
    fn import_error_equality() {
        assert_eq!(ImportError::Corrupt, ImportError::Corrupt);
        assert_ne!(ImportError::Corrupt, ImportError::TooNew);
    }

    #[test]
    fn import_progress_default() {
        assert_eq!(ImportProgress::default(), ImportProgress::Extracting);
    }

    #[test]
    fn export_progress_default() {
        assert_eq!(ExportProgress::default(), ExportProgress::File);
    }
}
