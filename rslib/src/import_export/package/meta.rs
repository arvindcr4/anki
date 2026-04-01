// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use std::fs::File;
use std::io;
use std::io::Read;

pub(super) use anki_proto::import_export::package_metadata::Version;
pub(super) use anki_proto::import_export::PackageMetadata as Meta;
use prost::Message;
use zip::ZipArchive;
use zstd::stream::copy_decode;

use crate::import_export::ImportError;
use crate::prelude::*;
use crate::storage::SchemaVersion;

pub(super) trait VersionExt {
    fn collection_filename(&self) -> &'static str;
    fn schema_version(&self) -> SchemaVersion;
}

impl VersionExt for Version {
    fn collection_filename(&self) -> &'static str {
        match self {
            Version::Unknown => unreachable!(),
            Version::Legacy1 => "collection.anki2",
            Version::Legacy2 => "collection.anki21",
            Version::Latest => "collection.anki21b",
        }
    }

    /// Latest schema version that is supported by all clients supporting
    /// this package version.
    fn schema_version(&self) -> SchemaVersion {
        match self {
            Version::Unknown => unreachable!(),
            Version::Legacy1 | Version::Legacy2 => SchemaVersion::V11,
            Version::Latest => SchemaVersion::V18,
        }
    }
}

pub(in crate::import_export) trait MetaExt: Sized {
    fn new() -> Self;
    fn new_legacy() -> Self;
    fn from_archive(archive: &mut ZipArchive<File>) -> Result<Self>;
    fn collection_filename(&self) -> &'static str;
    fn schema_version(&self) -> SchemaVersion;
    fn zstd_compressed(&self) -> bool;
    fn media_list_is_hashmap(&self) -> bool;
    fn is_legacy(&self) -> bool;
    fn copy(&self, reader: &mut impl Read, writer: &mut impl io::Write) -> io::Result<()>;
}

impl MetaExt for Meta {
    fn new() -> Self {
        Self {
            version: Version::Latest as i32,
        }
    }

    fn new_legacy() -> Self {
        Self {
            version: Version::Legacy2 as i32,
        }
    }

    /// Extracts meta data from an archive and checks if its version is
    /// supported.
    fn from_archive(archive: &mut ZipArchive<File>) -> Result<Self> {
        let meta_bytes = archive.by_name("meta").ok().and_then(|mut meta_file| {
            let mut buf = vec![];
            meta_file.read_to_end(&mut buf).ok()?;
            Some(buf)
        });
        let meta = if let Some(bytes) = meta_bytes {
            let meta: Meta = Message::decode(&*bytes)?;
            if meta.version() == Version::Unknown {
                return Err(AnkiError::ImportError {
                    source: ImportError::TooNew,
                });
            }
            meta
        } else {
            Meta {
                version: if archive.by_name("collection.anki21").is_ok() {
                    Version::Legacy2
                } else {
                    Version::Legacy1
                } as i32,
            }
        };
        Ok(meta)
    }

    fn collection_filename(&self) -> &'static str {
        self.version().collection_filename()
    }

    /// Latest schema version that is supported by all clients supporting
    /// this package version.
    fn schema_version(&self) -> SchemaVersion {
        self.version().schema_version()
    }

    fn zstd_compressed(&self) -> bool {
        !self.is_legacy()
    }

    fn media_list_is_hashmap(&self) -> bool {
        self.is_legacy()
    }

    fn is_legacy(&self) -> bool {
        matches!(self.version(), Version::Legacy1 | Version::Legacy2)
    }

    fn copy(&self, reader: &mut impl Read, writer: &mut impl io::Write) -> io::Result<()> {
        if self.zstd_compressed() {
            copy_decode(reader, writer)
        } else {
            io::copy(reader, writer).map(|_| ())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_collection_filename_legacy1() {
        assert_eq!(Version::Legacy1.collection_filename(), "collection.anki2");
    }

    #[test]
    fn version_collection_filename_legacy2() {
        assert_eq!(Version::Legacy2.collection_filename(), "collection.anki21");
    }

    #[test]
    fn version_collection_filename_latest() {
        assert_eq!(Version::Latest.collection_filename(), "collection.anki21b");
    }

    #[test]
    fn version_schema_legacy1() {
        assert_eq!(Version::Legacy1.schema_version(), SchemaVersion::V11);
    }

    #[test]
    fn version_schema_legacy2() {
        assert_eq!(Version::Legacy2.schema_version(), SchemaVersion::V11);
    }

    #[test]
    fn version_schema_latest() {
        assert_eq!(Version::Latest.schema_version(), SchemaVersion::V18);
    }

    #[test]
    fn meta_new_is_latest() {
        let meta = Meta::new();
        assert_eq!(meta.version(), Version::Latest);
    }

    #[test]
    fn meta_new_legacy_is_legacy2() {
        let meta = Meta::new_legacy();
        assert_eq!(meta.version(), Version::Legacy2);
    }

    #[test]
    fn meta_latest_not_legacy() {
        let meta = Meta::new();
        assert!(!meta.is_legacy());
        assert!(meta.zstd_compressed());
        assert!(!meta.media_list_is_hashmap());
    }

    #[test]
    fn meta_legacy_properties() {
        let meta = Meta::new_legacy();
        assert!(meta.is_legacy());
        assert!(!meta.zstd_compressed());
        assert!(meta.media_list_is_hashmap());
    }

    #[test]
    fn meta_collection_filename_delegates() {
        assert_eq!(Meta::new().collection_filename(), "collection.anki21b");
        assert_eq!(Meta::new_legacy().collection_filename(), "collection.anki21");
    }

    #[test]
    fn meta_schema_version_delegates() {
        assert_eq!(Meta::new().schema_version(), SchemaVersion::V18);
        assert_eq!(Meta::new_legacy().schema_version(), SchemaVersion::V11);
    }
}
