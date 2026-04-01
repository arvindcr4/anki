// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

mod bulkadd;
mod complete;
mod findreplace;
mod matcher;
mod notes;
mod register;
mod remove;
mod rename;
mod reparent;
mod service;
mod tree;
pub(crate) mod undo;

use unicase::UniCase;

use crate::prelude::*;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Tag {
    pub name: String,
    pub usn: Usn,
    pub expanded: bool,
}

impl Tag {
    pub fn new(name: String, usn: Usn) -> Self {
        Tag {
            name,
            usn,
            expanded: false,
        }
    }

    pub(crate) fn set_modified(&mut self, usn: Usn) {
        self.usn = usn;
    }
}

pub(crate) fn split_tags(tags: &str) -> impl Iterator<Item = &str> {
    tags.split(is_tag_separator).filter(|tag| !tag.is_empty())
}

pub(crate) fn join_tags(tags: &[String]) -> String {
    if tags.is_empty() {
        "".into()
    } else {
        format!(" {} ", tags.join(" "))
    }
}

fn is_tag_separator(c: char) -> bool {
    c == ' ' || c == '\u{3000}'
}

pub(crate) fn immediate_parent_name_unicase(tag_name: UniCase<&str>) -> Option<UniCase<&str>> {
    tag_name.rsplit_once("::").map(|t| t.0).map(UniCase::new)
}

fn immediate_parent_name_str(tag_name: &str) -> Option<&str> {
    tag_name.rsplit_once("::").map(|t| t.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_tags_basic() {
        let tags: Vec<&str> = split_tags(" foo bar baz ").collect();
        assert_eq!(tags, vec!["foo", "bar", "baz"]);
    }

    #[test]
    fn split_tags_empty() {
        let tags: Vec<&str> = split_tags("").collect();
        assert!(tags.is_empty());
    }

    #[test]
    fn split_tags_whitespace_only() {
        let tags: Vec<&str> = split_tags("   ").collect();
        assert!(tags.is_empty());
    }

    #[test]
    fn split_tags_single() {
        let tags: Vec<&str> = split_tags("hello").collect();
        assert_eq!(tags, vec!["hello"]);
    }

    #[test]
    fn split_tags_cjk_separator() {
        let tags: Vec<&str> = split_tags("foo\u{3000}bar").collect();
        assert_eq!(tags, vec!["foo", "bar"]);
    }

    #[test]
    fn join_tags_basic() {
        let tags = vec!["foo".to_string(), "bar".to_string()];
        assert_eq!(join_tags(&tags), " foo bar ");
    }

    #[test]
    fn join_tags_empty() {
        let tags: Vec<String> = vec![];
        assert_eq!(join_tags(&tags), "");
    }

    #[test]
    fn join_tags_single() {
        let tags = vec!["hello".to_string()];
        assert_eq!(join_tags(&tags), " hello ");
    }

    #[test]
    fn is_tag_separator_space() {
        assert!(is_tag_separator(' '));
    }

    #[test]
    fn is_tag_separator_cjk() {
        assert!(is_tag_separator('\u{3000}'));
    }

    #[test]
    fn is_tag_separator_other() {
        assert!(!is_tag_separator('a'));
        assert!(!is_tag_separator(':'));
        assert!(!is_tag_separator('\t'));
    }

    #[test]
    fn immediate_parent_with_parent() {
        assert_eq!(immediate_parent_name_str("foo::bar::baz"), Some("foo::bar"));
    }

    #[test]
    fn immediate_parent_single_level() {
        assert_eq!(immediate_parent_name_str("foo::bar"), Some("foo"));
    }

    #[test]
    fn immediate_parent_no_parent() {
        assert_eq!(immediate_parent_name_str("foo"), None);
    }

    #[test]
    fn tag_new() {
        let tag = Tag::new("test::tag".to_string(), Usn(5));
        assert_eq!(tag.name, "test::tag");
        assert_eq!(tag.usn, Usn(5));
        assert!(!tag.expanded);
    }

    #[test]
    fn tag_set_modified() {
        let mut tag = Tag::new("foo".to_string(), Usn(1));
        tag.set_modified(Usn(10));
        assert_eq!(tag.usn, Usn(10));
    }
}
