# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
Tests for offline sync queue.

These tests use mocking to test the queue without requiring
Anki Desktop to be running.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from anki.ankiconnect import AnkiConnectRateLimit, AnkiConnectUnavailable
from anki.offline_queue import (
    MAX_BATCH_SIZE,
    QUEUE_FILENAME,
    OfflineSyncQueue,
    QueuedCard,
    QueueStatus,
)


class _FakeAnkiConnectClient:
    def __init__(
        self,
        *,
        discover_result: bool = True,
        invoke_return: object | None = None,
        invoke_side_effect: object | None = None,
    ) -> None:
        self.discover = Mock(return_value=discover_result)
        self._invoke = Mock()
        if invoke_side_effect is not None:
            self._invoke.side_effect = invoke_side_effect
        else:
            self._invoke.return_value = invoke_return
        self.closed = False

    def __enter__(self) -> "_FakeAnkiConnectClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True


class TestQueuedCard:
    """Tests for QueuedCard dataclass."""

    def test_create_queued_card(self) -> None:
        """Test creating a queued card with all fields."""
        card = QueuedCard(
            local_id=123,
            front="Question",
            back="Answer",
            deck="Test Deck",
            tags=["tag1", "tag2"],
            queued_at=1000000,
            attempt_count=1,
            last_error=None,
        )
        assert card.local_id == 123
        assert card.front == "Question"
        assert card.back == "Answer"
        assert card.deck == "Test Deck"
        assert card.tags == ["tag1", "tag2"]
        assert card.queued_at == 1000000
        assert card.attempt_count == 1
        assert card.last_error is None

    def test_queued_card_defaults(self) -> None:
        """Test default values for optional fields."""
        card = QueuedCard(
            local_id=456,
            front="Q",
            back="A",
            deck="Deck",
            queued_at=1000000,
        )
        assert card.tags == []
        assert card.attempt_count == 0
        assert card.last_error is None


class TestOfflineSyncQueue:
    """Tests for OfflineSyncQueue class."""

    def setup_method(self) -> None:
        """Create a temporary queue for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue_path = Path(self.temp_dir) / QUEUE_FILENAME
        self.queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            retry_interval=1,  # Fast retry for tests
            deck="Test Deck",
        )

    def teardown_method(self) -> None:
        """Clean up queue."""
        self.queue.stop_auto_sync()
        if self.queue_path.exists():
            self.queue_path.unlink()

    def test_empty_queue(self) -> None:
        """Test empty queue returns zero length."""
        assert len(self.queue) == 0

    def test_add_card(self) -> None:
        """Test adding a single card to the queue."""
        position = self.queue.add_card(
            front="What is Rust?",
            back="A systems programming language.",
            deck="Programming",
            tags=["rust", "coding"],
        )
        assert len(self.queue) == 1
        assert position == 1

    def test_add_card_uses_default_deck(self) -> None:
        """Test that default deck is used when not specified."""
        self.queue.add_card(front="Q", back="A")
        cards = self.queue.get_queue()
        assert cards[0].deck == "Test Deck"

    def test_add_cards_batch(self) -> None:
        """Test adding multiple cards at once."""
        cards = [
            {"front": "Card 1", "back": "Answer 1"},
            {"front": "Card 2", "back": "Answer 2"},
            {"front": "Card 3", "back": "Answer 3"},
        ]
        count = self.queue.add_cards_batch(cards)
        assert count == 3
        assert len(self.queue) == 3

    def test_fifo_order(self) -> None:
        """Test that cards are processed in FIFO order."""
        self.queue.add_card(front="First", back="1")
        time.sleep(0.01)  # Ensure different timestamps
        self.queue.add_card(front="Second", back="2")
        time.sleep(0.01)
        self.queue.add_card(front="Third", back="3")

        cards = self.queue.get_queue()
        assert cards[0].front == "First"
        assert cards[1].front == "Second"
        assert cards[2].front == "Third"

    def test_remove_card(self) -> None:
        """Test removing a card by local_id."""
        self.queue.add_card(front="Q1", back="A1", local_id=100)
        self.queue.add_card(front="Q2", back="A2", local_id=200)

        removed = self.queue.remove_card(100)
        assert removed is True
        assert len(self.queue) == 1
        cards = self.queue.get_queue()
        assert cards[0].local_id == 200

    def test_remove_nonexistent_card(self) -> None:
        """Test removing a card that doesn't exist."""
        result = self.queue.remove_card(9999)
        assert result is False

    def test_queue_persists_across_restart(self) -> None:
        """Test that queue survives application restart."""
        # Add cards
        self.queue.add_card(front="Persisted", back="Yes", local_id=42)

        # Create new queue instance with same path
        new_queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            deck="Different Deck",
        )

        assert len(new_queue) == 1
        cards = new_queue.get_queue()
        assert cards[0].front == "Persisted"

    def test_clear_queue(self) -> None:
        """Test clearing all cards from queue."""
        self.queue.add_card(front="Q1", back="A1")
        self.queue.add_card(front="Q2", back="A2")

        count = self.queue.clear_queue()
        assert count == 2
        assert len(self.queue) == 0

    def test_get_status_empty(self) -> None:
        """Test getting status of empty queue."""
        status = self.queue.get_status()
        assert status.pending_count == 0
        assert status.syncing is False
        assert status.last_error is None

    def test_get_status_with_cards(self) -> None:
        """Test status reflects queued cards."""
        self.queue.add_card(front="Q", back="A")
        self.queue.add_card(front="Q2", back="A2")

        status = self.queue.get_status()
        assert status.pending_count == 2


