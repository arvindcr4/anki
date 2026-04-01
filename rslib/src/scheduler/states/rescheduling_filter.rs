// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::interval_kind::IntervalKind;
use super::normal::NormalState;
use super::CardState;
use super::SchedulingStates;
use super::StateContext;
use crate::revlog::RevlogReviewKind;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ReschedulingFilterState {
    pub original_state: NormalState,
}

impl ReschedulingFilterState {
    pub(crate) fn interval_kind(self) -> IntervalKind {
        self.original_state.interval_kind()
    }

    pub(crate) fn revlog_kind(self) -> RevlogReviewKind {
        self.original_state.revlog_kind()
    }

    pub(crate) fn next_states(self, ctx: &StateContext) -> SchedulingStates {
        let normal = self.original_state.next_states(ctx);
        if ctx.in_filtered_deck {
            SchedulingStates {
                current: self.into(),
                again: maybe_wrap(normal.again),
                hard: maybe_wrap(normal.hard),
                good: maybe_wrap(normal.good),
                easy: maybe_wrap(normal.easy),
            }
        } else {
            // card is marked as filtered, but not in a filtered deck; convert to normal
            normal
        }
    }
}

/// The review state is returned unchanged because cards are returned to
/// their original deck in that state; other normal states are wrapped
/// in the filtered state. Providing a filtered state is an error.
fn maybe_wrap(state: CardState) -> CardState {
    match state {
        CardState::Normal(normal) => {
            if matches!(normal, NormalState::Review(_)) {
                normal.into()
            } else {
                ReschedulingFilterState {
                    original_state: normal,
                }
                .into()
            }
        }
        CardState::Filtered(_) => {
            unreachable!()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scheduler::states::FilteredState;
    use crate::scheduler::states::LearnState;
    use crate::scheduler::states::NewState;
    use crate::scheduler::states::ReviewState;

    fn make_review() -> ReviewState {
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
    fn rescheduling_interval_kind_delegates() {
        let state = ReschedulingFilterState {
            original_state: NormalState::New(NewState { position: 0 }),
        };
        assert_eq!(state.interval_kind(), IntervalKind::InSecs(0));
    }

    #[test]
    fn rescheduling_revlog_kind_delegates() {
        let state = ReschedulingFilterState {
            original_state: NormalState::Review(make_review()),
        };
        assert_eq!(state.revlog_kind(), RevlogReviewKind::Review);
    }

    #[test]
    fn maybe_wrap_review_stays_normal() {
        let review = make_review();
        let state: CardState = NormalState::Review(review).into();
        let wrapped = maybe_wrap(state);
        assert!(matches!(wrapped, CardState::Normal(NormalState::Review(_))));
    }

    #[test]
    fn maybe_wrap_new_gets_wrapped() {
        let state: CardState = NormalState::New(NewState { position: 5 }).into();
        let wrapped = maybe_wrap(state);
        assert!(matches!(
            wrapped,
            CardState::Filtered(FilteredState::Rescheduling(ReschedulingFilterState {
                original_state: NormalState::New(NewState { position: 5 })
            }))
        ));
    }

    #[test]
    fn maybe_wrap_learning_gets_wrapped() {
        let learn = LearnState {
            remaining_steps: 2,
            scheduled_secs: 600,
            elapsed_secs: 0,
            memory_state: None,
        };
        let state: CardState = NormalState::Learning(learn).into();
        let wrapped = maybe_wrap(state);
        assert!(matches!(
            wrapped,
            CardState::Filtered(FilteredState::Rescheduling(_))
        ));
    }
}
