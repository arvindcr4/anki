# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.w3.org/1999/xhtml

"""
Tests for AnkiConnect HTTP client.

These tests use mocking to test the client without requiring
Anki Desktop to be running.
"""

from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import Mock, patch

from anki.ankiconnect import (
    AnkiConnectClient,
    AnkiConnectUnavailable,
    AnkiConnectRateLimit,
    AnkiConnectAPIError,
    DEFAULT_URL,
    MAX_RETRIES,
)


class MockResponse:
    """Mock HTTP response for requests."""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self) -> dict:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def make_success_response(result: Any) -> MockResponse:
    """Create a successful AnkiConnect response."""
    return MockResponse({"result": result, "error": None})


def make_error_response(error: str, status_code: int = 200) -> MockResponse:
    """Create an error response from AnkiConnect."""
    return MockResponse({"result": None, "error": error}, status_code=status_code)


class TestDiscover:
    """Tests for discover() method."""

    def test_discover_success(self) -> None:
        """Test successful discovery when AnkiConnect is available."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(6)

            client = AnkiConnectClient()
            assert client.discover() is True
            mock_session.post.assert_called_once()
            # Verify the request format
            call_args = mock_session.post.call_args
            assert call_args[0][0] == DEFAULT_URL
            assert call_args[1]["json"]["action"] == "version"
            assert call_args[1]["json"]["version"] == 6

    def test_discover_unavailable(self) -> None:
        """Test discovery when AnkiConnect is not running."""
        with patch("requests.Session") as MockSession:
            from requests.exceptions import ConnectionError

            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.side_effect = ConnectionError("Connection refused")

            client = AnkiConnectClient()
            assert client.discover() is False

    def test_discover_api_error(self) -> None:
        """Test discovery when AnkiConnect returns an error."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_error_response("API error")

            client = AnkiConnectClient()
            assert client.discover() is False


class TestGetDecks:
    """Tests for get_decks() method."""

    def test_get_decks_empty(self) -> None:
        """Test getting decks when none exist."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response([])

            client = AnkiConnectClient()
            assert client.get_decks() == []

    def test_get_decks_with_values(self) -> None:
        """Test getting deck names."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(
                ["Default", "My Deck", "Japanese::JLPT N5"]
            )

            client = AnkiConnectClient()
            decks = client.get_decks()
            assert decks == ["Default", "My Deck", "Japanese::JLPT N5"]
            mock_session.post.assert_called_once()

    def test_get_decks_unavailable(self) -> None:
        """Test getting decks when AnkiConnect is unavailable."""
        with patch("requests.Session") as MockSession:
            from requests.exceptions import ConnectionError

            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.side_effect = ConnectionError("Connection refused")

            client = AnkiConnectClient()
            assert client.get_decks() == []


class TestAddNote:
    """Tests for add_note() method."""

    def test_add_note_basic(self) -> None:
        """Test adding a basic note."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(1234567890)

            client = AnkiConnectClient()
            note_id = client.add_note("Hello", "World", "Test Deck")

            assert note_id == 1234567890
            # Verify the request structure
            call_args = mock_session.post.call_args
            payload = call_args[1]["json"]
            assert payload["action"] == "addNote"
            assert payload["params"]["note"]["deckName"] == "Test Deck"
            assert payload["params"]["note"]["modelName"] == "Basic"
            assert payload["params"]["note"]["fields"]["Front"] == "Hello"
            assert payload["params"]["note"]["fields"]["Back"] == "World"

    def test_add_note_with_tags(self) -> None:
        """Test adding a note with tags."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(123)

            client = AnkiConnectClient()
            note_id = client.add_note(
                "Question",
                "Answer",
                "My Deck",
                tags=["important", "review"],
            )

            assert note_id == 123
            call_args = mock_session.post.call_args
            payload = call_args[1]["json"]
            assert payload["params"]["note"]["tags"] == ["important", "review"]

    def test_add_note_duplicate(self) -> None:
        """Test adding a duplicate note returns None."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(None)

            client = AnkiConnectClient()
            note_id = client.add_note("Duplicate", "Content", "Deck")

            assert note_id is None

    def test_add_note_unavailable(self) -> None:
        """Test adding a note when AnkiConnect is unavailable."""
        with patch("requests.Session") as MockSession:
            from requests.exceptions import ConnectionError

            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.side_effect = ConnectionError("Connection refused")

            client = AnkiConnectClient()
            assert client.add_note("Front", "Back", "Deck") is None


class TestRateLimit:
    """Tests for rate limiting behavior."""

    def test_rate_limit_429(self) -> None:
        """Test handling of 429 rate limit response."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session

            # First two calls return 429, third succeeds
            mock_session.post.side_effect = [
                MockResponse({}, 429),
                MockResponse({}, 429),
                make_success_response(123),
            ]

            client = AnkiConnectClient()
            note_id = client.add_note("Front", "Back", "Deck")

            assert note_id == 123
            assert mock_session.post.call_count == 3

    def test_rate_limit_exhausted_retries(self) -> None:
        """Test behavior when all retries are exhausted due to rate limiting."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session

            # All calls return 429
            mock_session.post.side_effect = [
                MockResponse({}, 429),
                MockResponse({}, 429),
                MockResponse({}, 429),
            ]

            client = AnkiConnectClient()

            # Use _invoke() directly to test rate limit exception propagation
            # add_note() catches errors and returns None, but _invoke() raises them
            with pytest.raises(AnkiConnectRateLimit):
                client._invoke("addNote", {"note": {"deckName": "Test", "fields": {"Front": "A", "Back": "B"}}})


class TestGetDeckNamesAndIds:
    """Tests for get_deck_names_and_ids() method."""

    def test_get_deck_names_and_ids(self) -> None:
        """Test getting deck names mapped to IDs."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(
                {"Default": 1, "My Deck": 1234567890, "Japanese::JLPT N5": 9876543210}
            )

            client = AnkiConnectClient()
            decks = client.get_deck_names_and_ids()

            assert decks == {
                "Default": 1,
                "My Deck": 1234567890,
                "Japanese::JLPT N5": 9876543210,
            }


