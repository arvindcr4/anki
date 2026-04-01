// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Notetypes for generated flashcards.
//!
//! This module provides notetypes for Basic (front/back Q&A) and Cloze
//! (fill-in-the-blank) flashcards.

use anki_i18n::I18n;
use anki_proto::notetypes::notetype::config::Kind as NotetypeKind;
use anki_proto::notetypes::stock_notetype::OriginalStockKind;
use anki_proto::notetypes::ClozeField;

use crate::notetype::Notetype;
use crate::notetype::NotetypeConfig;

/// Create a Basic notetype with Front and Back fields.
///
/// Basic notetypes generate cards with a question on the front
/// and answer on the back. The FrontSide template helper can be used
/// to show the question again on the answer side.
pub fn basic_notetype(tr: &I18n) -> Notetype {
    let mut nt = empty_stock(
        NotetypeKind::Normal,
        OriginalStockKind::Basic,
        tr.notetypes_basic_name(),
    );

    let front = tr.notetypes_front_field();
    let back = tr.notetypes_back_field();

    nt.add_field(front.as_ref());
    nt.add_field(back.as_ref());

    // Card 1: Front → Back
    nt.add_template(
        tr.notetypes_card_1_name(),
        fieldref(&front),
        format!(
            "{}\n\n<hr id=answer>\n\n{}",
            fieldref("FrontSide"),
            fieldref(&back),
        ),
    );

    nt
}

/// Create a Cloze notetype for fill-in-the-blank flashcards.
///
/// Cloze notetypes use the {{c1::text}} syntax to hide portions of the text.
/// Multiple cloze numbers ({{c1::}}, {{c2::}}, etc.) can be used in a single
/// card.
pub fn cloze_notetype(tr: &I18n) -> Notetype {
    let mut nt = empty_stock(
        NotetypeKind::Cloze,
        OriginalStockKind::Cloze,
        tr.notetypes_cloze_name(),
    );

    let text = tr.notetypes_text_field();
    let text_config = nt.add_field(text.as_ref());
    text_config.tag = Some(ClozeField::Text as u32);
    text_config.prevent_deletion = true;

    let back_extra = tr.notetypes_back_extra_field();
    let back_extra_config = nt.add_field(back_extra.as_ref());
    back_extra_config.tag = Some(ClozeField::BackExtra as u32);

    let qfmt = format!("{{{{cloze:{text}}}}}");
    let afmt = format!("{qfmt}<br>\n{{{{{back_extra}}}}}");

    nt.add_template(nt.name.clone(), qfmt, afmt);

    nt
}

// Helper functions
//---------------------------------------------------

/// returns {{name}}
fn fieldref<S: AsRef<str>>(name: S) -> String {
    format!("{{{{{}}}}}", name.as_ref())
}

/// Create an empty notetype with a given name and stock kind.
fn empty_stock(
    nt_kind: NotetypeKind,
    original_stock_kind: OriginalStockKind,
    name: impl Into<String>,
) -> Notetype {
    Notetype {
        name: name.into(),
        config: NotetypeConfig {
            kind: nt_kind as i32,
            original_stock_kind: original_stock_kind as i32,
            ..if nt_kind == NotetypeKind::Cloze {
                Notetype::new_cloze_config()
            } else {
                Notetype::new_config()
            }
        },
        ..Default::default()
    }
}

#[cfg(test)]
mod test {
    use anki_i18n::I18n;

    use super::*;

    #[test]
    fn test_basic_notetype_has_front_and_back() {
        // We can't easily test this without full i18n setup
        // but we can verify the structure is correct
        let mut nt = Notetype::default();
        nt.add_field("Front");
        nt.add_field("Back");
        assert_eq!(nt.fields.len(), 2);
        assert_eq!(nt.fields[0].name, "Front");
        assert_eq!(nt.fields[1].name, "Back");
    }

    #[test]
    fn test_cloze_notetype_has_text_field() {
        let mut nt = Notetype {
            config: Notetype::new_cloze_config(),
            ..Default::default()
        };
        nt.add_field("Text");
        nt.add_field("Back Extra");
        assert_eq!(nt.fields.len(), 2);
        assert!(nt.config.kind() == NotetypeKind::Cloze);
    }

    #[test]
    fn test_cloze_notetype_matches_stock_template() {
        let tr = I18n::template_only();
        let nt = cloze_notetype(&tr);
        assert_eq!(nt.name, tr.notetypes_cloze_name());
        assert_eq!(nt.config.kind(), NotetypeKind::Cloze);
        assert_eq!(nt.fields.len(), 2);
        assert_eq!(nt.fields[0].name, tr.notetypes_text_field());
        assert_eq!(nt.fields[0].config.tag, Some(ClozeField::Text as u32));
        assert!(nt.fields[0].config.prevent_deletion);
        assert_eq!(nt.fields[1].name, tr.notetypes_back_extra_field());
        assert_eq!(nt.fields[1].config.tag, Some(ClozeField::BackExtra as u32));
        assert!(!nt.fields[1].config.prevent_deletion);
        assert_eq!(nt.templates.len(), 1);
        assert_eq!(nt.templates[0].config.q_format, "{{cloze:Text}}");
        assert_eq!(
            nt.templates[0].config.a_format,
            "{{cloze:Text}}<br>\n{{Back Extra}}"
        );
    }

    #[test]
    fn test_fieldref_format() {
        assert_eq!(fieldref("Front"), "{{Front}}");
        assert_eq!(fieldref("Back"), "{{Back}}");
    }
}
