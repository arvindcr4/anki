// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use crate::error::AnkiError;
use crate::invalid_input;

// Roll our own implementation until this becomes stable
// https://github.com/rust-lang/rust/issues/94047
#[allow(unused)]
pub(crate) trait TryCollect: ExactSizeIterator {
    fn try_collect<const N: usize>(self) -> Result<[Self::Item; N], AnkiError>
    where
        // Self: Sized,
        Self::Item: Copy + Default;
}

impl<I, T> TryCollect for I
where
    I: ExactSizeIterator<Item = T>,
    T: Copy + Default,
{
    fn try_collect<const N: usize>(self) -> Result<[T; N], AnkiError> {
        if self.len() != N {
            invalid_input!("expected {N}; got {}", self.len());
        }

        let mut result = [T::default(); N];
        for (index, value) in self.enumerate() {
            result[index] = value;
        }

        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn try_collect_exact_match() {
        let v = vec![1, 2, 3];
        let result: [i32; 3] = v.into_iter().try_collect().unwrap();
        assert_eq!(result, [1, 2, 3]);
    }

    #[test]
    fn try_collect_single_element() {
        let v = vec![42];
        let result: [i32; 1] = v.into_iter().try_collect().unwrap();
        assert_eq!(result, [42]);
    }

    #[test]
    fn try_collect_wrong_size_too_few() {
        let v = vec![1, 2];
        let result: Result<[i32; 3], AnkiError> = v.into_iter().try_collect();
        assert!(result.is_err());
    }

    #[test]
    fn try_collect_wrong_size_too_many() {
        let v = vec![1, 2, 3, 4];
        let result: Result<[i32; 3], AnkiError> = v.into_iter().try_collect();
        assert!(result.is_err());
    }

    #[test]
    fn try_collect_empty_to_zero() {
        let v: Vec<i32> = vec![];
        let result: [i32; 0] = v.into_iter().try_collect().unwrap();
        let expected: [i32; 0] = [];
        assert_eq!(result, expected);
    }

    #[test]
    fn try_collect_with_floats() {
        let v = vec![1.0_f32, 2.5, 3.7];
        let result: [f32; 3] = v.into_iter().try_collect().unwrap();
        assert_eq!(result, [1.0, 2.5, 3.7]);
    }
}
