# schema.py -- one tiny database shared by every demo in this folder.
# Same shape as Encore's: events hold the FIXED capacity; seats left is
# COMPUTED from confirmed reservations (one home for the rule, Chapter 5).
import sqlite3

SCHEMA = """
CREATE TABLE events (
    id       TEXT PRIMARY KEY,
    title    TEXT NOT NULL,
    capacity INTEGER NOT NULL
);
CREATE TABLE reservations (
    id       TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id),
    status   TEXT NOT NULL
);
CREATE TABLE idempotency (
    key          TEXT PRIMARY KEY,
    reservation  TEXT NOT NULL
);
"""

SEED = [("ev_101", "Jazz Ensemble: Fall Concert", 42),
        ("ev_103", "Film Society: Friday Screening", 2)]


def fresh_db(trace=None):
    """A brand-new in-memory database, seeded. Pass trace=list to record
    every SQL statement sent (so patterns can be MEASURED, not asserted)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO events VALUES (?,?,?)", SEED)
    conn.commit()
    if trace is not None:
        conn.set_trace_callback(trace.append)
    return conn


class SoldOut(Exception):
    pass
