// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::sync::Arc;

use crate::config::ConfigKey;
use crate::prelude::*;

impl Collection {
    pub fn set_current_deck(&mut self, deck: DeckId) -> Result<OpOutput<()>> {
        self.transact(Op::SetCurrentDeck, |col| col.set_current_deck_inner(deck))
    }

    /// Fetch the current deck, falling back to the default if the previously
    /// selected deck is invalid.
    pub fn get_current_deck(&mut self) -> Result<Arc<Deck>> {
        if let Some(deck) = self.get_deck(self.get_current_deck_id())? {
            return Ok(deck);
        }
        self.get_deck(DeckId(1))?.or_not_found(DeckId(1))
    }
}

impl Collection {
    /// The returned id may reference a deck that does not exist;
    /// prefer using get_current_deck() instead.
    pub(crate) fn get_current_deck_id(&self) -> DeckId {
        self.get_config_optional(ConfigKey::CurrentDeckId)
            .unwrap_or(DeckId(1))
    }

    fn set_current_deck_inner(&mut self, deck: DeckId) -> Result<()> {
        if self.set_current_deck_id(deck)? {
            self.state.card_queues = None;
        }
        Ok(())
    }

    fn set_current_deck_id(&mut self, did: DeckId) -> Result<bool> {
        self.set_config(ConfigKey::CurrentDeckId, &did)
    }
}

#[cfg(test)]
mod tests {
    use crate::config::ConfigKey;
    use crate::prelude::*;

    #[test]
    fn current_deck_id_defaults_to_one() {
        let col = Collection::new();
        assert_eq!(col.get_current_deck_id(), DeckId(1));
    }

    #[test]
    fn get_current_deck_returns_default() {
        let mut col = Collection::new();
        let deck = col.get_current_deck().unwrap();
        assert_eq!(deck.id, DeckId(1));
    }

    #[test]
    fn set_and_get_current_deck() {
        let mut col = Collection::new();
        // default deck should exist
        let deck = col.get_current_deck().unwrap();
        assert_eq!(deck.id, DeckId(1));

        // setting to non-existent deck should fall back to default
        col.set_config(ConfigKey::CurrentDeckId, &DeckId(999))
            .unwrap();
        let deck = col.get_current_deck().unwrap();
        assert_eq!(deck.id, DeckId(1));
    }
}
