// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::interval_kind::IntervalKind;
use super::LearnState;
use super::NewState;
use super::RelearnState;
use super::ReviewState;
use super::SchedulingStates;
use super::StateContext;
use crate::revlog::RevlogReviewKind;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum NormalState {
    New(NewState),
    Learning(LearnState),
    Review(ReviewState),
    Relearning(RelearnState),
}

impl NormalState {
    pub(crate) fn interval_kind(self) -> IntervalKind {
        match self {
            NormalState::New(state) => state.interval_kind(),
            NormalState::Learning(state) => state.interval_kind(),
            NormalState::Review(state) => state.interval_kind(),
            NormalState::Relearning(state) => state.interval_kind(),
        }
    }

    pub(crate) fn revlog_kind(self) -> RevlogReviewKind {
        match self {
            NormalState::New(state) => state.revlog_kind(),
            NormalState::Learning(state) => state.revlog_kind(),
            NormalState::Review(state) => state.revlog_kind(),
            NormalState::Relearning(state) => state.revlog_kind(),
        }
    }

    pub(crate) fn next_states(self, ctx: &StateContext) -> SchedulingStates {
        match self {
            NormalState::New(_) => {
                // New state acts like answering a failed learning card
                let next_states = LearnState {
                    remaining_steps: ctx.steps.remaining_for_failed(),
                    scheduled_secs: 0,
                    elapsed_secs: 0,
                    memory_state: None,
                }
                .next_states(ctx);
                // .. but with current as New, not Learning
                SchedulingStates {
                    current: self.into(),
                    ..next_states
                }
            }
            NormalState::Learning(state) => state.next_states(ctx),
            NormalState::Review(state) => state.next_states(ctx),
            NormalState::Relearning(state) => state.next_states(ctx),
        }
    }

    pub(crate) fn review_state(self) -> Option<ReviewState> {
        match self {
            NormalState::New(_) => None,
            NormalState::Learning(_) => None,
            NormalState::Review(state) => Some(state),
            NormalState::Relearning(RelearnState { review, .. }) => Some(review),
        }
    }

    pub(crate) fn leeched(self) -> bool {
        self.review_state().map(|r| r.leeched).unwrap_or_default()
    }
}

impl From<NewState> for NormalState {
    fn from(state: NewState) -> Self {
        NormalState::New(state)
    }
}

impl From<ReviewState> for NormalState {
    fn from(state: ReviewState) -> Self {
        NormalState::Review(state)
    }
}

impl From<LearnState> for NormalState {
    fn from(state: LearnState) -> Self {
        NormalState::Learning(state)
    }
}

impl From<RelearnState> for NormalState {
    fn from(state: RelearnState) -> Self {
        NormalState::Relearning(state)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn default_review_state() -> ReviewState {
        ReviewState {
            scheduled_days: 10,
            elapsed_days: 10,
            ease_factor: 2.5,
            lapses: 0,
            leeched: false,
            memory_state: None,
        }
    }

    #[test]
    fn interval_kind_new() {
        let state = NormalState::New(NewState { position: 0 });
        assert_eq!(state.interval_kind(), IntervalKind::InSecs(0));
    }

    #[test]
    fn interval_kind_review() {
        let state = NormalState::Review(default_review_state());
        assert_eq!(state.interval_kind(), IntervalKind::InDays(10));
    }

    #[test]
    fn revlog_kind_new() {
        let state = NormalState::New(NewState { position: 0 });
        assert_eq!(state.revlog_kind(), RevlogReviewKind::Learning);
    }

    #[test]
    fn revlog_kind_review() {
        let state = NormalState::Review(default_review_state());
        assert_eq!(state.revlog_kind(), RevlogReviewKind::Review);
    }

    #[test]
    fn review_state_from_new_is_none() {
        let state = NormalState::New(NewState { position: 0 });
        assert!(state.review_state().is_none());
    }

    #[test]
    fn review_state_from_learning_is_none() {
        let state = NormalState::Learning(LearnState {
            remaining_steps: 2,
            scheduled_secs: 60,
            elapsed_secs: 0,
            memory_state: None,
        });
        assert!(state.review_state().is_none());
    }

    #[test]
    fn review_state_from_review_is_some() {
        let review = default_review_state();
        let state = NormalState::Review(review);
        assert_eq!(state.review_state(), Some(review));
    }

    #[test]
    fn review_state_from_relearning() {
        let review = default_review_state();
        let state = NormalState::Relearning(RelearnState {
            review,
            learning: LearnState {
                remaining_steps: 1,
                scheduled_secs: 600,
                elapsed_secs: 0,
                memory_state: None,
            },
        });
        assert_eq!(state.review_state(), Some(review));
    }

    #[test]
    fn leeched_false_by_default() {
        let state = NormalState::Review(default_review_state());
        assert!(!state.leeched());
    }

    #[test]
    fn leeched_true_when_set() {
        let mut review = default_review_state();
        review.leeched = true;
        let state = NormalState::Review(review);
        assert!(state.leeched());
    }

    #[test]
    fn leeched_new_is_false() {
        let state = NormalState::New(NewState { position: 0 });
        assert!(!state.leeched());
    }

    #[test]
    fn from_new_state() {
        let new = NewState { position: 42 };
        let normal: NormalState = new.into();
        assert!(matches!(normal, NormalState::New(s) if s.position == 42));
    }

    #[test]
    fn from_review_state() {
        let review = default_review_state();
        let normal: NormalState = review.into();
        assert!(matches!(normal, NormalState::Review(_)));
    }
}
