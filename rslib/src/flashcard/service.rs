// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! NotetypeManager service for creating and managing notetypes.
//!
//! This service provides functionality to create and manage the Basic and Cloze
//! notetypes used for generated flashcards.

use std::sync::Arc;

use crate::collection::Collection;
use crate::error::Result;
use crate::flashcard::notetype::basic_notetype;
use crate::flashcard::notetype::cloze_notetype;
use crate::notetype::Notetype;

/// NotetypeManager handles creation and management of notetypes for flashcards.
pub struct NotetypeManager;

impl NotetypeManager {
    /// Create a Basic notetype for Q&A flashcards.
    ///
    /// Returns the created notetype.
    pub fn create_basic_notetype(col: &mut Collection) -> Result<Arc<Notetype>> {
        let nt = basic_notetype(&col.tr);
        let mut nt_mut = nt;
        col.add_notetype(&mut nt_mut, true)?;
        Ok(Arc::new(nt_mut))
    }

    /// Create a Cloze notetype for fill-in-the-blank flashcards.
    ///
    /// Returns the created notetype.
    pub fn create_cloze_notetype(col: &mut Collection) -> Result<Arc<Notetype>> {
        let nt = cloze_notetype(&col.tr);
        let mut nt_mut = nt;
        col.add_notetype(&mut nt_mut, true)?;
        Ok(Arc::new(nt_mut))
    }

    /// Get or create a Basic notetype.
    ///
    /// If a Basic notetype with the standard name already exists, returns it.
    /// Otherwise creates a new one.
    pub fn get_or_create_basic(col: &mut Collection) -> Result<Arc<Notetype>> {
        // Extract name as owned string to avoid holding immutable borrow
        // while calling mutable method
        let name = col.tr.notetypes_basic_name().to_string();
        if let Some(nt) = col.get_notetype_by_name(&name)? {
            return Ok(nt);
        }
        Self::create_basic_notetype(col)
    }

    /// Get or create a Cloze notetype.
    ///
    /// If a Cloze notetype with the standard name already exists, returns it.
    /// Otherwise creates a new one.
    pub fn get_or_create_cloze(col: &mut Collection) -> Result<Arc<Notetype>> {
        // Extract name as owned string to avoid holding immutable borrow
        // while calling mutable method
        let name = col.tr.notetypes_cloze_name().to_string();
        if let Some(nt) = col.get_notetype_by_name(&name)? {
            return Ok(nt);
        }
        Self::create_cloze_notetype(col)
    }
}

#[cfg(test)]
mod test {
    // Integration tests would require a full collection setup
    // which is beyond unit testing scope
}
