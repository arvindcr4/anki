#!/usr/bin/env python3
"""
Local Anki Server — AnkiConnect-compatible API backed by SQLite.

Zero dependencies beyond Python 3.8+ stdlib.
Implements the subset of AnkiConnect used by the Anki Bookmarks extension.

Usage:
    python anki_server.py                    # default port 8765
    python anki_server.py --port 9000        # custom port
    python anki_server.py --db cards.db      # custom database file
    python anki_server.py --export deck.apkg # export all cards to .apkg
"""

import argparse
import hashlib
import json
import os
import random
import sqlite3
import struct
import time
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.request import Request, urlopen
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class CardDatabase:
    def __init__(self, db_path="anki_cards.db"):
        self.db_path = db_path
        self.lock = Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                fields TEXT NOT NULL,  -- JSON array of field names
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                model_id INTEGER NOT NULL,
                deck_id INTEGER NOT NULL,
                fields TEXT NOT NULL,   -- JSON object {fieldName: value}
                tags TEXT DEFAULT '[]', -- JSON array
                checksum TEXT NOT NULL, -- for duplicate detection
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (model_id) REFERENCES models(id),
                FOREIGN KEY (deck_id) REFERENCES decks(id)
            );

            CREATE INDEX IF NOT EXISTS idx_notes_checksum ON notes(checksum);
            CREATE INDEX IF NOT EXISTS idx_notes_deck ON notes(deck_id);
        """)

        # Ensure the "Basic" model exists
        self.conn.execute("""
            INSERT OR IGNORE INTO models (id, name, fields)
            VALUES (1, 'Basic', '["Front", "Back"]')
        """)
        self.conn.commit()

    def _generate_id(self):
        """Generate a unique ID similar to Anki's note IDs (timestamp-based)."""
        return int(time.time() * 1000) + random.randint(0, 999)

    def _note_checksum(self, fields, deck_id):
        """Create a checksum for duplicate detection within a deck."""
        raw = json.dumps(fields, sort_keys=True) + str(deck_id)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # -- Deck operations --

    def deck_names(self):
        with self.lock:
            rows = self.conn.execute("SELECT name FROM decks ORDER BY name").fetchall()
            return [r["name"] for r in rows]

    def deck_names_and_ids(self):
        with self.lock:
            rows = self.conn.execute("SELECT id, name FROM decks ORDER BY name").fetchall()
            return {r["name"]: r["id"] for r in rows}

    def create_deck(self, name):
        with self.lock:
            deck_id = self._generate_id()
            try:
                self.conn.execute(
                    "INSERT INTO decks (id, name) VALUES (?, ?)",
                    (deck_id, name),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                row = self.conn.execute(
                    "SELECT id FROM decks WHERE name = ?", (name,)
                ).fetchone()
                deck_id = row["id"]
            return deck_id

    def delete_decks(self, deck_ids):
        with self.lock:
            for did in deck_ids:
                self.conn.execute("DELETE FROM notes WHERE deck_id = ?", (did,))
                self.conn.execute("DELETE FROM decks WHERE id = ?", (did,))
            self.conn.commit()

    # -- Model operations --

    def model_names(self):
        with self.lock:
            rows = self.conn.execute("SELECT name FROM models ORDER BY name").fetchall()
            return [r["name"] for r in rows]

    def _ensure_model(self, name, fields):
        row = self.conn.execute("SELECT id FROM models WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        model_id = self._generate_id()
        self.conn.execute(
            "INSERT INTO models (id, name, fields) VALUES (?, ?, ?)",
            (model_id, name, json.dumps(fields)),
        )
        return model_id

    # -- Note operations --

    def add_notes(self, notes):
        """Add multiple notes. Returns list of IDs (None for duplicates)."""
        results = []
        with self.lock:
            for note in notes:
                deck_name = note.get("deckName", "Default")
                model_name = note.get("modelName", "Basic")
                fields = note.get("fields", {})
                tags = note.get("tags", [])
                options = note.get("options", {})

                # Ensure deck exists
                deck_row = self.conn.execute(
                    "SELECT id FROM decks WHERE name = ?", (deck_name,)
                ).fetchone()
                if not deck_row:
                    deck_id = self._generate_id()
                    self.conn.execute(
                        "INSERT INTO decks (id, name) VALUES (?, ?)",
                        (deck_id, deck_name),
                    )
                else:
                    deck_id = deck_row["id"]

                # Ensure model exists
                field_names = list(fields.keys())
                model_id = self._ensure_model(model_name, field_names)

                # Check for duplicates
                allow_dupe = options.get("allowDuplicate", False)
                scope = options.get("duplicateScope", "deck")
                checksum = self._note_checksum(fields, deck_id if scope == "deck" else 0)

                if not allow_dupe:
                    if scope == "deck":
                        existing = self.conn.execute(
                            "SELECT id FROM notes WHERE checksum = ? AND deck_id = ?",
                            (checksum, deck_id),
                        ).fetchone()
                    else:
                        existing = self.conn.execute(
                            "SELECT id FROM notes WHERE checksum = ?",
                            (checksum,),
                        ).fetchone()
                    if existing:
                        results.append(None)
                        continue

                note_id = self._generate_id()
                self.conn.execute(
                    "INSERT INTO notes (id, model_id, deck_id, fields, tags, checksum) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        note_id,
                        model_id,
                        deck_id,
                        json.dumps(fields),
                        json.dumps(tags),
                        checksum,
                    ),
                )
                results.append(note_id)

            self.conn.commit()
        return results

    def find_notes(self, query=""):
        with self.lock:
            if query.startswith("deck:"):
                deck_name = query[5:].strip().strip('"')
                rows = self.conn.execute(
                    "SELECT n.id FROM notes n JOIN decks d ON n.deck_id = d.id "
                    "WHERE d.name = ?",
                    (deck_name,),
                ).fetchall()
            elif query.startswith("tag:"):
                tag = query[4:].strip()
                rows = self.conn.execute("SELECT id, tags FROM notes").fetchall()
                rows = [r for r in rows if tag in json.loads(r["tags"])]
            elif query:
                rows = self.conn.execute(
                    "SELECT id FROM notes WHERE fields LIKE ?",
                    (f"%{query}%",),
                ).fetchall()
            else:
                rows = self.conn.execute("SELECT id FROM notes").fetchall()
            return [r["id"] for r in rows]

    def notes_info(self, note_ids):
        with self.lock:
            results = []
            for nid in note_ids:
                row = self.conn.execute(
                    "SELECT n.*, d.name as deck_name, m.name as model_name "
                    "FROM notes n "
                    "JOIN decks d ON n.deck_id = d.id "
                    "JOIN models m ON n.model_id = m.id "
                    "WHERE n.id = ?",
                    (nid,),
                ).fetchone()
                if row:
                    results.append({
                        "noteId": row["id"],
                        "modelName": row["model_name"],
                        "deckName": row["deck_name"],
                        "fields": {
                            k: {"value": v, "order": i}
                            for i, (k, v) in enumerate(json.loads(row["fields"]).items())
                        },
                        "tags": json.loads(row["tags"]),
                    })
            return results

    def get_num_cards_today(self):
        with self.lock:
            cutoff = time.time() - 86400
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM notes WHERE created_at > ?",
                (cutoff,),
            ).fetchone()
            return row["cnt"]

    def stats(self):
        with self.lock:
            decks = self.conn.execute("SELECT COUNT(*) as cnt FROM decks").fetchone()["cnt"]
            notes = self.conn.execute("SELECT COUNT(*) as cnt FROM notes").fetchone()["cnt"]
            return {"decks": decks, "notes": notes}

    # -- Export --

    def export_apkg(self, deck_name=None):
        with self.lock:
            if deck_name:
                notes = self.conn.execute(
                    "SELECT n.*, d.name as deck_name FROM notes n "
                    "JOIN decks d ON n.deck_id = d.id WHERE d.name = ?",
                    (deck_name,),
                ).fetchall()
            else:
                notes = self.conn.execute(
                    "SELECT n.*, d.name as deck_name FROM notes n "
                    "JOIN decks d ON n.deck_id = d.id"
                ).fetchall()

        return self._build_apkg(notes)

    def _build_apkg(self, notes):
        """Build a minimal .apkg from note rows."""
        # Create an in-memory SQLite db for the collection
        buf = BytesIO()
        col_db = sqlite3.connect(":memory:")

        # Anki collection schema (minimal)
        col_db.executescript("""
            CREATE TABLE col (
                id INTEGER PRIMARY KEY,
                crt INTEGER NOT NULL,
                mod INTEGER NOT NULL,
                scm INTEGER NOT NULL,
                ver INTEGER NOT NULL,
                dty INTEGER NOT NULL,
                usn INTEGER NOT NULL,
                ls INTEGER NOT NULL,
                conf TEXT NOT NULL,
                models TEXT NOT NULL,
                decks TEXT NOT NULL,
                dconf TEXT NOT NULL,
                tags TEXT NOT NULL
            );
            CREATE TABLE notes (
                id INTEGER PRIMARY KEY,
                guid TEXT NOT NULL,
                mid INTEGER NOT NULL,
                mod INTEGER NOT NULL,
                usn INTEGER NOT NULL,
                tags TEXT NOT NULL,
                flds TEXT NOT NULL,
                sfld TEXT NOT NULL,
                csum INTEGER NOT NULL,
                flags INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY,
                nid INTEGER NOT NULL,
                did INTEGER NOT NULL,
                ord INTEGER NOT NULL,
                mod INTEGER NOT NULL,
                usn INTEGER NOT NULL,
                type INTEGER NOT NULL,
                queue INTEGER NOT NULL,
                due INTEGER NOT NULL,
                ivl INTEGER NOT NULL,
                factor INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                lapses INTEGER NOT NULL,
                left INTEGER NOT NULL,
                odue INTEGER NOT NULL,
                odid INTEGER NOT NULL,
                flags INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE revlog (
                id INTEGER PRIMARY KEY,
                cid INTEGER NOT NULL,
                usn INTEGER NOT NULL,
                ease INTEGER NOT NULL,
                ivl INTEGER NOT NULL,
                lastIvl INTEGER NOT NULL,
                factor INTEGER NOT NULL,
                time INTEGER NOT NULL,
                type INTEGER NOT NULL
            );
            CREATE TABLE graves (
                usn INTEGER NOT NULL,
                oid INTEGER NOT NULL,
                type INTEGER NOT NULL
            );
        """)

        now = int(time.time())
        model_id = 1609459200000  # fixed model ID
        deck_ids = {}
        deck_counter = 1609459200001

        # Collect unique decks
        for note in notes:
            dname = note["deck_name"]
            if dname not in deck_ids:
                deck_ids[dname] = deck_counter
                deck_counter += 1

        if not deck_ids:
            deck_ids["Default"] = deck_counter

        # Build models JSON
        models = {
            str(model_id): {
                "id": model_id,
                "name": "Basic",
                "type": 0,
                "mod": now,
                "usn": -1,
                "sortf": 0,
                "did": list(deck_ids.values())[0],
                "tmpls": [{
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": "{{Front}}",
                    "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
                    "bqfmt": "",
                    "bafmt": "",
                    "did": None,
                    "bfont": "",
                    "bsize": 0,
                }],
                "flds": [
                    {"name": "Front", "ord": 0, "sticky": False,
                     "rtl": False, "font": "Arial", "size": 20, "media": []},
                    {"name": "Back", "ord": 1, "sticky": False,
                     "rtl": False, "font": "Arial", "size": 20, "media": []},
                ],
                "css": ".card { font-family: arial; font-size: 20px; "
                       "text-align: center; color: black; background-color: white; }",
                "latexPre": "",
                "latexPost": "",
                "latexsvg": False,
                "req": [[0, "all", [0]]],
                "tags": [],
                "vers": [],
            }
        }

        # Build decks JSON
        decks = {}
        for dname, did in deck_ids.items():
            decks[str(did)] = {
                "id": did,
                "name": dname,
                "mod": now,
                "usn": -1,
                "lrnToday": [0, 0],
                "revToday": [0, 0],
                "newToday": [0, 0],
                "timeToday": [0, 0],
                "collapsed": False,
                "desc": "",
                "dyn": 0,
                "conf": 1,
                "extendNew": 10,
                "extendRev": 50,
            }

        # Default deck config
        dconf = {
            "1": {
                "id": 1, "name": "Default", "mod": 0, "usn": 0,
                "maxTaken": 60, "autoplay": True, "timer": 0,
                "replayq": True, "dyn": False,
                "new": {"delays": [1, 10], "ints": [1, 4, 0],
                        "initialFactor": 2500, "order": 1,
                        "perDay": 20, "bury": False},
                "rev": {"perDay": 200, "ease4": 1.3, "ivlFct": 1,
                        "maxIvl": 36500, "bury": False,
                        "hardFactor": 1.2},
                "lapse": {"delays": [10], "mult": 0, "minInt": 1,
                          "leechFails": 8, "leechAction": 0},
            }
        }

        # Insert collection metadata
        col_db.execute(
            "INSERT INTO col VALUES (1,?,?,?,11,0,-1,0,?,?,?,?,?)",
            (now, now, now * 1000,
             json.dumps({}), json.dumps(models), json.dumps(decks),
             json.dumps(dconf), json.dumps({})),
        )

        # Insert notes and cards
        card_id = now * 1000
        for note in notes:
            fields = json.loads(note["fields"])
            tags_list = json.loads(note["tags"])
            front = fields.get("Front", "")
            back = fields.get("Back", "")
            flds = front + "\x1f" + back
            sfld = front
            csum = int(hashlib.sha1(sfld.encode()).hexdigest()[:8], 16)
            guid = hashlib.sha1(str(note["id"]).encode()).hexdigest()[:10]
            tags_str = " ".join(tags_list)
            did = deck_ids.get(note["deck_name"], list(deck_ids.values())[0])

            col_db.execute(
                "INSERT INTO notes VALUES (?,?,?,?,?,' ? ',?,?,?,0,'')",
                (note["id"], guid, model_id, now, -1, flds, sfld, csum),
            )
            # Fix: tags need to be in the query properly
            col_db.execute(
                "UPDATE notes SET tags = ? WHERE id = ?",
                (tags_str, note["id"]),
            )

            col_db.execute(
                "INSERT INTO cards VALUES (?,?,?,0,?,?,"
                "0,0,?,0,0,0,0,0,0,0,0,'')",
                (card_id, note["id"], did, now, -1, note["id"]),
            )
            card_id += 1

        col_db.commit()

        # Dump to bytes
        for line in col_db.iterdump():
            pass  # ensure all data is flushed

        # Save to a temp file, read back
        tmp_path = Path(self.db_path).parent / "_export_tmp.anki2"
        backup_conn = sqlite3.connect(str(tmp_path))
        col_db.backup(backup_conn)
        backup_conn.close()
        col_db.close()

        with open(tmp_path, "rb") as f:
            col_bytes = f.read()
        tmp_path.unlink()

        # Create .apkg (zip with collection.anki2 + media file)
        apkg_buf = BytesIO()
        with zipfile.ZipFile(apkg_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("collection.anki2", col_bytes)
            zf.writestr("media", "{}")
        apkg_buf.seek(0)
        return apkg_buf.read()


# ---------------------------------------------------------------------------
# Sync: push cards from our DB → Anki desktop via AnkiConnect
# ---------------------------------------------------------------------------

class AnkiDesktopSync:
    """Push cards from our local DB to Anki desktop via AnkiConnect."""

    def __init__(self, anki_url="http://localhost:8765"):
        self.anki_url = anki_url

    def _invoke(self, action, params=None):
        payload = {"action": action, "version": 6}
        if params:
            payload["params"] = params
        data = json.dumps(payload).encode()
        req = Request(self.anki_url, data=data,
                      headers={"Content-Type": "application/json"})
        resp = json.loads(urlopen(req, timeout=10).read())
        if resp.get("error"):
            raise RuntimeError(f"AnkiConnect: {resp['error']}")
        return resp.get("result")

    def ping(self):
        try:
            ver = self._invoke("version")
            return True, ver
        except Exception as e:
            return False, str(e)

    def sync(self, db):
        """Push all cards from our DB to Anki desktop. Returns stats."""
        ok, info = self.ping()
        if not ok:
            raise ConnectionError(
                f"Cannot reach Anki desktop at {self.anki_url}. "
                f"Is Anki running with AnkiConnect installed? ({info})"
            )

        stats = {"decks_created": 0, "cards_pushed": 0, "duplicates": 0, "errors": []}

        # Get all decks and notes from our DB
        deck_names = db.deck_names()
        for deck_name in deck_names:
            # Ensure deck exists in Anki
            try:
                self._invoke("createDeck", {"deck": deck_name})
                stats["decks_created"] += 1
            except Exception:
                pass  # deck may already exist

            # Get notes for this deck
            note_ids = db.find_notes(f"deck:{deck_name}")
            if not note_ids:
                continue

            notes_info = db.notes_info(note_ids)

            # Build AnkiConnect notes
            anki_notes = []
            for note in notes_info:
                fields = {k: v["value"] for k, v in note["fields"].items()}
                anki_notes.append({
                    "deckName": deck_name,
                    "modelName": note["modelName"],
                    "fields": fields,
                    "options": {
                        "allowDuplicate": False,
                        "duplicateScope": "deck",
                    },
                    "tags": note["tags"],
                })

            # Push in batches of 50
            for i in range(0, len(anki_notes), 50):
                batch = anki_notes[i:i + 50]
                try:
                    results = self._invoke("addNotes", {"notes": batch})
                    for r in results:
                        if r is not None:
                            stats["cards_pushed"] += 1
                        else:
                            stats["duplicates"] += 1
                except Exception as e:
                    stats["errors"].append(f"Batch {i//50}: {e}")

        return stats


# ---------------------------------------------------------------------------
# AnkiConnect-compatible HTTP handler
# ---------------------------------------------------------------------------

class AnkiHandler(BaseHTTPRequestHandler):
    db: CardDatabase = None  # set by server setup

    def log_message(self, fmt, *args):
        # Quieter logging
        print(f"[anki-server] {args[0] if args else ''}")

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        """Health check / stats / sync / export endpoints."""
        if self.path == "/health":
            self._json_response({"status": "ok", **self.db.stats()})
        elif self.path.startswith("/export"):
            self._handle_export()
        else:
            self._json_response({"status": "ok", "message": "Anki Local Server"})

    def do_POST(self):
        """AnkiConnect protocol handler."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._json_response({"error": "Invalid JSON", "result": None})
            return

        action = body.get("action", "")
        params = body.get("params", {})
        result = None
        error = None

        try:
            result = self._dispatch(action, params)
        except Exception as e:
            error = str(e)

        self._json_response({"result": result, "error": error})

    def _dispatch(self, action, params):
        handlers = {
            "version": lambda p: 6,
            "deckNames": lambda p: self.db.deck_names(),
            "deckNamesAndIds": lambda p: self.db.deck_names_and_ids(),
            "createDeck": lambda p: self.db.create_deck(p["deck"]),
            "deleteDecks": lambda p: self.db.delete_decks(p.get("decks", [])),
            "modelNames": lambda p: self.db.model_names(),
            "addNote": lambda p: self._add_single_note(p["note"]),
            "addNotes": lambda p: self.db.add_notes(p["notes"]),
            "findNotes": lambda p: self.db.find_notes(p.get("query", "")),
            "notesInfo": lambda p: self.db.notes_info(p.get("notes", [])),
            "getNumCardsReviewedToday": lambda p: self.db.get_num_cards_today(),
            "sync": lambda p: None,  # no-op
            "multi": lambda p: self._multi(p.get("actions", [])),
        }

        handler = handlers.get(action)
        if not handler:
            raise ValueError(f"Unsupported action: {action}")
        return handler(params)

    def _add_single_note(self, note):
        results = self.db.add_notes([note])
        return results[0]

    def _multi(self, actions):
        results = []
        for act in actions:
            try:
                r = self._dispatch(act.get("action", ""), act.get("params", {}))
                results.append({"result": r, "error": None})
            except Exception as e:
                results.append({"result": None, "error": str(e)})
        return results

    def _handle_sync_to_anki(self):
        """GET /sync-to-anki?url=http://localhost:8765 → push cards to Anki desktop."""
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        anki_url = query.get("url", ["http://localhost:8765"])[0]

        try:
            syncer = AnkiDesktopSync(anki_url)
            stats = syncer.sync(self.db)
            self._json_response({"status": "ok", **stats})
        except Exception as e:
            self._json_response({"status": "error", "error": str(e)})

    def _handle_export(self):
        """GET /export?deck=DeckName → .apkg download."""
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        deck_name = query.get("deck", [None])[0]

        apkg_data = self.db.export_apkg(deck_name)
        filename = f"{deck_name or 'all_cards'}.apkg"

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(apkg_data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(apkg_data)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        # WARNING: Only allow localhost origins to prevent cross-site request forgery
        origin = self.headers.get("Origin", "")
        allowed_origins = {
            "http://localhost",
            "http://127.0.0.1",
            "https://localhost",
            "https://127.0.0.1",
        }
        # Match origin with any port
        origin_base = origin.rsplit(":", 1)[0] if "://" in origin else origin
        if origin_base in allowed_origins or origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "http://localhost:8765")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Local Anki Server (AnkiConnect-compatible)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--db", default="anki_cards.db", help="SQLite database path")
    parser.add_argument("--export", metavar="FILE", help="Export all cards to .apkg and exit")
    args = parser.parse_args()

    db = CardDatabase(args.db)

    if args.export:
        data = db.export_apkg()
        with open(args.export, "wb") as f:
            f.write(data)
        stats = db.stats()
        print(f"Exported {stats['notes']} notes from {stats['decks']} decks → {args.export}")
        return

    AnkiHandler.db = db
    server = HTTPServer((args.host, args.port), AnkiHandler)
    stats = db.stats()
    print(f"AnkiConnect Server running on http://{args.host}:{args.port}")
    print(f"Database: {os.path.abspath(args.db)} ({stats['notes']} notes, {stats['decks']} decks)")
    print(f"Endpoints:")
    print(f"  POST /          — AnkiConnect API (no auth)")
    print(f"  GET  /health    — server stats")
    print(f"  GET  /export    — download .apkg")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()