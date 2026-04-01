// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use anki_i18n::I18n;
use snafu::Snafu;

#[derive(Debug, PartialEq, Eq, Snafu)]
pub enum FilteredDeckError {
    MustBeLeafNode,
    CanNotMoveCardsInto,
    SearchReturnedNoCards,
    FilteredDeckRequired,
}

impl FilteredDeckError {
    pub fn message(&self, tr: &I18n) -> String {
        match self {
            FilteredDeckError::MustBeLeafNode => tr.errors_filtered_parent_deck(),
            FilteredDeckError::CanNotMoveCardsInto => {
                tr.browsing_cards_cant_be_manually_moved_into()
            }
            FilteredDeckError::SearchReturnedNoCards => tr.decks_filtered_deck_search_empty(),
            FilteredDeckError::FilteredDeckRequired => tr.errors_filtered_deck_required(),
        }
        .into()
    }
}

#[derive(Debug, PartialEq, Eq, Snafu)]
pub enum CustomStudyError {
    NoMatchingCards,
    ExistingDeck,
}

impl CustomStudyError {
    pub fn message(&self, tr: &I18n) -> String {
        match self {
            Self::NoMatchingCards => tr.custom_study_no_cards_matched_the_criteria_you(),
            Self::ExistingDeck => tr.custom_study_must_rename_deck(),
        }
        .into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn filtered_deck_error_messages_not_empty() {
        let tr = I18n::template_only();
        assert!(!FilteredDeckError::MustBeLeafNode.message(&tr).is_empty());
        assert!(!FilteredDeckError::CanNotMoveCardsInto
            .message(&tr)
            .is_empty());
        assert!(!FilteredDeckError::SearchReturnedNoCards
            .message(&tr)
            .is_empty());
        assert!(!FilteredDeckError::FilteredDeckRequired
            .message(&tr)
            .is_empty());
    }

    #[test]
    fn custom_study_error_messages_not_empty() {
        let tr = I18n::template_only();
        assert!(!CustomStudyError::NoMatchingCards.message(&tr).is_empty());
        assert!(!CustomStudyError::ExistingDeck.message(&tr).is_empty());
    }

    #[test]
    fn filtered_deck_error_equality() {
        assert_eq!(
            FilteredDeckError::MustBeLeafNode,
            FilteredDeckError::MustBeLeafNode
        );
        assert_ne!(
            FilteredDeckError::MustBeLeafNode,
            FilteredDeckError::FilteredDeckRequired
        );
    }

    #[test]
    fn custom_study_error_equality() {
        assert_eq!(
            CustomStudyError::NoMatchingCards,
            CustomStudyError::NoMatchingCards
        );
        assert_ne!(
            CustomStudyError::NoMatchingCards,
            CustomStudyError::ExistingDeck
        );
    }
}
