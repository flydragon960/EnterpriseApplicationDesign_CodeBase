"""
optimistic_lock.py -- Chapter 7, Section 7.1: optimistic locking.

Five students try to book an event with 2 seats at the same moment.
book_optimistic() reads without locking, then writes only if the row's
version is unchanged; on a conflict it re-reads and retries. Exactly 2
bookings succeed.

Runs on PostgreSQL:
    docker run -d --name encore-db -e POSTGRES_PASSWORD=pw \
        -e POSTGRES_DB=encore -p 5432:5432 postgres:16
    pip install sqlalchemy "psycopg[binary]"
    python optimistic_lock.py

It uses only standard SQL, so it also runs on SQLite: switch the
DATABASE_URL below and nothing else changes.
"""
import threading

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql+psycopg://postgres:pw@localhost:5432/encore"
# DATABASE_URL = "sqlite:///encore.db"

# The engine is a connection factory: it knows where the database
# is and how to reach it. No connection is open yet.
engine = create_engine(DATABASE_URL)


# ---------------------------------------------------------------------
# Setup: the schema from Section 7.1
# ---------------------------------------------------------------------
def reset_database(seats=2):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS reservations"))
        conn.execute(text("DROP TABLE IF EXISTS events"))
        conn.execute(text("""
            CREATE TABLE events (
                id         INTEGER PRIMARY KEY,
                name       TEXT    NOT NULL,
                seats_left INTEGER NOT NULL CHECK (seats_left >= 0),
                version    INTEGER NOT NULL DEFAULT 0
            )"""))
        conn.execute(text("""
            CREATE TABLE reservations (
                event_id INTEGER NOT NULL REFERENCES events(id),
                student  TEXT    NOT NULL,
                PRIMARY KEY (event_id, student)
            )"""))
        conn.execute(
            text("INSERT INTO events (id, name, seats_left) "
                 "VALUES (1, 'Jazz Night', :s)"),
            {"s": seats})


# ---------------------------------------------------------------------
# Optimistic locking: one loop, retry on conflict (Listing 7.2)
# ---------------------------------------------------------------------
class TooManyRetries(Exception):
    pass


def book_optimistic(event_id, student, max_attempts=10):
    for attempt in range(max_attempts):
        # 1. Read the data and its version: no lock, done at once.
        with engine.connect() as conn:
            seats, version = conn.execute(
                text("SELECT seats_left, version FROM events "
                     "WHERE id = :id"),
                {"id": event_id},
            ).one()

        # 2. Decide, using what we read.
        if seats <= 0:
            return False

        # 3. Write only if the version is still the one we read.
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE events "
                     "SET seats_left = seats_left - 1, "
                     "    version = version + 1 "
                     "WHERE id = :id AND version = :v"),
                {"id": event_id, "v": version})
            if result.rowcount == 1:          # version matched: we won
                conn.execute(
                    text("INSERT INTO reservations "
                         "(event_id, student) VALUES (:id, :s)"),
                    {"id": event_id, "s": student})
                return True                   # COMMIT

        # 4. rowcount == 0: someone changed the row first.
        #    Go back to step 1 and re-read.
    raise TooManyRetries(
        f"{student}: gave up after {max_attempts} attempts")


# ---------------------------------------------------------------------
# Concurrency test: five students, two seats (Listing 7.3)
# ---------------------------------------------------------------------
def race(book, event_id=1):
    students = ["kim", "ana", "raj", "lee", "tom"]
    results = {}
    start = threading.Barrier(len(students))

    def click(name):
        start.wait()                 # all five start together
        results[name] = book(event_id, name)

    threads = [threading.Thread(target=click, args=(s,))
               for s in students]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(name for name, ok in results.items() if ok)


def show_state(event_id=1):
    with engine.connect() as conn:
        seats, version = conn.execute(
            text("SELECT seats_left, version FROM events WHERE id = :id"),
            {"id": event_id}).one()
        rows = conn.execute(
            text("SELECT count(*) FROM reservations "
                 "WHERE event_id = :id"),
            {"id": event_id}).scalar_one()
    return seats, version, rows


if __name__ == "__main__":
    reset_database(seats=2)
    confirmed = race(book_optimistic)
    seats, version, rows = show_state()
    ok = len(confirmed) == 2 and seats == 0 and rows == 2
    print(f"optimistic   confirmed: {' '.join(confirmed)}  "
          f"seats_left={seats}  version={version}  reservations={rows}  "
          f"{'correct' if ok else 'WRONG'}")
