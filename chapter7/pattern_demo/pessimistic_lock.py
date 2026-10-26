"""
pessimistic_lock.py -- Chapter 7, Section 7.1: pessimistic locking.

Five students try to book an event with 2 seats at the same moment.
book_pessimistic() locks the event row with SELECT ... FOR UPDATE, so the
bookings pass through the row one at a time: exactly 2 succeed.

Requires PostgreSQL (SQLite does not support SELECT ... FOR UPDATE):
    docker run -d --name encore-db -e POSTGRES_PASSWORD=pw \
        -e POSTGRES_DB=encore -p 5432:5432 postgres:16
    pip install sqlalchemy "psycopg[binary]"
    python pessimistic_lock.py
"""
import threading

from sqlalchemy import create_engine, text

# The engine is a connection factory: it knows where the database
# is and how to reach it. No connection is open yet.
engine = create_engine(
    "postgresql+psycopg://postgres:pw@localhost:5432/encore")


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
# Pessimistic locking: one transaction, lock first (Listing 7.1)
# ---------------------------------------------------------------------
def book_pessimistic(event_id, student):
    with engine.begin() as conn:                  # BEGIN
        # Read and lock the row; rivals wait at this statement.
        seats = conn.execute(
            text("SELECT seats_left FROM events "
                 "WHERE id = :id FOR UPDATE"),
            {"id": event_id},
        ).scalar_one()

        if seats <= 0:
            # Sold out: leaving the block ends the transaction
            # and releases the lock.
            return False

        conn.execute(
            text("UPDATE events SET seats_left = seats_left - 1 "
                 "WHERE id = :id"),
            {"id": event_id})
        conn.execute(
            text("INSERT INTO reservations (event_id, student) "
                 "VALUES (:id, :s)"),
            {"id": event_id, "s": student})
        return True                          # COMMIT; lock released


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
        seats = conn.execute(
            text("SELECT seats_left FROM events WHERE id = :id"),
            {"id": event_id}).scalar_one()
        rows = conn.execute(
            text("SELECT count(*) FROM reservations "
                 "WHERE event_id = :id"),
            {"id": event_id}).scalar_one()
    return seats, rows


if __name__ == "__main__":
    reset_database(seats=2)
    confirmed = race(book_pessimistic)
    seats, rows = show_state()
    ok = len(confirmed) == 2 and seats == 0 and rows == 2
    print(f"pessimistic  confirmed: {' '.join(confirmed)}  "
          f"seats_left={seats}  reservations={rows}  "
          f"{'correct' if ok else 'WRONG'}")
