// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Content ingestion service for LLM flashcard generation.
//!
//! This module handles ingesting content from various sources (URLs, audio,
//! video, text) and preparing it for flashcard generation via the LLM.

mod api;
mod models;
mod service;

pub use api::*;
pub use models::*;
pub use service::*;
