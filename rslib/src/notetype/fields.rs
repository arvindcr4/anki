// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::NoteFieldConfig;
use super::NoteFieldProto;
use crate::prelude::*;

#[derive(Debug, PartialEq, Clone)]
pub struct NoteField {
    pub ord: Option<u32>,
    pub name: String,
    pub config: NoteFieldConfig,
}

impl From<NoteField> for NoteFieldProto {
    fn from(f: NoteField) -> Self {
        NoteFieldProto {
            ord: f.ord.map(Into::into),
            name: f.name,
            config: Some(f.config),
        }
    }
}

impl From<NoteFieldProto> for NoteField {
    fn from(f: NoteFieldProto) -> Self {
        NoteField {
            ord: f.ord.map(|n| n.val),
            name: f.name,
            config: f.config.unwrap_or_default(),
        }
    }
}

impl NoteField {
    pub fn new(name: impl Into<String>) -> Self {
        NoteField {
            ord: None,
            name: name.into(),
            config: NoteFieldConfig {
                id: Some(rand::random()),
                sticky: false,
                rtl: false,
                plain_text: false,
                font_name: "Arial".into(),
                font_size: 20,
                description: "".into(),
                collapsed: false,
                exclude_from_search: false,
                tag: None,
                prevent_deletion: false,
                other: vec![],
            },
        }
    }

    /// Fix the name of the field if it's valid. Otherwise explain why it's not.
    pub(crate) fn fix_name(&mut self) -> Result<()> {
        require!(!self.name.is_empty(), "Empty field name");
        let bad_chars = |c| c == ':' || c == '{' || c == '}' || c == '"';
        if self.name.contains(bad_chars) {
            self.name = self.name.replace(bad_chars, "");
        }
        // and leading/trailing whitespace and special chars
        let bad_start_chars = |c: char| c == '#' || c == '/' || c == '^' || c.is_whitespace();
        let trimmed = self.name.trim().trim_start_matches(bad_start_chars);
        require!(!trimmed.is_empty(), "Field name: {}", self.name);
        if trimmed.len() != self.name.len() {
            self.name = trimmed.into();
        }
        Ok(())
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn name() {
        let mut field = NoteField::new("  # /^ t:e{s\"t} field name #/^  ");
        assert_eq!(field.fix_name(), Ok(()));
        assert_eq!(&field.name, "test field name #/^");
    }

    #[test]
    fn new_field_defaults() {
        let field = NoteField::new("Front");
        assert_eq!(field.name, "Front");
        assert!(field.ord.is_none());
        assert_eq!(field.config.font_name, "Arial");
        assert_eq!(field.config.font_size, 20);
        assert!(!field.config.sticky);
        assert!(!field.config.rtl);
        assert!(!field.config.plain_text);
    }

    #[test]
    fn fix_name_valid_name_unchanged() {
        let mut field = NoteField::new("Front");
        assert!(field.fix_name().is_ok());
        assert_eq!(field.name, "Front");
    }

    #[test]
    fn fix_name_removes_colons() {
        let mut field = NoteField::new("my:field");
        assert!(field.fix_name().is_ok());
        assert_eq!(field.name, "myfield");
    }

    #[test]
    fn fix_name_removes_braces() {
        let mut field = NoteField::new("my{field}");
        assert!(field.fix_name().is_ok());
        assert_eq!(field.name, "myfield");
    }

    #[test]
    fn fix_name_removes_quotes() {
        let mut field = NoteField::new("my\"field\"");
        assert!(field.fix_name().is_ok());
        assert_eq!(field.name, "myfield");
    }

    #[test]
    fn fix_name_trims_leading_special() {
        let mut field = NoteField::new("#/^test");
        assert!(field.fix_name().is_ok());
        assert_eq!(field.name, "test");
    }

    #[test]
    fn fix_name_empty_fails() {
        let mut field = NoteField::new("");
        assert!(field.fix_name().is_err());
    }

    #[test]
    fn fix_name_only_bad_chars_fails() {
        let mut field = NoteField::new("::{}\"\"");
        assert!(field.fix_name().is_err());
    }

    #[test]
    fn from_proto_roundtrip() {
        let field = NoteField::new("Back");
        let proto: NoteFieldProto = field.clone().into();
        assert_eq!(proto.name, "Back");
        let back: NoteField = proto.into();
        assert_eq!(back.name, "Back");
        assert!(back.ord.is_none());
    }

    #[test]
    fn from_proto_with_ord() {
        let proto = NoteFieldProto {
            ord: Some(anki_proto::generic::UInt32 { val: 3 }),
            name: "Test".to_string(),
            config: Some(NoteFieldConfig::default()),
        };
        let field: NoteField = proto.into();
        assert_eq!(field.ord, Some(3));
        assert_eq!(field.name, "Test");
    }
}
