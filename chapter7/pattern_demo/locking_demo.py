"""
locking_demo.py -- pessimistic vs optimistic locking in Python.

Story: an event has 2 seats. 5 students click "Book" at the same moment.
A correct system confirms exactly 2 bookings and leaves seats_left = 0.

Needs PostgreSQL (SELECT ... FOR UPDATE is not supported by SQLite):
    docker run -d --name encore-db -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=encore \
        -p 5432:5432 postgres:16
    pip install sqlalchemy "psycopg[binary]"
    python locking_demo.py
"""
import threading
import time

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql+psycopg://postgres:pw@localhost:5432/encore"
engine = create_engine(DATABASE_URL)

EVENT_ID = 1
THINK_TIME = 0.05  # pause between "read" and "write", to make races likely


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def reset_database(seats=2):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS reservations"))
        conn.execute(text("DROP TABLE IF EXISTS events"))
        conn.execute(text("""
            CREATE TABLE events (
                id         INTEGER PRIMARY KEY,
                seats_left INTEGER NOT NULL,
                version    INTEGER NOT NULL DEFAULT 0
            )"""))
        conn.execute(text("""
            CREATE TABLE reservations (
                event_id INTEGER NOT NULL REFERENCES events(id),
                student  TEXT    NOT NULL,
                PRIMARY KEY (event_id, student)
            )"""))
        conn.execute(text("INSERT INTO events (id, seats_left) VALUES (:id, :s)"),
                     {"id": EVENT_ID, "s": seats})


def write_booking(conn, student, extra_where="", params=None):
    """The two writes of a booking. Returns how many event rows were updated."""
    result = conn.execute(
        text("UPDATE events SET seats_left = seats_left - 1, version = version + 1 "
             "WHERE id = :id " + extra_where),
        {"id": EVENT_ID, **(params or {})})
    if result.rowcount == 1:
        conn.execute(
            text("INSERT INTO reservations (event_id, student) VALUES (:id, :s)"),
            {"id": EVENT_ID, "s": student})
    return result.rowcount


# ---------------------------------------------------------------------------
# For contrast: NO protection (read, think, write)
# ---------------------------------------------------------------------------
def book_unsafe(student):
    with engine.begin() as conn:
        seats = conn.execute(text("SELECT seats_left FROM events WHERE id = :id"),
                             {"id": EVENT_ID}).scalar_one()
        if seats <= 0:
            return False
        time.sleep(THINK_TIME)           # others read the same "seats" meanwhile
        write_booking(conn, student)
        return True


# ---------------------------------------------------------------------------
# Pattern 1: PESSIMISTIC -- lock the row, then read, check, write
# ---------------------------------------------------------------------------
def book_pessimistic(student):
    with engine.begin() as conn:                         # BEGIN
        seats = conn.execute(
            text("SELECT seats_left FROM events WHERE id = :id FOR UPDATE"),
            {"id": EVENT_ID},
        ).scalar_one()                                   # read + lock (others wait)

        if seats <= 0:
            return False                                 # sold out; block ends,
                                                         # lock released
        time.sleep(THINK_TIME)                           # safe: row is locked
        write_booking(conn, student)
        return True                                      # COMMIT, lock released


# ---------------------------------------------------------------------------
# Pattern 2: OPTIMISTIC -- read without locking, write only if unchanged
# ---------------------------------------------------------------------------
retry_count = 0
retry_lock = threading.Lock()


def book_optimistic(student, max_attempts=10):
    global retry_count
    for attempt in range(1, max_attempts + 1):
        # 1. Read the data AND its version. No lock, no open transaction.
        with engine.connect() as conn:
            seats, version = conn.execute(
                text("SELECT seats_left, version FROM events WHERE id = :id"),
                {"id": EVENT_ID},
            ).one()

        # 2. Decide, using what we read.
        if seats <= 0:
            return False
        time.sleep(THINK_TIME)                           # others may write now

        # 3. Write ONLY if the version is still the one we read.
        with engine.begin() as conn:
            updated = write_booking(conn, student,
                                    "AND version = :v", {"v": version})
            if updated == 1:
                return True                              # we won; COMMIT

        # 4. updated == 0: someone changed the row. Start over.
        with retry_lock:
            retry_count += 1
    raise RuntimeError(f"{student}: gave up after {max_attempts} attempts")


# ---------------------------------------------------------------------------
# Race: 5 students click at the same moment
# ---------------------------------------------------------------------------
def race(book, label):
    global retry_count
    retry_count = 0
    reset_database(seats=2)
    students = ["kim", "ana", "raj", "lee", "tom"]
    results = {}
    start = threading.Barrier(len(students))

    def click(name):
        start.wait()                     # everyone starts together
        results[name] = book(name)

    threads = [threading.Thread(target=click, args=(s,)) for s in students]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with engine.connect() as conn:
        seats = conn.execute(text("SELECT seats_left FROM events WHERE id = :id"),
                             {"id": EVENT_ID}).scalar_one()
        rows = conn.execute(text("SELECT count(*) FROM reservations")).scalar_one()
    confirmed = sorted(n for n, ok in results.items() if ok)
    verdict = "correct" if len(confirmed) == 2 and seats == 0 else "WRONG"
    print(f"{label:<12} confirmed={confirmed}  seats_left={seats}  "
          f"rows={rows}  retries={retry_count}  -> {verdict}")


if __name__ == "__main__":
    race(book_unsafe, "unsafe")
    race(book_pessimistic, "pessimistic")
    race(book_optimistic, "optimistic")