class TestSyncNow:
    """Tests for sync_now() method."""

    def setup_method(self) -> None:
        """Create a temporary queue for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue_path = Path(self.temp_dir) / QUEUE_FILENAME
        self.queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            retry_interval=1,
            deck="Test Deck",
        )

    def teardown_method(self) -> None:
        """Clean up queue."""
        self.queue.stop_auto_sync()
        if self.queue_path.exists():
            self.queue_path.unlink()

    def test_sync_now_returns_zero_when_empty(self) -> None:
        """Test syncing empty queue returns zeros."""
        success, failed = self.queue.sync_now()
        assert success == 0
        assert failed == 0

    def test_sync_now_returns_zero_when_already_syncing(self) -> None:
        """Test that concurrent sync attempts are rejected."""
        self.queue.add_card(front="Q", back="A")

        # Set syncing flag directly
        with self.queue._lock:
            self.queue._syncing = True

        success, failed = self.queue.sync_now()
        assert success == 0
        assert failed == 0

    def test_sync_success_removes_card(self) -> None:
        """Test that successfully synced cards are removed from queue."""
        self.queue.add_card(front="Q", back="A", local_id=1)

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(invoke_return=12345)

            success, failed = self.queue.sync_now()

        assert success == 1
        assert failed == 0
        assert len(self.queue) == 0

    def test_sync_failure_keeps_card(self) -> None:
        """Test that failed cards remain in queue with error set."""
        self.queue.add_card(front="Q", back="A", local_id=1)

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(invoke_return=None)

            success, failed = self.queue.sync_now()

        assert success == 0
        assert failed == 1
        assert len(self.queue) == 1
        cards = self.queue.get_queue()
        assert cards[0].last_error is not None

    def test_sync_unavailable_stops_processing(self) -> None:
        """Test that unavailable AnkiConnect stops sync immediately."""
        self.queue.add_card(front="Q1", back="A1")
        self.queue.add_card(front="Q2", back="A2")

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(discover_result=False)

            success, failed = self.queue.sync_now()

        # No progress made
        assert success == 0
        assert failed == 2
        assert len(self.queue) == 2

    def test_sync_unavailable_reports_all_pending_cards_across_batches(self) -> None:
        """Test that an initial outage counts every pending card, not just one batch."""
        total_cards = MAX_BATCH_SIZE + 1
        for index in range(total_cards):
            self.queue.add_card(front=f"Q{index}", back=f"A{index}")

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(discover_result=False)

            success, failed = self.queue.sync_now()

        assert success == 0
        assert failed == total_cards
        assert len(self.queue) == total_cards

    def test_sync_success_processes_all_pending_cards_across_batches(self) -> None:
        """Test that one sync attempt drains every queued card, not just the first batch."""
        total_cards = MAX_BATCH_SIZE + 2
        for local_id in range(1, total_cards + 1):
            self.queue.add_card(
                front=f"Q{local_id}", back=f"A{local_id}", local_id=local_id
            )

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(invoke_return=12345)

            success, failed = self.queue.sync_now()

        assert success == total_cards
        assert failed == 0
        assert len(self.queue) == 0

    def test_sync_increments_attempt_count(self) -> None:
        """Test that each sync attempt increments the counter."""
        self.queue.add_card(front="Q", back="A", local_id=1)

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(invoke_return=None)

            self.queue.sync_now()
            self.queue.sync_now()

        cards = self.queue.get_queue()
        assert cards[0].attempt_count == 2

    def test_sync_unexpected_exception_keeps_card_queued(self) -> None:
        """Test that unexpected client failures do not crash the queue sync."""
        self.queue.add_card(front="Q", back="A", local_id=1)

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(
                invoke_side_effect=RuntimeError("boom")
            )

            success, failed = self.queue.sync_now()

        assert success == 0
        assert failed == 1
        cards = self.queue.get_queue()
        assert len(cards) == 1
        assert cards[0].last_error == "boom"
        assert self.queue.get_status().last_error == "boom"

    @pytest.mark.parametrize(
        "error_type,error_message",
        [
            (AnkiConnectUnavailable, "temporary outage"),
            (AnkiConnectRateLimit, "rate limited"),
        ],
    )
    def test_sync_unavailable_mid_batch_counts_remaining_and_persists(
        self,
        error_type: type[Exception],
        error_message: str,
    ) -> None:
        """Test that a mid-batch outage counts the current card and saves progress."""
        self.queue.add_card(front="Q1", back="A1", local_id=1)
        self.queue.add_card(front="Q2", back="A2", local_id=2)
        self.queue.add_card(front="Q3", back="A3", local_id=3)

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(
                invoke_side_effect=[12345, error_type(error_message)]
            )

            success, failed = self.queue.sync_now()

        assert success == 1
        assert failed == 2

        reloaded = OfflineSyncQueue(queue_path=self.queue_path, deck="Test Deck")
        remaining_ids = [card.local_id for card in reloaded.get_queue()]
        assert remaining_ids == [2, 3]

    @pytest.mark.parametrize(
        "error_type,error_message",
        [
            (AnkiConnectUnavailable, "temporary outage"),
            (AnkiConnectRateLimit, "rate limited"),
        ],
    )
    def test_sync_unavailable_mid_batch_reports_all_remaining_cards_across_batches(
        self,
        error_type: type[Exception],
        error_message: str,
    ) -> None:
        """Test that a mid-batch outage counts cards still queued beyond the current batch."""
        total_cards = MAX_BATCH_SIZE + 2
        for local_id in range(1, total_cards + 1):
            self.queue.add_card(
                front=f"Q{local_id}", back=f"A{local_id}", local_id=local_id
            )

        with patch("anki.offline_queue.AnkiConnectClient") as MockClient:
            MockClient.return_value = _FakeAnkiConnectClient(
                invoke_side_effect=[12345, error_type(error_message)]
            )

            success, failed = self.queue.sync_now()

        assert success == 1
        assert failed == total_cards - 1

        reloaded = OfflineSyncQueue(queue_path=self.queue_path, deck="Test Deck")
        remaining_ids = [card.local_id for card in reloaded.get_queue()]
        assert remaining_ids == list(range(2, total_cards + 1))

    def test_generated_local_ids_remain_unique_when_clock_stalls(self) -> None:
        """Test that auto-generated local IDs do not collide on a fixed clock."""
        with (
            patch("anki.offline_queue.time.time", return_value=1000),
            patch("anki.offline_queue.time.time_ns", return_value=1_000_000_000),
        ):
            self.queue.add_card(front="Q1", back="A1")
            self.queue.add_card(front="Q2", back="A2")

        cards = self.queue.get_queue()
        assert cards[0].local_id != cards[1].local_id


class TestAutoSync:
    """Tests for auto-sync background thread."""

    def setup_method(self) -> None:
        """Create a temporary queue for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue_path = Path(self.temp_dir) / QUEUE_FILENAME
        self.queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            retry_interval=1,  # Fast for tests
            deck="Test Deck",
        )

    def teardown_method(self) -> None:
        """Clean up queue."""
        self.queue.stop_auto_sync()
        if self.queue_path.exists():
            self.queue_path.unlink()

    def test_start_auto_sync_creates_thread(self) -> None:
        """Test that starting auto-sync creates background thread."""
        self.queue.add_card(front="Q", back="A")
        self.queue.start_auto_sync()
        time.sleep(0.05)  # Give thread time to start
        assert self.queue._monitor_thread is not None
        assert self.queue._monitor_thread.is_alive()

    def test_stop_auto_sync_joins_thread(self) -> None:
        """Test that stopping auto-sync joins the thread."""
        self.queue.start_auto_sync()
        time.sleep(0.05)
        self.queue.stop_auto_sync()
        # Thread should be stopped
        assert (
            self.queue._monitor_thread is None
            or not self.queue._monitor_thread.is_alive()
        )

    def test_stop_auto_sync_handles_monitor_clearing_reference_during_join(
        self,
    ) -> None:
        """Test that stop_auto_sync tolerates the monitor clearing its own reference."""
        monitor = Mock()

        def join(timeout: int) -> None:
            self.queue._monitor_thread = None

        monitor.join.side_effect = join
        monitor.is_alive.return_value = False
        self.queue._monitor_thread = monitor

        self.queue.stop_auto_sync()

        assert self.queue._monitor_thread is None
        monitor.join.assert_called_once_with(timeout=5)

    def test_multiple_start_calls_dont_create_multiple_threads(self) -> None:
        """Test that calling start multiple times is idempotent."""
        self.queue.start_auto_sync()
        thread1 = self.queue._monitor_thread
        self.queue.start_auto_sync()
        thread2 = self.queue._monitor_thread
        assert thread1 is thread2

    def test_stop_timeout_keeps_monitor_reference_and_blocks_restart(self) -> None:
        """Test that a stop timeout does not let a second monitor thread start."""
        monitor = Mock()
        monitor.is_alive.return_value = True
        self.queue._monitor_thread = monitor

        self.queue.stop_auto_sync()

        assert self.queue._monitor_thread is monitor
        monitor.join.assert_called_once_with(timeout=5)

        with patch("anki.offline_queue.threading.Thread") as mock_thread:
            self.queue.start_auto_sync()

        mock_thread.assert_not_called()


