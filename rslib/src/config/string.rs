// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use strum::IntoStaticStr;

use crate::prelude::*;

#[derive(Debug, Clone, Copy, IntoStaticStr)]
#[strum(serialize_all = "camelCase")]
pub enum StringKey {
    SetDueBrowser,
    SetDueReviewer,
    DefaultSearchText,
    CardStateCustomizer,
}

impl Collection {
    pub fn get_config_string(&self, key: StringKey) -> String {
        let default = match key {
            StringKey::SetDueBrowser => "0",
            StringKey::SetDueReviewer => "1",
            _other => "",
        };
        self.get_config_optional(key)
            .unwrap_or_else(|| default.to_string())
    }

    pub fn set_config_string(
        &mut self,
        key: StringKey,
        val: &str,
        undoable: bool,
    ) -> Result<OpOutput<()>> {
        let op = if undoable {
            Op::UpdateConfig
        } else {
            Op::SkipUndo
        };
        self.transact(op, |col| {
            col.set_config_string_inner(key, val)?;
            Ok(())
        })
    }
}

impl Collection {
    pub(crate) fn set_config_string_inner(&mut self, key: StringKey, val: &str) -> Result<bool> {
        self.set_config(key, &val)
    }
}

#[cfg(test)]
mod tests {
    use crate::prelude::*;

    use super::*;

    #[test]
    fn string_key_defaults() {
        let col = Collection::new();
        assert_eq!(col.get_config_string(StringKey::SetDueBrowser), "0");
        assert_eq!(col.get_config_string(StringKey::SetDueReviewer), "1");
        assert_eq!(col.get_config_string(StringKey::DefaultSearchText), "");
        assert_eq!(col.get_config_string(StringKey::CardStateCustomizer), "");
    }

    #[test]
    fn string_key_set_and_get() {
        let mut col = Collection::new();
        col.set_config_string_inner(StringKey::DefaultSearchText, "is:due")
            .unwrap();
        assert_eq!(
            col.get_config_string(StringKey::DefaultSearchText),
            "is:due"
        );
    }

    #[test]
    fn string_key_strum_serialization() {
        let key: &str = StringKey::SetDueBrowser.into();
        assert_eq!(key, "setDueBrowser");
        let key: &str = StringKey::DefaultSearchText.into();
        assert_eq!(key, "defaultSearchText");
    }

    #[test]
    fn string_key_overwrite() {
        let mut col = Collection::new();
        col.set_config_string_inner(StringKey::CardStateCustomizer, "first")
            .unwrap();
        col.set_config_string_inner(StringKey::CardStateCustomizer, "second")
            .unwrap();
        assert_eq!(
            col.get_config_string(StringKey::CardStateCustomizer),
            "second"
        );
    }
}
