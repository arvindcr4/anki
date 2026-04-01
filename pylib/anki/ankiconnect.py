# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
AnkiConnect HTTP client for syncing flashcards to Anki Desktop.

AnkiConnect is an Anki addon that exposes a local HTTP API.
This module provides a Python client to interact with it.

Usage:
    client = AnkiConnectClient()
    if client.discover():
        decks = client.get_decks()
        note_id = client.add_note("Front", "Back", "My Deck")
"""

from __future__ import annotations

import time
from typing import Any

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
DEFAULT_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = 1


class AnkiConnectError(Exception):
    """Base exception for AnkiConnect errors."""
    pass


class AnkiConnectUnavailable(AnkiConnectError):
    """Raised when AnkiConnect is not available (Anki not running or addon not installed)."""
    pass


class AnkiConnectRateLimit(AnkiConnectError):
    """Raised when AnkiConnect returns a 429 rate limit response."""
    pass


class AnkiConnectAPIError(AnkiConnectError):
    """Raised when AnkiConnect returns an error response."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class AnkiConnectClient:
    """
    Client for interacting with AnkiConnect API.

    AnkiConnect exposes a local HTTP API that allows adding notes,
    fetching deck information, and other operations.

    Attributes:
        url: Base URL of AnkiConnect (default: http://localhost:8765)
        timeout: Request timeout in seconds (default: 10)
        version: API version (default: 6)
    """

    def __init__(
        self,
        url: str = DEFAULT_URL,
        timeout: int = DEFAULT_TIMEOUT,
        version: int = 6,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.version = version
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def __enter__(self) -> AnkiConnectClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            self.session.close()
            self.session = None

    def _invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        """
        Invoke an AnkiConnect action.

        Args:
            action: The AnkiConnect action name (e.g., "version", "deckNames")
            params: Optional parameters for the action

        Returns:
            The result from AnkiConnect

        Raises:
            AnkiConnectUnavailable: If AnkiConnect is not reachable
            AnkiConnectRateLimit: If rate limited (429 response)
            AnkiConnectAPIError: If AnkiConnect returns an error
        """
        payload: dict[str, Any] = {"action": action, "version": self.version}
        if params:
            payload["params"] = params

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(
                    self.url,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1))
                        continue
                    raise AnkiConnectRateLimit(
                        "Rate limited by AnkiConnect (429). Please try again later."
                    )

                response.raise_for_status()
                result = response.json()

                if result.get("error"):
                    raise AnkiConnectAPIError(
                        f"AnkiConnect error: {result['error']}"
                    )

                return result.get("result")

            except RequestsConnectionError as e:
                raise AnkiConnectUnavailable(
                    f"Cannot connect to AnkiConnect at {self.url}. "
                    f"Is Anki running with AnkiConnect addon installed?"
                ) from e

    def discover(self) -> bool:
        """
        Check if AnkiConnect is available.

        Sends a version request to discover if Anki is running with
        the AnkiConnect addon.

        Returns:
            True if AnkiConnect is available, False otherwise
        """
        try:
            result = self._invoke("version")
            return result is not None
        except (AnkiConnectUnavailable, AnkiConnectAPIError):
            return False

    def get_version(self) -> int | None:
        """
        Get the AnkiConnect API version.

        Returns:
            The API version number, or None if unavailable
        """
        try:
            return self._invoke("version")
        except AnkiConnectError:
            return None

    def get_decks(self) -> list[str]:
        """
        Get list of deck names.

        Returns:
            List of deck names, or empty list if unavailable
        """
        try:
            return self._invoke("deckNames") or []
        except AnkiConnectError:
            return []

    def get_deck_names_and_ids(self) -> dict[str, int]:
        """
        Get deck names mapped to their IDs.

        Returns:
            Dictionary mapping deck names to deck IDs
        """
        try:
            result = self._invoke("deckNamesAndIds")
            return result or {}
        except AnkiConnectError:
            return {}

    def create_deck(self, deck: str) -> int | None:
        """
        Create a new deck.

        Args:
            deck: Name of the deck to create

        Returns:
            The deck ID if successful, None otherwise
        """
        try:
            return self._invoke("createDeck", {"deck": deck})
        except AnkiConnectError:
            return None

    def add_note(
        self,
        front: str,
        back: str,
        deck: str,
        tags: list[str] | None = None,
    ) -> int | None:
        """
        Add a note to Anki.

        Args:
            front: Front text of the note
            back: Back text of the note
            deck: Name of the deck to add the note to
            tags: Optional list of tags

        Returns:
            The note ID if successful, None if failed (e.g., duplicate)
        """
        note = {
            "deckName": deck,
            "modelName": "Basic",
            "fields": {
                "Front": front,
                "Back": back,
            },
        }
        if tags:
            note["tags"] = tags

        try:
            return self._invoke("addNote", {"note": note})
        except AnkiConnectError:
            return None

    def add_notes_batch(
        self,
        notes: list[dict[str, Any]],
    ) -> list[int | None]:
        """
        Add multiple notes at once.

        Each note should have the structure:
        {
            "deckName": "Deck Name",
            "fields": {"Front": "...", "Back": "..."},
            "tags": ["tag1", "tag2"],  # optional
        }

        Args:
            notes: List of note dictionaries

        Returns:
            List of note IDs (None for duplicates or failed notes)
        """
        try:
            return self._invoke("addNotes", {"notes": notes}) or []
        except AnkiConnectError:
            return [None] * len(notes)

    def find_notes(self, query: str) -> list[int]:
        """
        Find note IDs matching a query.

        Args:
            query: Anki search query (e.g., "deck:MyDeck tag:important")

        Returns:
            List of matching note IDs
        """
        try:
            return self._invoke("findNotes", {"query": query}) or []
        except AnkiConnectError:
            return []

    def notes_info(self, note_ids: list[int]) -> list[dict[str, Any]]:
        """
        Get information about notes.

        Args:
            note_ids: List of note IDs to query

        Returns:
            List of note information dictionaries
        """
        try:
            return self._invoke("notesInfo", {"notes": note_ids}) or []
        except AnkiConnectError:
            return []
