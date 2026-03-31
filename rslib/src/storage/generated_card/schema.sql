-- Schema for generated flashcards storage
CREATE TABLE IF NOT EXISTS generated_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  front TEXT NOT NULL,
  back TEXT NOT NULL,
  source_url TEXT,
  source_type TEXT NOT NULL DEFAULT 'text',
  created_at INTEGER NOT NULL,
  sync_status TEXT NOT NULL DEFAULT 'pending',
  tags TEXT NOT NULL DEFAULT ''
);
-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sync_status ON generated_cards(sync_status);
CREATE INDEX IF NOT EXISTS idx_source_type ON generated_cards(source_type);
CREATE INDEX IF NOT EXISTS idx_created_at ON generated_cards(created_at);