class TestCreateDeck:
    """Tests for create_deck() method."""

    def test_create_deck_success(self) -> None:
        """Test creating a new deck."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(12345)

            client = AnkiConnectClient()
            deck_id = client.create_deck("New Deck")

            assert deck_id == 12345
            call_args = mock_session.post.call_args
            payload = call_args[1]["json"]
            assert payload["action"] == "createDeck"
            assert payload["params"]["deck"] == "New Deck"


class TestAddNotesBatch:
    """Tests for add_notes_batch() method."""

    def test_add_notes_batch_success(self) -> None:
        """Test adding multiple notes at once."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(
                [123, 456, 789]
            )

            client = AnkiConnectClient()
            notes = [
                {"deckName": "Deck1", "fields": {"Front": "A", "Back": "1"}},
                {"deckName": "Deck2", "fields": {"Front": "B", "Back": "2"}},
                {"deckName": "Deck3", "fields": {"Front": "C", "Back": "3"}},
            ]
            result = client.add_notes_batch(notes)

            assert result == [123, 456, 789]
            call_args = mock_session.post.call_args
            payload = call_args[1]["json"]
            assert payload["action"] == "addNotes"
            assert len(payload["params"]["notes"]) == 3

    def test_add_notes_batch_with_duplicates(self) -> None:
        """Test batch with some duplicates (None values)."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(
                [123, None, 456]
            )

            client = AnkiConnectClient()
            result = client.add_notes_batch(
                [
                    {"deckName": "Deck", "fields": {"Front": "A", "Back": "1"}},
                    {"deckName": "Deck", "fields": {"Front": "B", "Back": "2"}},
                    {"deckName": "Deck", "fields": {"Front": "C", "Back": "3"}},
                ]
            )

            assert result == [123, None, 456]


class TestContextManager:
    """Tests for context manager support."""

    def test_context_manager(self) -> None:
        """Test that client can be used as context manager."""
        with patch("requests.Session") as MockSession:
            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.return_value = make_success_response(6)
            mock_session.close = Mock()

            with AnkiConnectClient() as client:
                assert client.discover() is True

            mock_session.close.assert_called_once()


class TestConnectionRefused:
    """Tests for connection refused handling."""

    def test_connection_refused_exception(self) -> None:
        """Test that ConnectionError raises AnkiConnectUnavailable."""
        with patch("requests.Session") as MockSession:
            from requests.exceptions import ConnectionError

            mock_session = Mock()
            MockSession.return_value = mock_session
            mock_session.post.side_effect = ConnectionError("Connection refused")

            client = AnkiConnectClient()

            with pytest.raises(AnkiConnectUnavailable) as exc_info:
                client._invoke("version")

            assert "Cannot connect to AnkiConnect" in str(exc_info.value)
            assert DEFAULT_URL in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
