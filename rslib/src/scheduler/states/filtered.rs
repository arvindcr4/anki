// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::IntervalKind;
use super::PreviewState;
use super::ReschedulingFilterState;
use super::ReviewState;
use super::SchedulingStates;
use super::StateContext;
use crate::revlog::RevlogReviewKind;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FilteredState {
    Preview(PreviewState),
    Rescheduling(ReschedulingFilterState),
}

impl FilteredState {
    pub(crate) fn interval_kind(self) -> IntervalKind {
        match self {
            FilteredState::Preview(state) => state.interval_kind(),
            FilteredState::Rescheduling(state) => state.interval_kind(),
        }
    }

    pub(crate) fn revlog_kind(self) -> RevlogReviewKind {
        match self {
            FilteredState::Preview(state) => state.revlog_kind(),
            FilteredState::Rescheduling(state) => state.revlog_kind(),
        }
    }

    pub(crate) fn next_states(self, ctx: &StateContext) -> SchedulingStates {
        match self {
            FilteredState::Preview(state) => state.next_states(ctx),
            FilteredState::Rescheduling(state) => state.next_states(ctx),
        }
    }

    pub(crate) fn review_state(self) -> Option<ReviewState> {
        match self {
            FilteredState::Preview(_) => None,
            FilteredState::Rescheduling(state) => state.original_state.review_state(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scheduler::states::NewState;
    use crate::scheduler::states::NormalState;

    #[test]
    fn preview_interval_kind() {
        let state = FilteredState::Preview(PreviewState {
            scheduled_secs: 300,
            finished: false,
        });
        assert_eq!(state.interval_kind(), IntervalKind::InSecs(300));
    }

    #[test]
    fn rescheduling_interval_kind_delegates() {
        let review = ReviewState {
            scheduled_days: 15,
            elapsed_days: 15,
            ease_factor: 2.5,
            lapses: 0,
            leeched: false,
            memory_state: None,
        };
        let state = FilteredState::Rescheduling(ReschedulingFilterState {
            original_state: NormalState::Review(review),
        });
        assert_eq!(state.interval_kind(), IntervalKind::InDays(15));
    }

    #[test]
    fn preview_revlog_kind_is_filtered() {
        let state = FilteredState::Preview(PreviewState {
            scheduled_secs: 0,
            finished: true,
        });
        assert_eq!(state.revlog_kind(), RevlogReviewKind::Filtered);
    }

    #[test]
    fn rescheduling_revlog_kind_delegates() {
        let review = ReviewState {
            scheduled_days: 10,
            elapsed_days: 10,
            ease_factor: 2.5,
            lapses: 0,
            leeched: false,
            memory_state: None,
        };
        let state = FilteredState::Rescheduling(ReschedulingFilterState {
            original_state: NormalState::Review(review),
        });
        assert_eq!(state.revlog_kind(), RevlogReviewKind::Review);
    }

    #[test]
    fn preview_review_state_is_none() {
        let state = FilteredState::Preview(PreviewState {
            scheduled_secs: 60,
            finished: false,
        });
        assert!(state.review_state().is_none());
    }

    #[test]
    fn rescheduling_review_state_from_review() {
        let review = ReviewState {
            scheduled_days: 10,
            elapsed_days: 10,
            ease_factor: 2.5,
            lapses: 2,
            leeched: false,
            memory_state: None,
        };
        let state = FilteredState::Rescheduling(ReschedulingFilterState {
            original_state: NormalState::Review(review),
        });
        assert_eq!(state.review_state(), Some(review));
    }

    #[test]
    fn rescheduling_review_state_from_new_is_none() {
        let state = FilteredState::Rescheduling(ReschedulingFilterState {
            original_state: NormalState::New(NewState { position: 0 }),
        });
        assert!(state.review_state().is_none());
    }
}
