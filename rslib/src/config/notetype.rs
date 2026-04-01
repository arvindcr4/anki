// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use strum::IntoStaticStr;

use super::ConfigKey;
use crate::notetype::NotetypeKind;
use crate::prelude::*;

/// Notetype config packed into a collection config key. This may change
/// frequently, and we want to avoid the potentially expensive notetype
/// write/sync.
#[derive(Debug, Clone, Copy, IntoStaticStr)]
#[strum(serialize_all = "camelCase")]
enum NotetypeConfigKey {
    #[strum(to_string = "lastDeck")]
    LastDeckAddedTo,
}

impl Collection {
    pub fn get_aux_template_config_key(
        &mut self,
        ntid: NotetypeId,
        card_ordinal: usize,
        key: &str,
    ) -> Result<String> {
        let nt = self.get_notetype(ntid)?.or_not_found(ntid)?;
        let ordinal = if matches!(nt.config.kind(), NotetypeKind::Cloze) {
            0
        } else {
            card_ordinal
        };
        Ok(get_aux_notetype_config_key(
            ntid,
            &format!("{key}_{ordinal}"),
        ))
    }
}

impl NotetypeConfigKey {
    fn for_notetype(self, ntid: NotetypeId) -> String {
        get_aux_notetype_config_key(ntid, <&'static str>::from(self))
    }
}

impl Collection {
    #[allow(dead_code)]
    pub(crate) fn get_current_notetype_id(&self) -> Option<NotetypeId> {
        self.get_config_optional(ConfigKey::CurrentNotetypeId)
    }

    pub(crate) fn set_current_notetype_id(&mut self, ntid: NotetypeId) -> Result<()> {
        self.set_config(ConfigKey::CurrentNotetypeId, &ntid)
            .map(|_| ())
    }

    pub(crate) fn clear_aux_config_for_notetype(&mut self, ntid: NotetypeId) -> Result<()> {
        self.remove_config_prefix(&get_aux_notetype_config_key(ntid, ""))
    }

    pub(crate) fn get_last_deck_added_to_for_notetype(&self, id: NotetypeId) -> Option<DeckId> {
        let key = NotetypeConfigKey::LastDeckAddedTo.for_notetype(id);
        self.get_config_optional(key.as_str())
    }

    pub(crate) fn set_last_deck_for_notetype(&mut self, id: NotetypeId, did: DeckId) -> Result<()> {
        let key = NotetypeConfigKey::LastDeckAddedTo.for_notetype(id);
        self.set_config(key.as_str(), &did).map(|_| ())
    }
}

pub fn get_aux_notetype_config_key(ntid: NotetypeId, key: &str) -> String {
    format!("_nt_{ntid}_{key}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aux_config_key_format() {
        let key = get_aux_notetype_config_key(NotetypeId(123), "myKey");
        assert_eq!(key, "_nt_123_myKey");
    }

    #[test]
    fn aux_config_key_empty_suffix() {
        let key = get_aux_notetype_config_key(NotetypeId(42), "");
        assert_eq!(key, "_nt_42_");
    }

    #[test]
    fn aux_config_key_zero_id() {
        let key = get_aux_notetype_config_key(NotetypeId(0), "test");
        assert_eq!(key, "_nt_0_test");
    }

    #[test]
    fn notetype_config_key_for_notetype() {
        let key = NotetypeConfigKey::LastDeckAddedTo.for_notetype(NotetypeId(456));
        assert_eq!(key, "_nt_456_lastDeck");
    }
}
