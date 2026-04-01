// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use fsrs::FSRSError;

use crate::error::AnkiError;
use crate::error::InvalidInputError;

impl From<FSRSError> for AnkiError {
    fn from(err: FSRSError) -> Self {
        match err {
            FSRSError::NotEnoughData => AnkiError::FsrsInsufficientData,
            FSRSError::OptimalNotFound => AnkiError::FsrsUnableToDetermineDesiredRetention,
            FSRSError::Interrupted => AnkiError::Interrupted,
            FSRSError::InvalidParameters => AnkiError::FsrsParamsInvalid,
            FSRSError::InvalidInput => AnkiError::FsrsParamsInvalid,
            FSRSError::InvalidDeckSize => AnkiError::InvalidInput {
                source: InvalidInputError {
                    message: "no cards to simulate".to_string(),
                    source: None,
                    backtrace: None,
                },
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn not_enough_data_maps_correctly() {
        let err: AnkiError = FSRSError::NotEnoughData.into();
        assert!(matches!(err, AnkiError::FsrsInsufficientData));
    }

    #[test]
    fn optimal_not_found_maps_correctly() {
        let err: AnkiError = FSRSError::OptimalNotFound.into();
        assert!(matches!(
            err,
            AnkiError::FsrsUnableToDetermineDesiredRetention
        ));
    }

    #[test]
    fn interrupted_maps_correctly() {
        let err: AnkiError = FSRSError::Interrupted.into();
        assert!(matches!(err, AnkiError::Interrupted));
    }

    #[test]
    fn invalid_parameters_maps_correctly() {
        let err: AnkiError = FSRSError::InvalidParameters.into();
        assert!(matches!(err, AnkiError::FsrsParamsInvalid));
    }

    #[test]
    fn invalid_input_maps_correctly() {
        let err: AnkiError = FSRSError::InvalidInput.into();
        assert!(matches!(err, AnkiError::FsrsParamsInvalid));
    }

    #[test]
    fn invalid_deck_size_maps_to_invalid_input() {
        let err: AnkiError = FSRSError::InvalidDeckSize.into();
        match err {
            AnkiError::InvalidInput { source } => {
                assert_eq!(source.message, "no cards to simulate");
            }
            other => panic!("expected InvalidInput, got {:?}", other),
        }
    }
}
