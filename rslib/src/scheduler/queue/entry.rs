// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use super::LearningQueueEntry;
use super::MainQueueEntry;
use super::MainQueueEntryKind;
use crate::card::CardQueue;
use crate::prelude::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum QueueEntry {
    IntradayLearning(LearningQueueEntry),
    Main(MainQueueEntry),
}

impl QueueEntry {
    pub fn card_id(&self) -> CardId {
        match self {
            QueueEntry::IntradayLearning(e) => e.id,
            QueueEntry::Main(e) => e.id,
        }
    }

    pub fn mtime(&self) -> TimestampSecs {
        match self {
            QueueEntry::IntradayLearning(e) => e.mtime,
            QueueEntry::Main(e) => e.mtime,
        }
    }

    pub fn kind(&self) -> QueueEntryKind {
        match self {
            QueueEntry::IntradayLearning(_e) => QueueEntryKind::Learning,
            QueueEntry::Main(e) => match e.kind {
                MainQueueEntryKind::New => QueueEntryKind::New,
                MainQueueEntryKind::Review => QueueEntryKind::Review,
                MainQueueEntryKind::InterdayLearning => QueueEntryKind::Learning,
            },
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum QueueEntryKind {
    New,
    Learning,
    Review,
}

impl From<&Card> for QueueEntry {
    fn from(card: &Card) -> Self {
        let kind = match card.queue {
            CardQueue::Learn | CardQueue::PreviewRepeat => {
                return QueueEntry::IntradayLearning(LearningQueueEntry {
                    due: TimestampSecs(card.due as i64),
                    id: card.id,
                    mtime: card.mtime,
                });
            }
            CardQueue::New => MainQueueEntryKind::New,
            CardQueue::Review | CardQueue::DayLearn => MainQueueEntryKind::Review,
            CardQueue::Suspended | CardQueue::SchedBuried | CardQueue::UserBuried => {
                unreachable!()
            }
        };
        QueueEntry::Main(MainQueueEntry {
            id: card.id,
            mtime: card.mtime,
            kind,
        })
    }
}

impl From<LearningQueueEntry> for QueueEntry {
    fn from(e: LearningQueueEntry) -> Self {
        Self::IntradayLearning(e)
    }
}

impl From<MainQueueEntry> for QueueEntry {
    fn from(e: MainQueueEntry) -> Self {
        Self::Main(e)
    }
}

impl From<&LearningQueueEntry> for QueueEntry {
    fn from(e: &LearningQueueEntry) -> Self {
        Self::IntradayLearning(*e)
    }
}

impl From<&MainQueueEntry> for QueueEntry {
    fn from(e: &MainQueueEntry) -> Self {
        Self::Main(*e)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn learning_entry() -> LearningQueueEntry {
        LearningQueueEntry {
            due: TimestampSecs(1000),
            id: CardId(42),
            mtime: TimestampSecs(900),
        }
    }

    fn main_entry(kind: MainQueueEntryKind) -> MainQueueEntry {
        MainQueueEntry {
            id: CardId(99),
            mtime: TimestampSecs(800),
            kind,
        }
    }

    #[test]
    fn card_id_learning() {
        let entry = QueueEntry::IntradayLearning(learning_entry());
        assert_eq!(entry.card_id(), CardId(42));
    }

    #[test]
    fn card_id_main() {
        let entry = QueueEntry::Main(main_entry(MainQueueEntryKind::New));
        assert_eq!(entry.card_id(), CardId(99));
    }

    #[test]
    fn mtime_learning() {
        let entry = QueueEntry::IntradayLearning(learning_entry());
        assert_eq!(entry.mtime(), TimestampSecs(900));
    }

    #[test]
    fn mtime_main() {
        let entry = QueueEntry::Main(main_entry(MainQueueEntryKind::Review));
        assert_eq!(entry.mtime(), TimestampSecs(800));
    }

    #[test]
    fn kind_intraday_learning() {
        let entry = QueueEntry::IntradayLearning(learning_entry());
        assert_eq!(entry.kind(), QueueEntryKind::Learning);
    }

    #[test]
    fn kind_main_new() {
        let entry = QueueEntry::Main(main_entry(MainQueueEntryKind::New));
        assert_eq!(entry.kind(), QueueEntryKind::New);
    }

    #[test]
    fn kind_main_review() {
        let entry = QueueEntry::Main(main_entry(MainQueueEntryKind::Review));
        assert_eq!(entry.kind(), QueueEntryKind::Review);
    }

    #[test]
    fn kind_main_interday_learning() {
        let entry = QueueEntry::Main(main_entry(MainQueueEntryKind::InterdayLearning));
        assert_eq!(entry.kind(), QueueEntryKind::Learning);
    }

    #[test]
    fn from_learning_entry() {
        let le = learning_entry();
        let entry: QueueEntry = le.into();
        assert!(matches!(entry, QueueEntry::IntradayLearning(_)));
    }

    #[test]
    fn from_main_entry() {
        let me = main_entry(MainQueueEntryKind::New);
        let entry: QueueEntry = me.into();
        assert!(matches!(entry, QueueEntry::Main(_)));
    }

    #[test]
    fn from_ref_learning_entry() {
        let le = learning_entry();
        let entry: QueueEntry = (&le).into();
        assert_eq!(entry.card_id(), CardId(42));
    }

    #[test]
    fn from_ref_main_entry() {
        let me = main_entry(MainQueueEntryKind::Review);
        let entry: QueueEntry = (&me).into();
        assert_eq!(entry.card_id(), CardId(99));
    }
}
