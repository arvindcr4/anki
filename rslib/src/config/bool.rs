// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use strum::IntoStaticStr;

use crate::prelude::*;

#[derive(Debug, Clone, Copy, IntoStaticStr)]
#[strum(serialize_all = "camelCase")]
pub enum BoolKey {
    ApplyAllParentLimits,
    BrowserTableShowNotesMode,
    CardCountsSeparateInactive,
    CollapseCardState,
    CollapseDecks,
    CollapseFlags,
    CollapseNotetypes,
    CollapseSavedSearches,
    CollapseTags,
    CollapseToday,
    FutureDueShowBacklog,
    HideAudioPlayButtons,
    IgnoreAccentsInSearch,
    InterruptAudioWhenAnswering,
    NewCardsIgnoreReviewLimit,
    PasteImagesAsPng,
    PasteStripsFormatting,
    RenderLatex,
    PreviewBothSides,
    RestorePositionBrowser,
    RestorePositionReviewer,
    ResetCountsBrowser,
    ResetCountsReviewer,
    RandomOrderReposition,
    Sched2021,
    ShiftPositionOfExistingCards,
    MergeNotetypes,
    WithScheduling,
    WithDeckConfigs,
    Fsrs,
    FsrsHealthCheck,
    FsrsLegacyEvaluate,
    LoadBalancerEnabled,
    FsrsShortTermWithStepsEnabled,
    #[strum(to_string = "normalize_note_text")]
    NormalizeNoteText,
    #[strum(to_string = "dayLearnFirst")]
    ShowDayLearningCardsFirst,
    #[strum(to_string = "estTimes")]
    ShowIntervalsAboveAnswerButtons,
    #[strum(to_string = "dueCounts")]
    ShowRemainingDueCountsInStudy,
    #[strum(to_string = "addToCur")]
    AddingDefaultsToCurrentDeck,
}

impl Collection {
    pub fn get_config_bool(&self, key: BoolKey) -> bool {
        match key {
            // some keys default to true
            BoolKey::InterruptAudioWhenAnswering
            | BoolKey::ShowIntervalsAboveAnswerButtons
            | BoolKey::AddingDefaultsToCurrentDeck
            | BoolKey::FutureDueShowBacklog
            | BoolKey::ShowRemainingDueCountsInStudy
            | BoolKey::CardCountsSeparateInactive
            | BoolKey::RestorePositionBrowser
            | BoolKey::RestorePositionReviewer
            | BoolKey::LoadBalancerEnabled
            | BoolKey::FsrsHealthCheck
            | BoolKey::NormalizeNoteText => self.get_config_optional(key).unwrap_or(true),

            // other options default to false
            other => self.get_config_default(other),
        }
    }

    pub fn set_config_bool(
        &mut self,
        key: BoolKey,
        value: bool,
        undoable: bool,
    ) -> Result<OpOutput<()>> {
        let op = if undoable {
            Op::UpdateConfig
        } else {
            Op::SkipUndo
        };
        self.transact(op, |col| {
            col.set_config(key, &value)?;
            Ok(())
        })
    }
}

impl Collection {
    pub(crate) fn set_config_bool_inner(&mut self, key: BoolKey, value: bool) -> Result<bool> {
        self.set_config(key, &value)
    }
}

#[cfg(test)]
mod tests {
    use crate::prelude::*;

    use super::*;

    #[test]
    fn bool_key_defaults_true() {
        let col = Collection::new();
        // these should default to true
        assert!(col.get_config_bool(BoolKey::InterruptAudioWhenAnswering));
        assert!(col.get_config_bool(BoolKey::ShowIntervalsAboveAnswerButtons));
        assert!(col.get_config_bool(BoolKey::AddingDefaultsToCurrentDeck));
        assert!(col.get_config_bool(BoolKey::FutureDueShowBacklog));
        assert!(col.get_config_bool(BoolKey::NormalizeNoteText));
    }

    #[test]
    fn bool_key_defaults_false() {
        let col = Collection::new();
        assert!(!col.get_config_bool(BoolKey::Fsrs));
        assert!(!col.get_config_bool(BoolKey::PasteImagesAsPng));
        assert!(!col.get_config_bool(BoolKey::HideAudioPlayButtons));
        assert!(!col.get_config_bool(BoolKey::PreviewBothSides));
    }

    #[test]
    fn bool_key_set_and_get() {
        let mut col = Collection::new();
        assert!(!col.get_config_bool(BoolKey::Fsrs));
        col.set_config_bool_inner(BoolKey::Fsrs, true).unwrap();
        assert!(col.get_config_bool(BoolKey::Fsrs));
        col.set_config_bool_inner(BoolKey::Fsrs, false).unwrap();
        assert!(!col.get_config_bool(BoolKey::Fsrs));
    }

    #[test]
    fn bool_key_string_serialization() {
        // BoolKey variants should serialize to camelCase strings via strum
        let key: &str = BoolKey::Fsrs.into();
        assert_eq!(key, "fsrs");
        let key: &str = BoolKey::PasteImagesAsPng.into();
        assert_eq!(key, "pasteImagesAsPng");
    }

    #[test]
    fn bool_key_custom_strum_serialization() {
        let key: &str = BoolKey::NormalizeNoteText.into();
        assert_eq!(key, "normalize_note_text");
        let key: &str = BoolKey::ShowDayLearningCardsFirst.into();
        assert_eq!(key, "dayLearnFirst");
    }
}
