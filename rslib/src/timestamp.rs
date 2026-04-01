// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::time;

use chrono::prelude::*;

use crate::define_newtype;
use crate::prelude::*;

define_newtype!(TimestampSecs, i64);
define_newtype!(TimestampMillis, i64);

impl TimestampSecs {
    pub fn now() -> Self {
        Self(elapsed().as_secs() as i64)
    }

    pub fn zero() -> Self {
        Self(0)
    }

    pub fn elapsed_secs_since(self, other: TimestampSecs) -> i64 {
        self.0 - other.0
    }

    pub fn elapsed_secs(self) -> u64 {
        (Self::now().0 - self.0).max(0) as u64
    }

    pub fn elapsed_days_since(self, other: TimestampSecs) -> u64 {
        (self.0 - other.0).max(0) as u64 / 86_400
    }

    pub fn as_millis(self) -> TimestampMillis {
        TimestampMillis(self.0 * 1000)
    }

    pub(crate) fn local_datetime(self) -> Result<DateTime<Local>> {
        Local
            .timestamp_opt(self.0, 0)
            .latest()
            .or_invalid("invalid timestamp")
    }

    /// YYYY-mm-dd
    pub(crate) fn date_string(self) -> String {
        self.local_datetime()
            .map(|dt| dt.format("%Y-%m-%d").to_string())
            .unwrap_or_else(|_err| "invalid date".to_string())
    }

    /// HH-MM
    pub(crate) fn time_string(self) -> String {
        self.local_datetime()
            .map(|dt| dt.format("%H:%M").to_string())
            .unwrap_or_else(|_err| "invalid date".to_string())
    }

    pub(crate) fn date_and_time_string(self) -> String {
        format!("{} @ {}", self.date_string(), self.time_string())
    }

    pub fn local_utc_offset(self) -> Result<FixedOffset> {
        Ok(*self.local_datetime()?.offset())
    }

    pub fn datetime(self, utc_offset: FixedOffset) -> Result<DateTime<FixedOffset>> {
        utc_offset
            .timestamp_opt(self.0, 0)
            .latest()
            .or_invalid("invalid timestamp")
    }

    pub fn adding_secs(self, secs: i64) -> Self {
        TimestampSecs(self.0 + secs)
    }
}

impl TimestampMillis {
    pub fn now() -> Self {
        Self(elapsed().as_millis() as i64)
    }

    pub fn zero() -> Self {
        Self(0)
    }

    pub fn as_secs(self) -> TimestampSecs {
        TimestampSecs(self.0 / 1000)
    }

    pub fn adding_secs(self, secs: i64) -> Self {
        Self(self.0 + secs * 1000)
    }

    pub fn elapsed_millis(self) -> u64 {
        (Self::now().0 - self.0).max(0) as u64
    }
}

fn elapsed() -> time::Duration {
    if *crate::PYTHON_UNIT_TESTS {
        // shift clock around rollover time to accommodate Python tests that make bad
        // assumptions. we should update the tests in the future and remove this
        // hack.
        let mut elap = time::SystemTime::now()
            .duration_since(time::SystemTime::UNIX_EPOCH)
            .unwrap();
        let now = Local::now();
        if now.hour() >= 2 && now.hour() < 4 {
            elap -= time::Duration::from_secs(60 * 60 * 2);
        }
        elap
    } else {
        time::SystemTime::now()
            .duration_since(time::SystemTime::UNIX_EPOCH)
            .unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timestamp_secs_zero() {
        assert_eq!(TimestampSecs::zero().0, 0);
    }

    #[test]
    fn elapsed_secs_since_positive() {
        let a = TimestampSecs(1000);
        let b = TimestampSecs(600);
        assert_eq!(a.elapsed_secs_since(b), 400);
    }

    #[test]
    fn elapsed_secs_since_negative() {
        let a = TimestampSecs(500);
        let b = TimestampSecs(800);
        assert_eq!(a.elapsed_secs_since(b), -300);
    }

    #[test]
    fn elapsed_secs_since_same() {
        let a = TimestampSecs(1000);
        assert_eq!(a.elapsed_secs_since(a), 0);
    }

    #[test]
    fn elapsed_days_since() {
        let a = TimestampSecs(86_400 * 10);
        let b = TimestampSecs(86_400 * 3);
        assert_eq!(a.elapsed_days_since(b), 7);
    }

    #[test]
    fn elapsed_days_since_partial_day() {
        let a = TimestampSecs(86_400 * 3 + 43_200); // 3.5 days
        let b = TimestampSecs(0);
        assert_eq!(a.elapsed_days_since(b), 3); // floors
    }

    #[test]
    fn elapsed_days_since_negative_clamped() {
        let a = TimestampSecs(0);
        let b = TimestampSecs(86_400);
        assert_eq!(a.elapsed_days_since(b), 0); // .max(0)
    }

    #[test]
    fn as_millis() {
        let ts = TimestampSecs(1_700_000);
        assert_eq!(ts.as_millis(), TimestampMillis(1_700_000_000));
    }

    #[test]
    fn as_millis_zero() {
        assert_eq!(TimestampSecs(0).as_millis(), TimestampMillis(0));
    }

    #[test]
    fn adding_secs() {
        let ts = TimestampSecs(1000);
        assert_eq!(ts.adding_secs(500), TimestampSecs(1500));
        assert_eq!(ts.adding_secs(-200), TimestampSecs(800));
        assert_eq!(ts.adding_secs(0), TimestampSecs(1000));
    }

    #[test]
    fn timestamp_millis_zero() {
        assert_eq!(TimestampMillis::zero().0, 0);
    }

    #[test]
    fn millis_as_secs() {
        assert_eq!(
            TimestampMillis(1_700_000_000).as_secs(),
            TimestampSecs(1_700_000)
        );
    }

    #[test]
    fn millis_as_secs_truncates() {
        assert_eq!(
            TimestampMillis(1_700_000_999).as_secs(),
            TimestampSecs(1_700_000)
        );
    }

    #[test]
    fn millis_adding_secs() {
        let ts = TimestampMillis(5000);
        assert_eq!(ts.adding_secs(3), TimestampMillis(8000));
        assert_eq!(ts.adding_secs(-1), TimestampMillis(4000));
    }

    #[test]
    fn date_string_valid() {
        // Use a known timestamp (2023-01-15 in UTC)
        let ts = TimestampSecs(1673740800);
        let s = ts.date_string();
        // Should produce a valid date format YYYY-mm-dd
        assert_eq!(s.len(), 10);
        assert!(s.contains('-'));
    }

    #[test]
    fn date_and_time_string_format() {
        let ts = TimestampSecs(1673740800);
        let s = ts.date_and_time_string();
        assert!(s.contains(" @ "));
    }
}
