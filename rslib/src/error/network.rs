// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use anki_i18n::I18n;
use reqwest::StatusCode;
use snafu::Snafu;

use super::AnkiError;
use crate::sync::collection::sanity::SanityCheckCounts;
use crate::sync::error::HttpError;

#[derive(Debug, PartialEq, Eq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub struct NetworkError {
    pub info: String,
    pub kind: NetworkErrorKind,
}

#[derive(Debug, PartialEq, Eq)]
pub enum NetworkErrorKind {
    Offline,
    Timeout,
    ProxyAuth,
    Other,
}

#[derive(Debug, PartialEq, Eq, Snafu)]
#[snafu(display("{kind:?}: {info}"))]
pub struct SyncError {
    pub info: String,
    pub kind: SyncErrorKind,
}

#[derive(Debug, PartialEq, Eq)]
pub enum SyncErrorKind {
    Conflict,
    ServerError,
    ClientTooOld,
    AuthFailed,
    ServerMessage,
    ClockIncorrect,
    Other,
    ResyncRequired,
    DatabaseCheckRequired,
    SyncNotStarted,
    UploadTooLarge,
    SanityCheckFailed {
        client: Option<SanityCheckCounts>,
        server: Option<SanityCheckCounts>,
    },
}

impl AnkiError {
    pub(crate) fn sync_error(info: impl Into<String>, kind: SyncErrorKind) -> Self {
        AnkiError::SyncError {
            source: SyncError {
                info: info.into(),
                kind,
            },
        }
    }

    pub(crate) fn server_message<S: Into<String>>(msg: S) -> AnkiError {
        AnkiError::sync_error(msg, SyncErrorKind::ServerMessage)
    }
}

impl From<&reqwest::Error> for AnkiError {
    fn from(err: &reqwest::Error) -> Self {
        let url = err.url().map(|url| url.as_str()).unwrap_or("");
        let str_err = format!("{err}");
        // strip url from error to avoid exposing keys
        let info = str_err.replace(url, "");

        if err.is_timeout() {
            AnkiError::NetworkError {
                source: NetworkError {
                    info,
                    kind: NetworkErrorKind::Timeout,
                },
            }
        } else if err.is_status() {
            error_for_status_code(info, err.status().unwrap())
        } else {
            guess_reqwest_error(info)
        }
    }
}

impl From<reqwest::Error> for AnkiError {
    fn from(err: reqwest::Error) -> Self {
        (&err).into()
    }
}

fn error_for_status_code(info: String, code: StatusCode) -> AnkiError {
    use reqwest::StatusCode as S;
    match code {
        S::PROXY_AUTHENTICATION_REQUIRED => AnkiError::NetworkError {
            source: NetworkError {
                info,
                kind: NetworkErrorKind::ProxyAuth,
            },
        },
        S::CONFLICT => AnkiError::SyncError {
            source: SyncError {
                info,
                kind: SyncErrorKind::Conflict,
            },
        },
        S::FORBIDDEN => AnkiError::SyncError {
            source: SyncError {
                info,
                kind: SyncErrorKind::AuthFailed,
            },
        },
        S::NOT_IMPLEMENTED => AnkiError::SyncError {
            source: SyncError {
                info,
                kind: SyncErrorKind::ClientTooOld,
            },
        },
        S::INTERNAL_SERVER_ERROR | S::BAD_GATEWAY | S::GATEWAY_TIMEOUT | S::SERVICE_UNAVAILABLE => {
            AnkiError::SyncError {
                source: SyncError {
                    info,
                    kind: SyncErrorKind::ServerError,
                },
            }
        }
        S::BAD_REQUEST => AnkiError::SyncError {
            source: SyncError {
                info,
                kind: SyncErrorKind::DatabaseCheckRequired,
            },
        },
        _ => AnkiError::NetworkError {
            source: NetworkError {
                info,
                kind: NetworkErrorKind::Other,
            },
        },
    }
}

