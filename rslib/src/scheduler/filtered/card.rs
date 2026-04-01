// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::DeckFilterContext;
use crate::card::CardQueue;
use crate::card::CardType;
use crate::prelude::*;
use crate::scheduler::timing::is_unix_epoch_timestamp;

impl Card {
    pub(crate) fn restore_queue_from_type(&mut self) {
        self.queue = match self.ctype {
            CardType::Learn | CardType::Relearn => {
                if is_unix_epoch_timestamp(self.due) {
                    // unix timestamp
                    CardQueue::Learn
                } else {
                    // day number
                    CardQueue::DayLearn
                }
            }
            CardType::New => CardQueue::New,
            CardType::Review => CardQueue::Review,
        }
    }

    pub(crate) fn move_into_filtered_deck(&mut self, ctx: &DeckFilterContext, position: i32) {
        // filtered and v1 learning cards are excluded, so odue should be guaranteed to
        // be zero
        if self.original_due != 0 {
            println!("bug: odue was set");
            return;
        }

        self.original_deck_id = self.deck_id;
        self.deck_id = ctx.target_deck;

        self.original_due = self.due;

        // if rescheduling is disabled, all cards go in the review queue
        if !ctx.config.reschedule {
            self.queue = CardQueue::Review;
        }
        if self.due > 0 {
            self.due = position;
        }
    }

    /// Restores to the original deck and clears original_due.
    /// This does not update the queue or type, so should only be used as
    /// part of an operation that adjusts those separately.
    pub(crate) fn remove_from_filtered_deck_before_reschedule(&mut self) {
        if self.original_deck_id.0 != 0 {
            self.deck_id = self.original_deck_id;
            self.original_deck_id.0 = 0;
            self.original_due = 0;
        }
    }

    pub(crate) fn original_or_current_deck_id(&self) -> DeckId {
        self.original_deck_id.or(self.deck_id)
    }

    pub(crate) fn remove_from_filtered_deck_restoring_queue(&mut self) {
        if self.original_deck_id.0 == 0 {
            // not in a filtered deck
            return;
        }

        self.deck_id = self.original_deck_id;
        self.original_deck_id.0 = 0;

        if self.original_due != 0 {
            self.due = self.original_due;
        }

        if (self.queue as i8) >= 0 {
            self.restore_queue_from_type();
        }

        self.original_due = 0;
    }

    pub(crate) fn is_filtered(&self) -> bool {
        self.original_deck_id.0 > 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restore_queue_new() {
        let mut card = Card {
            ctype: CardType::New,
            ..Default::default()
        };
        card.restore_queue_from_type();
        assert_eq!(card.queue, CardQueue::New);
    }

    #[test]
    fn restore_queue_review() {
        let mut card = Card {
            ctype: CardType::Review,
            ..Default::default()
        };
        card.restore_queue_from_type();
        assert_eq!(card.queue, CardQueue::Review);
    }

    #[test]
    fn restore_queue_learn_unix_timestamp() {
        let mut card = Card {
            ctype: CardType::Learn,
            due: 1_700_000_000, // unix timestamp
            ..Default::default()
        };
        card.restore_queue_from_type();
        assert_eq!(card.queue, CardQueue::Learn);
    }

    #[test]
    fn restore_queue_learn_day_number() {
        let mut card = Card {
            ctype: CardType::Learn,
            due: 100, // day number
            ..Default::default()
        };
        card.restore_queue_from_type();
        assert_eq!(card.queue, CardQueue::DayLearn);
    }

    #[test]
    fn original_or_current_deck_id_no_original() {
        let card = Card {
            deck_id: DeckId(5),
            original_deck_id: DeckId(0),
            ..Default::default()
        };
        assert_eq!(card.original_or_current_deck_id(), DeckId(5));
    }

    #[test]
    fn original_or_current_deck_id_has_original() {
        let card = Card {
            deck_id: DeckId(5),
            original_deck_id: DeckId(10),
            ..Default::default()
        };
        assert_eq!(card.original_or_current_deck_id(), DeckId(10));
    }

    #[test]
    fn is_filtered_true() {
        let card = Card {
            original_deck_id: DeckId(1),
            ..Default::default()
        };
        assert!(card.is_filtered());
    }

    #[test]
    fn is_filtered_false() {
        let card = Card::default();
        assert!(!card.is_filtered());
    }

    #[test]
    fn remove_from_filtered_restores_deck() {
        let mut card = Card {
            deck_id: DeckId(99),         // filtered deck
            original_deck_id: DeckId(1), // home deck
            original_due: 50,
            ..Default::default()
        };
        card.remove_from_filtered_deck_before_reschedule();
        assert_eq!(card.deck_id, DeckId(1));
        assert_eq!(card.original_deck_id, DeckId(0));
        assert_eq!(card.original_due, 0);
    }

    #[test]
    fn remove_from_filtered_noop_when_not_filtered() {
        let mut card = Card {
            deck_id: DeckId(1),
            original_deck_id: DeckId(0),
            ..Default::default()
        };
        card.remove_from_filtered_deck_before_reschedule();
        assert_eq!(card.deck_id, DeckId(1)); // unchanged
    }

    #[test]
    fn remove_restoring_queue() {
        let mut card = Card {
            ctype: CardType::Review,
            deck_id: DeckId(99),
            original_deck_id: DeckId(1),
            original_due: 50,
            due: -100,
            queue: CardQueue::Review,
            ..Default::default()
        };
        card.remove_from_filtered_deck_restoring_queue();
        assert_eq!(card.deck_id, DeckId(1));
        assert_eq!(card.due, 50);
        assert_eq!(card.queue, CardQueue::Review);
        assert_eq!(card.original_due, 0);
        assert_eq!(card.original_deck_id, DeckId(0));
    }
}
