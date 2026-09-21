CREATE TABLE events (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, capacity INTEGER NOT NULL);
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id),
    status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE idempotency (
    key TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
    ok BOOLEAN NOT NULL, code TEXT, value_json TEXT);
CREATE TABLE counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