fn guess_reqwest_error(mut info: String) -> AnkiError {
    if info.contains("dns error: cancelled") {
        return AnkiError::Interrupted;
    }
    let kind = if info.contains("unreachable") || info.contains("dns") {
        NetworkErrorKind::Offline
    } else if info.contains("timed out") {
        NetworkErrorKind::Timeout
    } else {
        if info.contains("invalid type") {
            info = format!(
                "{} {} {}\n\n{}",
                "Please force a one-way sync in the Preferences screen to bring your devices into sync.",
                "Then, please use the Check Database feature, and sync to your other devices.",
                "If problems persist, please post on the support forum.",
                info,
            );
        }

        NetworkErrorKind::Other
    };
    AnkiError::NetworkError {
        source: NetworkError { info, kind },
    }
}

impl From<zip::result::ZipError> for AnkiError {
    fn from(err: zip::result::ZipError) -> Self {
        AnkiError::sync_error(err.to_string(), SyncErrorKind::Other)
    }
}

impl SyncError {
    pub fn message(&self, tr: &I18n) -> String {
        match self.kind {
            SyncErrorKind::ServerMessage => self.info.clone().into(),
            SyncErrorKind::Other => self.info.clone().into(),
            SyncErrorKind::Conflict => tr.sync_conflict(),
            SyncErrorKind::ServerError => tr.sync_server_error(),
            SyncErrorKind::ClientTooOld => tr.sync_client_too_old(),
            SyncErrorKind::AuthFailed => tr.sync_wrong_pass(),
            SyncErrorKind::ResyncRequired => tr.sync_resync_required(),
            SyncErrorKind::ClockIncorrect => tr.sync_clock_off(),
            SyncErrorKind::DatabaseCheckRequired | SyncErrorKind::SanityCheckFailed { .. } => {
                tr.sync_sanity_check_failed()
            }
            SyncErrorKind::SyncNotStarted => "sync not started".into(),
            SyncErrorKind::UploadTooLarge => tr.sync_upload_too_large(&self.info),
        }
        .into()
    }
}

impl NetworkError {
    pub fn message(&self, tr: &I18n) -> String {
        let summary = match self.kind {
            NetworkErrorKind::Offline => tr.network_offline(),
            NetworkErrorKind::Timeout => tr.network_timeout(),
            NetworkErrorKind::ProxyAuth => tr.network_proxy_auth(),
            NetworkErrorKind::Other => tr.network_other(),
        };
        let details = tr.network_details(self.info.as_str());
        format!("{summary}\n\n{details}")
    }
}

