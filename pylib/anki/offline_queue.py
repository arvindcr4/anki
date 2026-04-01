# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
Offline queue for AnkiConnect sync.

When AnkiConnect is unavailable, failed sync attempts are queued
persistently and automatically retried when the connection is restored.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .ankiconnect import (
    AnkiConnectAPIError,
    AnkiConnectClient,
    AnkiConnectRateLimit,
    AnkiConnectUnavailable,
)

# Queue file name in user data directory
QUEUE_FILENAME = "anki_sync_queue.json"

# Default retry interval in seconds
DEFAULT_RETRY_INTERVAL = 60

# Maximum number of cards to sync per batch
MAX_BATCH_SIZE = 10


@dataclass
class QueuedCard:
    """A flashcard queued for sync to Anki."""

    # Unique local ID for the card
    local_id: int
    # Front content of the card
    front: str
    # Back content of the card
    back: str
    # Target deck name
    deck: str
    # Optional tags
    tags: list[str] = field(default_factory=list)
    # When the card was queued (Unix timestamp)
    queued_at: int = 0
    # Number of sync attempts
    attempt_count: int = 0
    # Last error message if any
    last_error: str | None = None


@dataclass
class QueueStatus:
    """Current status of the offline queue."""

    # Number of cards waiting to sync
    pending_count: int
    # Whether sync is currently in progress
    syncing: bool
    # Last successful sync time (Unix timestamp)
    last_success: int | None
    # Last error message if any
    last_error: str | None
    # Whether AnkiConnect is currently available
    anki_connect_available: bool