class TestQueuePersistence:
    """Tests for queue file persistence."""

    def setup_method(self) -> None:
        """Create a temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue_path = Path(self.temp_dir) / QUEUE_FILENAME

    def teardown_method(self) -> None:
        """Clean up."""
        if self.queue_path.exists():
            self.queue_path.unlink()

    def test_queue_file_created_on_first_add(self) -> None:
        """Test that queue file is created when first card is added."""
        queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            deck="Test",
        )
        queue.add_card(front="Q", back="A")

        assert self.queue_path.exists()

    def test_queue_file_json_format(self) -> None:
        """Test that queue file is valid JSON with expected structure."""
        queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            deck="Test",
        )
        queue.add_card(front="Front", back="Back", local_id=42)

        with open(self.queue_path) as f:
            data = json.load(f)

        assert "cards" in data
        assert "last_success" in data
        assert len(data["cards"]) == 1
        assert data["cards"][0]["front"] == "Front"

    def test_corrupted_queue_file_starts_fresh(self) -> None:
        """Test that corrupted queue file doesn't crash the app."""
        # Write corrupted data
        with open(self.queue_path, "w") as f:
            f.write("not valid json {{{")

        queue = OfflineSyncQueue(
            queue_path=self.queue_path,
            deck="Test",
        )

        # Should start with empty queue
        assert len(queue) == 0
        # And continue working
        queue.add_card(front="Q", back="A")
        assert len(queue) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
