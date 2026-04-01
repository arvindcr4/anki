// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

#[macro_export]
macro_rules! define_newtype {
    ( $name:ident, $type:ident ) => {
        #[repr(transparent)]
        #[derive(
            Debug,
            Default,
            Clone,
            Copy,
            PartialEq,
            Eq,
            PartialOrd,
            Ord,
            Hash,
            serde::Serialize,
            serde::Deserialize,
        )]
        pub struct $name(pub $type);

        impl std::fmt::Display for $name {
            fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                self.0.fmt(f)
            }
        }

        impl std::str::FromStr for $name {
            type Err = std::num::ParseIntError;
            fn from_str(s: &std::primitive::str) -> std::result::Result<Self, Self::Err> {
                $type::from_str(s).map($name)
            }
        }

        impl rusqlite::types::FromSql for $name {
            fn column_result(
                value: rusqlite::types::ValueRef<'_>,
            ) -> std::result::Result<Self, rusqlite::types::FromSqlError> {
                if let rusqlite::types::ValueRef::Integer(i) = value {
                    Ok(Self(i as $type))
                } else {
                    Err(rusqlite::types::FromSqlError::InvalidType)
                }
            }
        }

        impl rusqlite::ToSql for $name {
            fn to_sql(&self) -> ::rusqlite::Result<rusqlite::types::ToSqlOutput<'_>> {
                Ok(rusqlite::types::ToSqlOutput::Owned(
                    rusqlite::types::Value::Integer(self.0 as i64),
                ))
            }
        }

        impl From<$type> for $name {
            fn from(t: $type) -> $name {
                $name(t)
            }
        }

        impl From<$name> for $type {
            fn from(n: $name) -> $type {
                n.0
            }
        }
    };
}

define_newtype!(Usn, i32);

pub(crate) trait IntoNewtypeVec {
    fn into_newtype<F, T>(self, func: F) -> Vec<T>
    where
        F: FnMut(i64) -> T;
}

impl IntoNewtypeVec for Vec<i64> {
    fn into_newtype<F, T>(self, func: F) -> Vec<T>
    where
        F: FnMut(i64) -> T,
    {
        self.into_iter().map(func).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::prelude::*;

    #[test]
    fn usn_default_is_zero() {
        assert_eq!(Usn::default(), Usn(0));
    }

    #[test]
    fn usn_display() {
        assert_eq!(format!("{}", Usn(42)), "42");
        assert_eq!(format!("{}", Usn(-1)), "-1");
    }

    #[test]
    fn usn_from_str() {
        assert_eq!("42".parse::<Usn>().unwrap(), Usn(42));
        assert_eq!("-5".parse::<Usn>().unwrap(), Usn(-5));
        assert!("abc".parse::<Usn>().is_err());
    }

    #[test]
    fn usn_from_i32() {
        let usn: Usn = 99.into();
        assert_eq!(usn, Usn(99));
    }

    #[test]
    fn usn_into_i32() {
        let val: i32 = Usn(77).into();
        assert_eq!(val, 77);
    }

    #[test]
    fn usn_ordering() {
        assert!(Usn(1) < Usn(2));
        assert!(Usn(-1) < Usn(0));
        assert_eq!(Usn(5), Usn(5));
    }

    #[test]
    fn card_id_newtype() {
        let id = CardId(12345);
        assert_eq!(format!("{}", id), "12345");
        assert_eq!("999".parse::<CardId>().unwrap(), CardId(999));
    }

    #[test]
    fn deck_id_newtype() {
        let id: DeckId = 42.into();
        assert_eq!(id, DeckId(42));
        let val: i64 = id.into();
        assert_eq!(val, 42);
    }

    #[test]
    fn note_id_newtype() {
        let id = NoteId(0);
        assert_eq!(id, NoteId::default());
    }

    #[test]
    fn into_newtype_vec() {
        let ids: Vec<CardId> = vec![1_i64, 2, 3].into_newtype(CardId);
        assert_eq!(ids, vec![CardId(1), CardId(2), CardId(3)]);
    }

    #[test]
    fn into_newtype_vec_empty() {
        let ids: Vec<CardId> = vec![].into_newtype(CardId);
        assert!(ids.is_empty());
    }
}
