// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::interval_kind::IntervalKind;
use crate::revlog::RevlogReviewKind;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct NewState {
    pub position: u32,
}

impl NewState {
    pub(crate) fn interval_kind(self) -> IntervalKind {
        // todo: consider packing the due number in here; it would allow us to restore
        // the original position of cards - though not as cheaply as if it were
        // a card property.
        IntervalKind::InSecs(0)
    }

    pub(crate) fn revlog_kind(self) -> RevlogReviewKind {
        RevlogReviewKind::Learning
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_state_interval_kind_is_zero_secs() {
        let state = NewState { position: 0 };
        assert_eq!(state.interval_kind(), IntervalKind::InSecs(0));
    }

    #[test]
    fn new_state_interval_kind_ignores_position() {
        let state = NewState { position: 999 };
        assert_eq!(state.interval_kind(), IntervalKind::InSecs(0));
    }

    #[test]
    fn new_state_revlog_kind_is_learning() {
        let state = NewState { position: 0 };
        assert_eq!(state.revlog_kind(), RevlogReviewKind::Learning);
    }

    #[test]
    fn new_state_default_position_is_zero() {
        let state = NewState::default();
        assert_eq!(state.position, 0);
    }
}
