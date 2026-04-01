// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum IntervalKind {
    InSecs(u32),
    InDays(u32),
}

impl IntervalKind {
    /// Convert seconds-based intervals that pass the day barrier into days.
    pub(crate) fn maybe_as_days(self, secs_until_rollover: u32) -> Self {
        match self {
            IntervalKind::InSecs(secs) => {
                if secs >= secs_until_rollover {
                    IntervalKind::InDays(((secs - secs_until_rollover) / 86_400) + 1)
                } else {
                    IntervalKind::InSecs(secs)
                }
            }
            other => other,
        }
    }

    pub(crate) fn as_seconds(self) -> u32 {
        match self {
            IntervalKind::InSecs(secs) => secs,
            IntervalKind::InDays(days) => days.saturating_mul(86_400),
        }
    }

    pub(crate) fn as_revlog_interval(self) -> i32 {
        match self {
            IntervalKind::InDays(days) => days as i32,
            IntervalKind::InSecs(secs) => -i32::try_from(secs).unwrap_or(i32::MAX),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maybe_as_days_stays_in_secs_when_below_rollover() {
        let kind = IntervalKind::InSecs(3600);
        assert_eq!(kind.maybe_as_days(7200), IntervalKind::InSecs(3600));
    }

    #[test]
    fn maybe_as_days_converts_at_rollover_boundary() {
        let kind = IntervalKind::InSecs(7200);
        assert_eq!(kind.maybe_as_days(7200), IntervalKind::InDays(1));
    }

    #[test]
    fn maybe_as_days_converts_past_rollover() {
        // 2 days past rollover
        let kind = IntervalKind::InSecs(7200 + 86_400 * 2);
        assert_eq!(kind.maybe_as_days(7200), IntervalKind::InDays(3));
    }

    #[test]
    fn maybe_as_days_preserves_in_days() {
        let kind = IntervalKind::InDays(5);
        assert_eq!(kind.maybe_as_days(3600), IntervalKind::InDays(5));
    }

    #[test]
    fn as_seconds_from_secs() {
        assert_eq!(IntervalKind::InSecs(600).as_seconds(), 600);
    }

    #[test]
    fn as_seconds_from_days() {
        assert_eq!(IntervalKind::InDays(1).as_seconds(), 86_400);
        assert_eq!(IntervalKind::InDays(7).as_seconds(), 604_800);
    }

    #[test]
    fn as_seconds_from_zero_days() {
        assert_eq!(IntervalKind::InDays(0).as_seconds(), 0);
    }

    #[test]
    fn as_revlog_interval_days() {
        assert_eq!(IntervalKind::InDays(10).as_revlog_interval(), 10);
        assert_eq!(IntervalKind::InDays(0).as_revlog_interval(), 0);
    }

    #[test]
    fn as_revlog_interval_secs_is_negative() {
        assert_eq!(IntervalKind::InSecs(600).as_revlog_interval(), -600);
        assert_eq!(IntervalKind::InSecs(0).as_revlog_interval(), 0);
    }

    #[test]
    fn as_revlog_interval_large_secs() {
        // u32::MAX can't fit in i32, so try_from fails → unwrap_or(i32::MAX) → negated
        assert_eq!(
            IntervalKind::InSecs(u32::MAX).as_revlog_interval(),
            -i32::MAX
        );
    }
}
