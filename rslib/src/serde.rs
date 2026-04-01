// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use serde::Deserialize as DeTrait;
use serde::Deserializer;
pub(crate) use serde_aux::field_attributes::deserialize_bool_from_anything;
pub(crate) use serde_aux::field_attributes::deserialize_number_from_string;
use serde_json::Value;

use crate::timestamp::TimestampSecs;

/// Note: if you wish to cover the case where a field is missing, make sure you
/// also use the `serde(default)` flag.
pub(crate) fn default_on_invalid<'de, T, D>(deserializer: D) -> Result<T, D::Error>
where
    T: Default + DeTrait<'de>,
    D: Deserializer<'de>,
{
    let v: Value = DeTrait::deserialize(deserializer)?;
    Ok(T::deserialize(v).unwrap_or_default())
}

pub(crate) fn is_default<T: Default + PartialEq>(t: &T) -> bool {
    *t == Default::default()
}

pub(crate) fn deserialize_int_from_number<'de, T, D>(deserializer: D) -> Result<T, D::Error>
where
    D: Deserializer<'de>,
    T: serde::Deserialize<'de> + FromI64,
{
    #[derive(DeTrait)]
    #[serde(untagged)]
    enum IntOrFloat {
        Int(i64),
        Float(f64),
    }

    match IntOrFloat::deserialize(deserializer)? {
        IntOrFloat::Float(f) => Ok(T::from_i64(f as i64)),
        IntOrFloat::Int(i) => Ok(T::from_i64(i)),
    }
}

// It may be possible to use the num_traits crate instead in the future.
pub(crate) trait FromI64 {
    fn from_i64(val: i64) -> Self;
}

impl FromI64 for i32 {
    fn from_i64(val: i64) -> Self {
        val as Self
    }
}

impl FromI64 for u32 {
    fn from_i64(val: i64) -> Self {
        val.max(0) as Self
    }
}

impl FromI64 for i64 {
    fn from_i64(val: i64) -> Self {
        val
    }
}

impl FromI64 for TimestampSecs {
    fn from_i64(val: i64) -> Self {
        TimestampSecs(val)
    }
}

#[cfg(test)]
mod test {
    use serde::Deserialize;

    use super::*;

    #[derive(Deserialize, Debug, PartialEq, Eq)]
    struct MaybeInvalid {
        #[serde(deserialize_with = "default_on_invalid", default)]
        field: Option<usize>,
    }

    #[test]
    fn invalid_or_missing() {
        assert_eq!(
            serde_json::from_str::<MaybeInvalid>(r#"{"field": 5}"#).unwrap(),
            MaybeInvalid { field: Some(5) }
        );
        assert_eq!(
            serde_json::from_str::<MaybeInvalid>(r#"{"field": "5"}"#).unwrap(),
            MaybeInvalid { field: None }
        );
        assert_eq!(
            serde_json::from_str::<MaybeInvalid>(r#"{"another": 5}"#).unwrap(),
            MaybeInvalid { field: None }
        );
    }

    #[test]
    fn is_default_true() {
        assert!(is_default(&0_i32));
        assert!(is_default(&0_u32));
        assert!(is_default(&false));
        assert!(is_default(&String::new()));
    }

    #[test]
    fn is_default_false() {
        assert!(!is_default(&1_i32));
        assert!(!is_default(&42_u32));
        assert!(!is_default(&true));
        assert!(!is_default(&"hello".to_string()));
    }

    #[test]
    fn from_i64_i32() {
        assert_eq!(i32::from_i64(42), 42_i32);
        assert_eq!(i32::from_i64(-100), -100_i32);
    }

    #[test]
    fn from_i64_u32_clamps_negative() {
        assert_eq!(u32::from_i64(42), 42_u32);
        assert_eq!(u32::from_i64(-5), 0_u32); // clamped to 0
        assert_eq!(u32::from_i64(0), 0_u32);
    }

    #[test]
    fn from_i64_identity() {
        assert_eq!(i64::from_i64(123_456_789), 123_456_789_i64);
        assert_eq!(i64::from_i64(-999), -999_i64);
    }

    #[test]
    fn from_i64_timestamp() {
        let ts = TimestampSecs::from_i64(1_700_000_000);
        assert_eq!(ts, TimestampSecs(1_700_000_000));
    }

    #[test]
    fn deserialize_int_from_float() {
        #[derive(Deserialize, Debug, PartialEq, Eq)]
        struct HasInt {
            #[serde(deserialize_with = "deserialize_int_from_number")]
            val: i32,
        }
        // float value should be truncated to int
        let parsed: HasInt = serde_json::from_str(r#"{"val": 3.7}"#).unwrap();
        assert_eq!(parsed.val, 3);

        // int value should pass through
        let parsed: HasInt = serde_json::from_str(r#"{"val": 42}"#).unwrap();
        assert_eq!(parsed.val, 42);
    }

    #[test]
    fn deserialize_u32_from_negative_float() {
        #[derive(Deserialize, Debug, PartialEq, Eq)]
        struct HasU32 {
            #[serde(deserialize_with = "deserialize_int_from_number")]
            val: u32,
        }
        // negative should clamp to 0
        let parsed: HasU32 = serde_json::from_str(r#"{"val": -5.0}"#).unwrap();
        assert_eq!(parsed.val, 0);
    }
}