// This needs rethinking; we should be attaching error context as errors are
// encountered instead of trying to determine the problem later.
impl From<HttpError> for AnkiError {
    fn from(err: HttpError) -> Self {
        if let Some(reqwest_error) = err
            .source
            .as_ref()
            .and_then(|source| source.downcast_ref::<reqwest::Error>())
        {
            reqwest_error.into()
        } else if err.code == StatusCode::REQUEST_TIMEOUT {
            NetworkError {
                info: String::new(),
                kind: NetworkErrorKind::Timeout,
            }
            .into()
        } else {
            AnkiError::sync_error(format!("{err:?}"), SyncErrorKind::Other)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sync_error_message_server_message() {
        let tr = I18n::template_only();
        let err = SyncError {
            info: "custom server msg".into(),
            kind: SyncErrorKind::ServerMessage,
        };
        assert_eq!(err.message(&tr), "custom server msg");
    }

    #[test]
    fn sync_error_messages_not_empty() {
        let tr = I18n::template_only();
        let errors = vec![
            SyncError { info: "".into(), kind: SyncErrorKind::Conflict },
            SyncError { info: "".into(), kind: SyncErrorKind::ServerError },
            SyncError { info: "".into(), kind: SyncErrorKind::ClientTooOld },
            SyncError { info: "".into(), kind: SyncErrorKind::AuthFailed },
            SyncError { info: "".into(), kind: SyncErrorKind::ResyncRequired },
            SyncError { info: "".into(), kind: SyncErrorKind::ClockIncorrect },
            SyncError { info: "".into(), kind: SyncErrorKind::DatabaseCheckRequired },
            SyncError { info: "".into(), kind: SyncErrorKind::SyncNotStarted },
        ];
        for err in &errors {
            assert!(!err.message(&tr).is_empty());
        }
    }

    #[test]
    fn network_error_message_not_empty() {
        let tr = I18n::template_only();
        let kinds = vec![
            NetworkErrorKind::Offline,
            NetworkErrorKind::Timeout,
            NetworkErrorKind::ProxyAuth,
            NetworkErrorKind::Other,
        ];
        for kind in kinds {
            let err = NetworkError {
                info: "details".into(),
                kind,
            };
            assert!(!err.message(&tr).is_empty());
        }
    }

    #[test]
    fn error_for_status_code_proxy_auth() {
        let err = error_for_status_code("info".into(), StatusCode::PROXY_AUTHENTICATION_REQUIRED);
        assert!(matches!(err, AnkiError::NetworkError { .. }));
    }

    #[test]
    fn error_for_status_code_conflict() {
        let err = error_for_status_code("info".into(), StatusCode::CONFLICT);
        assert!(matches!(err, AnkiError::SyncError { .. }));
    }

    #[test]
    fn error_for_status_code_forbidden() {
        let err = error_for_status_code("info".into(), StatusCode::FORBIDDEN);
        if let AnkiError::SyncError { source } = err {
            assert_eq!(source.kind, SyncErrorKind::AuthFailed);
        } else {
            panic!("expected SyncError");
        }
    }

    #[test]
    fn error_for_status_code_internal_server() {
        let err = error_for_status_code("info".into(), StatusCode::INTERNAL_SERVER_ERROR);
        if let AnkiError::SyncError { source } = err {
            assert_eq!(source.kind, SyncErrorKind::ServerError);
        } else {
            panic!("expected SyncError");
        }
    }

    #[test]
    fn error_for_status_code_unknown() {
        let err = error_for_status_code("info".into(), StatusCode::IM_A_TEAPOT);
        assert!(matches!(err, AnkiError::NetworkError { .. }));
    }

    #[test]
    fn guess_reqwest_error_dns() {
        let err = guess_reqwest_error("dns error: cancelled".into());
        assert!(matches!(err, AnkiError::Interrupted));
    }

    #[test]
    fn guess_reqwest_error_unreachable() {
        let err = guess_reqwest_error("host unreachable".into());
        if let AnkiError::NetworkError { source } = err {
            assert_eq!(source.kind, NetworkErrorKind::Offline);
        } else {
            panic!("expected NetworkError");
        }
    }

    #[test]
    fn guess_reqwest_error_timeout() {
        let err = guess_reqwest_error("connection timed out".into());
        if let AnkiError::NetworkError { source } = err {
            assert_eq!(source.kind, NetworkErrorKind::Timeout);
        } else {
            panic!("expected NetworkError");
        }
    }

    #[test]
    fn guess_reqwest_error_other() {
        let err = guess_reqwest_error("something else".into());
        if let AnkiError::NetworkError { source } = err {
            assert_eq!(source.kind, NetworkErrorKind::Other);
        } else {
            panic!("expected NetworkError");
        }
    }

    #[test]
    fn anki_error_sync_error_constructor() {
        let err = AnkiError::sync_error("test", SyncErrorKind::Conflict);
        assert!(matches!(err, AnkiError::SyncError { .. }));
    }

    #[test]
    fn anki_error_server_message() {
        let err = AnkiError::server_message("server says no");
        if let AnkiError::SyncError { source } = err {
            assert_eq!(source.kind, SyncErrorKind::ServerMessage);
            assert_eq!(source.info, "server says no");
        } else {
            panic!("expected SyncError");
        }
    }

    #[test]
    fn sync_error_display() {
        let err = SyncError {
            info: "test info".into(),
            kind: SyncErrorKind::Conflict,
        };
        let display = format!("{err}");
        assert!(display.contains("Conflict"));
        assert!(display.contains("test info"));
    }
}