class OfflineSyncQueue:
    """
    Persistent queue for cards that failed to sync to Anki.

    Cards are persisted to disk so they survive application restarts.
    When AnkiConnect becomes available, cards are automatically synced
    in FIFO order.

    Attributes:
        queue_path: Path to the queue JSON file
        retry_interval: Seconds between retry attempts (default: 60)
        deck: Default deck name for new cards
    """

    def __init__(
        self,
        queue_path: Path,
        retry_interval: int = DEFAULT_RETRY_INTERVAL,
        deck: str = "LLM Cards",
    ) -> None:
        self.queue_path = queue_path
        self.retry_interval = retry_interval
        self.default_deck = deck
        self._cards: list[QueuedCard] = []
        self._lock = threading.Lock()
        self._syncing = False
        self._last_success: int | None = None
        self._last_error: str | None = None
        self._next_generated_local_id = int(time.time_ns())
        self._monitor_thread: threading.Thread | None = None
        self._stop_monitor = threading.Event()

        # Load existing queue from disk
        self._load_queue()
        self._next_generated_local_id = max(
            self._next_generated_local_id,
            max((card.local_id for card in self._cards), default=0),
        )

    def _load_queue(self) -> None:
        """Load queue from disk if it exists."""
        if self.queue_path.exists():
            try:
                with open(self.queue_path, "r") as f:
                    data = json.load(f)
                    self._cards = [QueuedCard(**c) for c in data.get("cards", [])]
                    self._last_success = data.get("last_success")
            except (json.JSONDecodeError, TypeError) as e:
                # If file is corrupted, start with empty queue
                self._cards = []
                self._last_error = f"Failed to load queue: {e}"

    def _save_queue(self) -> None:
        """Persist queue to disk."""
        data = {
            "cards": [asdict(c) for c in self._cards],
            "last_success": self._last_success,
        }
        # Write atomically using a temp file
        temp_path = self.queue_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self.queue_path)

    def _allocate_local_id(self) -> int:
        """
        Allocate a queue-local identifier that remains unique even if the
        wall clock does not advance between calls.
        """
        next_id = max(self._next_generated_local_id + 1, int(time.time_ns()))
        self._next_generated_local_id = next_id
        return next_id

    def add_card(
        self,
        front: str,
        back: str,
        deck: str | None = None,
        tags: list[str] | None = None,
        local_id: int | None = None,
    ) -> int:
        """
        Add a card to the sync queue.

        Args:
            front: Front content of the card
            back: Back content of the card
            deck: Target deck name (uses default if not specified)
            tags: Optional list of tags
            local_id: Optional local ID to track the card

        Returns:
            The queue position (1-based)
        """
        with self._lock:
            resolved_local_id = (
                local_id if local_id is not None else self._allocate_local_id()
            )
            self._next_generated_local_id = max(
                self._next_generated_local_id,
                resolved_local_id,
            )
            card = QueuedCard(
                local_id=resolved_local_id,
                front=front,
                back=back,
                deck=deck or self.default_deck,
                tags=tags or [],
                queued_at=int(time.time()),
                attempt_count=0,
                last_error=None,
            )
            self._cards.append(card)
            self._cards.sort(key=lambda c: c.queued_at)  # FIFO order
            self._save_queue()
            return len(self._cards)

    def add_cards_batch(
        self,
        cards: list[dict[str, Any]],
    ) -> int:
        """
        Add multiple cards to the queue at once.

        Args:
            cards: List of card dicts with front, back, deck, tags, local_id

        Returns:
            Number of cards added
        """
        with self._lock:
            queued_cards = []
            now = int(time.time())
            for i, card_data in enumerate(cards):
                resolved_local_id = card_data.get("local_id")
                if resolved_local_id is None:
                    resolved_local_id = self._allocate_local_id()
                else:
                    self._next_generated_local_id = max(
                        self._next_generated_local_id,
                        resolved_local_id,
                    )
                card = QueuedCard(
                    local_id=resolved_local_id,
                    front=card_data["front"],
                    back=card_data["back"],
                    deck=card_data.get("deck") or self.default_deck,
                    tags=card_data.get("tags", []),
                    queued_at=now + i,
                    attempt_count=0,
                    last_error=None,
                )
                queued_cards.append(card)

            self._cards.extend(queued_cards)
            self._cards.sort(key=lambda c: c.queued_at)  # FIFO order
            self._save_queue()
            return len(queued_cards)

    def remove_card(self, local_id: int) -> bool:
        """
        Remove a card from the queue by its local ID.

        Args:
            local_id: The local ID of the card to remove

        Returns:
            True if the card was found and removed
        """
        with self._lock:
            original_len = len(self._cards)
            self._cards = [c for c in self._cards if c.local_id != local_id]
            if len(self._cards) != original_len:
                self._save_queue()
                return True
            return False

    def get_queue(self) -> list[QueuedCard]:
        """Get a copy of the current queue in FIFO order."""
        with self._lock:
            return list(self._cards)

    def get_status(self) -> QueueStatus:
        """
        Get the current queue status.

        Returns:
            QueueStatus with counts and state information
        """
        with self._lock:
            pending_count = len(self._cards)
            syncing = self._syncing
            last_success = self._last_success
            last_error = self._last_error

        anki_available = self._check_anki_connect()
        return QueueStatus(
            pending_count=pending_count,
            syncing=syncing,
            last_success=last_success,
            last_error=last_error,
            anki_connect_available=anki_available,
        )

    def _check_anki_connect(self) -> bool:
        """Check if AnkiConnect is available."""
        client = AnkiConnectClient()
        try:
            return client.discover()
        except Exception:
            return False
        finally:
            client.close()

    def _remove_card_instance(self, card: QueuedCard) -> None:
        """Remove the exact queued card instance that just synced."""
        self._cards = [queued for queued in self._cards if queued is not card]

    def sync_now(self) -> tuple[int, int]:
        """
        Attempt to sync all queued cards to Anki.

        Returns:
            Tuple of (success_count, failed_count)
        """
        with self._lock:
            if self._syncing:
                return 0, 0
            self._syncing = True

        try:
            success_count = 0
            failed_count = 0

            # Get cards to process (in FIFO order)
            cards_to_process = []
            pending_count = 0
            with self._lock:
                cards_to_process = list(self._cards)
                pending_count = len(cards_to_process)
                self._last_error = None
            if not cards_to_process:
                return 0, 0

            with AnkiConnectClient() as client:
                # Check if AnkiConnect is available
                if not client.discover():
                    with self._lock:
                        self._last_error = "AnkiConnect unavailable"
                    return 0, pending_count

                # Process cards in batches
                for batch_start in range(0, pending_count, MAX_BATCH_SIZE):
                    batch = cards_to_process[batch_start : batch_start + MAX_BATCH_SIZE]
                    for card in batch:
                        with self._lock:
                            card.attempt_count += 1

                        note = {
                            "deckName": card.deck,
                            "modelName": "Basic",
                            "fields": {
                                "Front": card.front,
                                "Back": card.back,
                            },
                        }
                        if card.tags:
                            note["tags"] = card.tags

                        try:
                            note_id = client._invoke("addNote", {"note": note})

                            if note_id is not None:
                                # Success - remove the exact queued entry that synced.
                                with self._lock:
                                    self._remove_card_instance(card)
                                    self._last_success = int(time.time())
                                success_count += 1
                            else:
                                with self._lock:
                                    card.last_error = "Anki returned null"
                                failed_count += 1

                        except (AnkiConnectUnavailable, AnkiConnectRateLimit) as e:
                            with self._lock:
                                card.last_error = str(e)
                                self._last_error = str(e)
                                # Persist partial progress before returning early.
                                self._save_queue()
                            return success_count, pending_count - success_count

                        except AnkiConnectAPIError as e:
                            with self._lock:
                                card.last_error = str(e)
                                self._last_error = str(e)
                            failed_count += 1

                        except Exception as e:
                            with self._lock:
                                card.last_error = str(e)
                                self._last_error = str(e)
                            failed_count += 1

            # Save state after sync attempt
            self._save_queue()
            return success_count, failed_count

        finally:
            with self._lock:
                self._syncing = False

    def start_auto_sync(self) -> None:
        """Start background thread that auto-syncs when AnkiConnect is available."""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return

        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="OfflineSyncQueue-monitor",
        )
        self._monitor_thread.start()

    def stop_auto_sync(self) -> None:
        """Stop the background auto-sync thread."""
        self._stop_monitor.set()
        thread = self._monitor_thread
        if thread is not None:
            thread.join(timeout=5)
            if not thread.is_alive():
                with self._lock:
                    if self._monitor_thread is thread:
                        self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """Background loop that monitors AnkiConnect and retries sync."""
        try:
            while not self._stop_monitor.is_set():
                # Check if there are pending cards
                with self._lock:
                    has_pending = len(self._cards) > 0

                if has_pending:
                    # Try to sync
                    success, failed = self.sync_now()
                    if success > 0:
                        # Cards were synced successfully
                        pass

                # Wait for next retry interval or until stopped
                self._stop_monitor.wait(timeout=self.retry_interval)
        finally:
            with self._lock:
                if threading.current_thread() is self._monitor_thread:
                    self._monitor_thread = None

    def clear_queue(self) -> int:
        """
        Clear all cards from the queue.

        Returns:
            Number of cards cleared
        """
        with self._lock:
            count = len(self._cards)
            self._cards = []
            self._save_queue()
            return count

    def __len__(self) -> int:
        """Return the number of cards in the queue."""
        with self._lock:
            return len(self._cards)

    def __enter__(self) -> "OfflineSyncQueue":
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop_auto_sync()
