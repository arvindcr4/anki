// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use serde_json::json;

/// These items are expected to exist in schema 11. When adding
/// new config variables, you do not need to add them here -
/// just create an accessor function in one of the config/*.rs files,
/// with an appropriate default for missing/invalid values instead.
pub(crate) fn schema11_config_as_string(creation_offset: Option<i32>) -> String {
    let obj = json!({
        "activeDecks": [1],
        "curDeck": 1,
        "newSpread": 0,
        "collapseTime": 1200,
        "timeLim": 0,
        "estTimes": true,
        "dueCounts": true,
        "curModel": null,
        "nextPos": 1,
        "sortType": "noteFld",
        "sortBackwards": false,
        "addToCur": true,
        "dayLearnFirst": false,
        "schedVer": 2,
        "creationOffset": creation_offset,
        "sched2021": true,
    });
    serde_json::to_string(&obj).unwrap()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schema11_config_is_valid_json() {
        let s = schema11_config_as_string(None);
        let parsed: serde_json::Value = serde_json::from_str(&s).unwrap();
        assert!(parsed.is_object());
    }

    #[test]
    fn schema11_config_contains_expected_keys() {
        let s = schema11_config_as_string(Some(300));
        let parsed: serde_json::Value = serde_json::from_str(&s).unwrap();
        let obj = parsed.as_object().unwrap();
        assert!(obj.contains_key("activeDecks"));
        assert!(obj.contains_key("curDeck"));
        assert!(obj.contains_key("schedVer"));
        assert!(obj.contains_key("creationOffset"));
        assert!(obj.contains_key("sched2021"));
        assert!(obj.contains_key("sortType"));
    }

    #[test]
    fn schema11_config_creation_offset_some() {
        let s = schema11_config_as_string(Some(-300));
        let parsed: serde_json::Value = serde_json::from_str(&s).unwrap();
        assert_eq!(parsed["creationOffset"], -300);
    }

    #[test]
    fn schema11_config_creation_offset_none() {
        let s = schema11_config_as_string(None);
        let parsed: serde_json::Value = serde_json::from_str(&s).unwrap();
        assert!(parsed["creationOffset"].is_null());
    }

    #[test]
    fn schema11_config_default_values() {
        let s = schema11_config_as_string(None);
        let parsed: serde_json::Value = serde_json::from_str(&s).unwrap();
        assert_eq!(parsed["schedVer"], 2);
        assert_eq!(parsed["sched2021"], true);
        assert_eq!(parsed["collapseTime"], 1200);
        assert_eq!(parsed["nextPos"], 1);
        assert_eq!(parsed["sortType"], "noteFld");
        assert_eq!(parsed["sortBackwards"], false);
    }
}
