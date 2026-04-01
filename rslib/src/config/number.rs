// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use strum::IntoStaticStr;

use crate::prelude::*;

#[derive(Debug, Clone, Copy, IntoStaticStr)]
#[strum(serialize_all = "camelCase")]
pub enum I32ConfigKey {
    CsvDuplicateResolution,
    MatchScope,
    LastFsrsOptimize,
}

impl Collection {
    pub fn get_config_i32(&self, key: I32ConfigKey) -> i32 {
        #[allow(clippy::match_single_binding)]
        self.get_config_optional(key).unwrap_or(match key {
            _other => 0,
        })
    }
}

impl Collection {
    pub(crate) fn set_config_i32_inner(&mut self, key: I32ConfigKey, value: i32) -> Result<bool> {
        self.set_config(key, &value)
    }
}

#[cfg(test)]
mod tests {
    use crate::prelude::*;

    use super::*;

    #[test]
    fn i32_key_defaults_to_zero() {
        let col = Collection::new();
        assert_eq!(col.get_config_i32(I32ConfigKey::CsvDuplicateResolution), 0);
        assert_eq!(col.get_config_i32(I32ConfigKey::MatchScope), 0);
        assert_eq!(col.get_config_i32(I32ConfigKey::LastFsrsOptimize), 0);
    }

    #[test]
    fn i32_key_set_and_get() {
        let mut col = Collection::new();
        col.set_config_i32_inner(I32ConfigKey::CsvDuplicateResolution, 2)
            .unwrap();
        assert_eq!(col.get_config_i32(I32ConfigKey::CsvDuplicateResolution), 2);
    }

    #[test]
    fn i32_key_negative_value() {
        let mut col = Collection::new();
        col.set_config_i32_inner(I32ConfigKey::LastFsrsOptimize, -100)
            .unwrap();
        assert_eq!(col.get_config_i32(I32ConfigKey::LastFsrsOptimize), -100);
    }

    #[test]
    fn i32_key_strum_serialization() {
        let key: &str = I32ConfigKey::CsvDuplicateResolution.into();
        assert_eq!(key, "csvDuplicateResolution");
        let key: &str = I32ConfigKey::MatchScope.into();
        assert_eq!(key, "matchScope");
    }

    #[test]
    fn i32_key_overwrite() {
        let mut col = Collection::new();
        col.set_config_i32_inner(I32ConfigKey::MatchScope, 1)
            .unwrap();
        col.set_config_i32_inner(I32ConfigKey::MatchScope, 3)
            .unwrap();
        assert_eq!(col.get_config_i32(I32ConfigKey::MatchScope), 3);
    }

    #[test]
    fn i32_key_zero_value() {
        let mut col = Collection::new();
        col.set_config_i32_inner(I32ConfigKey::CsvDuplicateResolution, 5)
            .unwrap();
        col.set_config_i32_inner(I32ConfigKey::CsvDuplicateResolution, 0)
            .unwrap();
        assert_eq!(col.get_config_i32(I32ConfigKey::CsvDuplicateResolution), 0);
    }

    #[test]
    fn i32_key_large_value() {
        let mut col = Collection::new();
        col.set_config_i32_inner(I32ConfigKey::LastFsrsOptimize, i32::MAX)
            .unwrap();
        assert_eq!(
            col.get_config_i32(I32ConfigKey::LastFsrsOptimize),
            i32::MAX
        );
    }

    #[test]
    fn i32_key_min_value() {
        let mut col = Collection::new();
        col.set_config_i32_inner(I32ConfigKey::LastFsrsOptimize, i32::MIN)
            .unwrap();
        assert_eq!(
            col.get_config_i32(I32ConfigKey::LastFsrsOptimize),
            i32::MIN
        );
    }
}
