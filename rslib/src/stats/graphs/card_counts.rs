// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use anki_proto::stats::graphs_response::card_counts::Counts;
use anki_proto::stats::graphs_response::CardCounts;

use crate::card::Card;
use crate::card::CardQueue;
use crate::card::CardType;
use crate::stats::graphs::GraphsContext;

impl GraphsContext {
    pub(super) fn card_counts(&self) -> CardCounts {
        let mut excluding_inactive = Counts::default();
        let mut including_inactive = Counts::default();
        for card in &self.cards {
            match card.queue {
                CardQueue::Suspended => {
                    excluding_inactive.suspended += 1;
                }
                CardQueue::SchedBuried | CardQueue::UserBuried => {
                    excluding_inactive.buried += 1;
                }
                _ => increment_counts(&mut excluding_inactive, card),
            };
            increment_counts(&mut including_inactive, card);
        }
        CardCounts {
            excluding_inactive: Some(excluding_inactive),
            including_inactive: Some(including_inactive),
        }
    }
}

fn increment_counts(counts: &mut Counts, card: &Card) {
    match card.ctype {
        CardType::New => {
            counts.new_cards += 1;
        }
        CardType::Learn => {
            counts.learn += 1;
        }
        CardType::Review => {
            if card.interval < 21 {
                counts.young += 1;
            } else {
                counts.mature += 1;
            }
        }
        CardType::Relearn => {
            counts.relearn += 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn card_with_type_and_interval(ctype: CardType, interval: u32) -> Card {
        Card {
            ctype,
            interval,
            ..Default::default()
        }
    }

    #[test]
    fn new_card_counted() {
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::New, 0);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.new_cards, 1);
        assert_eq!(counts.learn, 0);
        assert_eq!(counts.young, 0);
        assert_eq!(counts.mature, 0);
        assert_eq!(counts.relearn, 0);
    }

    #[test]
    fn learn_card_counted() {
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::Learn, 0);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.learn, 1);
    }

    #[test]
    fn review_young_card() {
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::Review, 20);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.young, 1);
        assert_eq!(counts.mature, 0);
    }

    #[test]
    fn review_mature_card() {
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::Review, 21);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.young, 0);
        assert_eq!(counts.mature, 1);
    }

    #[test]
    fn review_boundary_card() {
        // interval exactly 21 should be mature
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::Review, 21);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.mature, 1);

        // interval 20 should be young
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::Review, 20);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.young, 1);
    }

    #[test]
    fn relearn_card_counted() {
        let mut counts = Counts::default();
        let card = card_with_type_and_interval(CardType::Relearn, 5);
        increment_counts(&mut counts, &card);
        assert_eq!(counts.relearn, 1);
    }

    #[test]
    fn multiple_cards_accumulate() {
        let mut counts = Counts::default();
        increment_counts(&mut counts, &card_with_type_and_interval(CardType::New, 0));
        increment_counts(&mut counts, &card_with_type_and_interval(CardType::New, 0));
        increment_counts(
            &mut counts,
            &card_with_type_and_interval(CardType::Review, 30),
        );
        increment_counts(
            &mut counts,
            &card_with_type_and_interval(CardType::Review, 10),
        );
        increment_counts(
            &mut counts,
            &card_with_type_and_interval(CardType::Learn, 0),
        );
        assert_eq!(counts.new_cards, 2);
        assert_eq!(counts.mature, 1);
        assert_eq!(counts.young, 1);
        assert_eq!(counts.learn, 1);
    }
}
