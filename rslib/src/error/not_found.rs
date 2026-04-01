// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::any;
use std::fmt;

use convert_case::Case;
use convert_case::Casing;
use snafu::Backtrace;
use snafu::OptionExt;
use snafu::Snafu;

use crate::prelude::*;

/// Something was unexpectedly missing from the database.
#[derive(Debug, Snafu)]
#[snafu(visibility(pub))]
pub struct NotFoundError {
    pub type_name: String,
    pub identifier: String,
    pub backtrace: Option<Backtrace>,
}

impl NotFoundError {
    pub fn message(&self, tr: &I18n) -> String {
        format!(
            "{} No such {}: '{}'",
            tr.errors_inconsistent_db_state(),
            self.type_name,
            self.identifier
        )
    }

    pub fn context(&self) -> String {
        format!("No such {}: '{}'", self.type_name, self.identifier)
    }
}

impl PartialEq for NotFoundError {
    fn eq(&self, other: &Self) -> bool {
        self.type_name == other.type_name && self.identifier == other.identifier
    }
}

impl Eq for NotFoundError {}

/// Allows generating [AnkiError::NotFound] from [None].
pub trait OrNotFound {
    type Value;
    fn or_not_found(self, identifier: impl fmt::Display) -> Result<Self::Value>;
}

impl<T> OrNotFound for Option<T> {
    type Value = T;

    fn or_not_found(self, identifier: impl fmt::Display) -> Result<Self::Value> {
        self.with_context(|| NotFoundSnafu {
            type_name: unqualified_lowercase_type_name::<Self::Value>(),
            identifier: format!("{identifier}"),
        })
        .map_err(Into::into)
    }
}

fn unqualified_lowercase_type_name<T: ?Sized>() -> String {
    any::type_name::<T>()
        .split("::")
        .last()
        .unwrap_or_default()
        .to_case(Case::Lower)
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn test_unqualified_lowercase_type_name() {
        assert_eq!(unqualified_lowercase_type_name::<CardId>(), "card id");
    }

    #[test]
    fn not_found_error_context() {
        let err = NotFoundError {
            type_name: "deck".into(),
            identifier: "42".into(),
            backtrace: None,
        };
        assert_eq!(err.context(), "No such deck: '42'");
    }

    #[test]
    fn not_found_error_message() {
        let tr = I18n::template_only();
        let err = NotFoundError {
            type_name: "card".into(),
            identifier: "123".into(),
            backtrace: None,
        };
        let msg = err.message(&tr);
        assert!(msg.contains("card"));
        assert!(msg.contains("123"));
    }

    #[test]
    fn not_found_error_equality() {
        let a = NotFoundError {
            type_name: "card".into(),
            identifier: "1".into(),
            backtrace: None,
        };
        let b = NotFoundError {
            type_name: "card".into(),
            identifier: "1".into(),
            backtrace: None,
        };
        assert_eq!(a, b);
    }

    #[test]
    fn not_found_error_inequality() {
        let a = NotFoundError {
            type_name: "card".into(),
            identifier: "1".into(),
            backtrace: None,
        };
        let b = NotFoundError {
            type_name: "deck".into(),
            identifier: "1".into(),
            backtrace: None,
        };
        assert_ne!(a, b);
    }

    #[test]
    fn or_not_found_some() {
        let result: Result<i32> = Some(42).or_not_found(DeckId(1));
        assert_eq!(result.unwrap(), 42);
    }

    #[test]
    fn or_not_found_none() {
        let result: Result<i32> = None.or_not_found(DeckId(999));
        assert!(result.is_err());
    }

    #[test]
    fn unqualified_name_simple() {
        assert_eq!(unqualified_lowercase_type_name::<String>(), "string");
    }

    #[test]
    fn unqualified_name_deck_id() {
        assert_eq!(unqualified_lowercase_type_name::<DeckId>(), "deck id");
    }
}
