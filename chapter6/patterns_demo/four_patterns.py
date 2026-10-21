# four_patterns.py -- Slide "Four ways to load and save an event", runnable.
# All four patterns do the SAME job: load ev_103 (capacity 2), reserve a
# seat, write it back. Watch WHERE the rule lives and WHO knows SQL.
from schema import fresh_db, SoldOut


# ---------------------------------------------------------------------------
# 1. TABLE DATA GATEWAY -- one object for the whole table; returns raw rows.
#    The rules live outside, in a Transaction Script.
# ---------------------------------------------------------------------------
class EventsGateway:                        # ONE object, whole events table
    def __init__(self, conn):
        self.conn = conn

    def find(self, event_id):               # -> a raw row, not an Event
        return self.conn.execute(
            "SELECT id, title, capacity FROM events WHERE id = ?",
            (event_id,)).fetchone()


class ReservationsGateway:                  # ONE object, whole reservations table
    def __init__(self, conn):
        self.conn = conn

    def count_confirmed(self, event_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM reservations "
            "WHERE event_id = ? AND status = 'confirmed'",
            (event_id,)).fetchone()[0]

    def insert(self, res_id, event_id, status):
        self.conn.execute("INSERT INTO reservations VALUES (?, ?, ?)",
                          (res_id, event_id, status))


def reserve_tdg(conn, event_id, res_id):    # Transaction Script: rule HERE
    events, reservations = EventsGateway(conn), ReservationsGateway(conn)
    with conn:
        row = events.find(event_id)
        if row["capacity"] - reservations.count_confirmed(event_id) <= 0:
            raise SoldOut(event_id)
        reservations.insert(res_id, event_id, "confirmed")


# ---------------------------------------------------------------------------
# 2. ROW DATA GATEWAY -- one object per row; holds the row's data, no rules.
#    The rules still live outside, in a Transaction Script.
# ---------------------------------------------------------------------------
class EventRowGateway:                      # ONE object = ONE events row
    def __init__(self, conn, id, title, capacity):
        self.conn, self.id, self.title, self.capacity = conn, id, title, capacity

    @classmethod
    def load(cls, conn, event_id):          # rebuild an object from a row
        r = conn.execute("SELECT id, title, capacity FROM events WHERE id = ?",
                         (event_id,)).fetchone()
        return cls(conn, r["id"], r["title"], r["capacity"]) if r else None

    def confirmed_count(self):              # a finder -- data access, not a rule
        return self.conn.execute(
            "SELECT COUNT(*) FROM reservations "
            "WHERE event_id = ? AND status = 'confirmed'", (self.id,)).fetchone()[0]


class ReservationRowGateway:                # ONE object = ONE reservations row
    def __init__(self, conn, id, event_id, status):
        self.conn, self.id, self.event_id, self.status = conn, id, event_id, status

    def insert(self):                       # writes THIS row
        self.conn.execute("INSERT INTO reservations VALUES (?, ?, ?)",
                          (self.id, self.event_id, self.status))


def reserve_rdg(conn, event_id, res_id):    # Transaction Script: rule HERE
    with conn:
        ev = EventRowGateway.load(conn, event_id)
        if ev.capacity - ev.confirmed_count() <= 0:
            raise SoldOut(event_id)
        ReservationRowGateway(conn, res_id, event_id, "confirmed").insert()


# ---------------------------------------------------------------------------
# 3. ACTIVE RECORD -- the row object grows the rules. Domain logic and SQL
#    sit side by side in the same class.
# ---------------------------------------------------------------------------
class ActiveEvent:                          # a row... that enforces rules
    def __init__(self, conn, id, title, capacity):
        self.conn, self.id, self.title, self.capacity = conn, id, title, capacity

    @classmethod
    def find(cls, conn, event_id):
        r = conn.execute("SELECT id, title, capacity FROM events WHERE id = ?",
                         (event_id,)).fetchone()
        return cls(conn, r["id"], r["title"], r["capacity"]) if r else None

    @property
    def seats_left(self):                   # domain rule ...
        taken = self.conn.execute(          # ... computed with SQL, in place
            "SELECT COUNT(*) FROM reservations "
            "WHERE event_id = ? AND status = 'confirmed'", (self.id,)).fetchone()[0]
        return self.capacity - taken

    def reserve(self, res_id):              # rule + persistence, one method
        if self.seats_left <= 0:
            raise SoldOut(self.id)
        with self.conn:
            self.conn.execute("INSERT INTO reservations VALUES (?, ?, 'confirmed')",
                              (res_id, self.id))


def reserve_ar(conn, event_id, res_id):
    ActiveEvent.find(conn, event_id).reserve(res_id)


# ---------------------------------------------------------------------------
# 4. DATA MAPPER -- a pure domain object (no conn, no SQL) and a separate
#    translator. This is Encore's choice.
# ---------------------------------------------------------------------------
class Reservation:                          # pure domain
    def __init__(self, id, event_id, status="confirmed"):
        self.id, self.event_id, self.status = id, event_id, status


class Event:                                # pure domain: import list empty
    def __init__(self, id, title, capacity):
        self.id, self.title, self.capacity = id, title, capacity
        self.reservations = {}

    @property
    def seats_left(self):                   # the rule, in plain Python
        confirmed = sum(r.status == "confirmed"
                        for r in self.reservations.values())
        return self.capacity - confirmed

    def reserve(self, res_id):
        if self.seats_left <= 0:
            raise SoldOut(self.id)
        r = Reservation(res_id, self.id)
        self.reservations[res_id] = r
        return r


class EventMapper:                          # ALL the SQL lives here
    def __init__(self, conn):
        self.conn = conn

    def find(self, event_id):               # rows -> a full aggregate
        row = self.conn.execute(
            "SELECT id, title, capacity FROM events WHERE id = ?",
            (event_id,)).fetchone()
        if row is None:
            return None
        event = Event(row["id"], row["title"], row["capacity"])
        for r in self.conn.execute(
                "SELECT id, status FROM reservations WHERE event_id = ?",
                (event_id,)):
            event.reservations[r["id"]] = Reservation(r["id"], event_id, r["status"])
        return event

    def save(self, event):                  # the aggregate -> rows
        # No commit here: the CALLER decides the transaction boundary
        # (reserve_dm below, or a Unit of Work in uow_identity_map.py).
        for r in event.reservations.values():
            self.conn.execute(
                "INSERT OR REPLACE INTO reservations (id, event_id, status) "
                "VALUES (?, ?, ?)", (r.id, event.id, r.status))


def reserve_dm(conn, event_id, res_id):     # load -> operate -> save
    mapper = EventMapper(conn)
    event = mapper.find(event_id)           # (1) load
    event.reserve(res_id)                   # (2) the rule, no SQL in sight
    with conn:
        mapper.save(event)                  # (3) write back, one transaction


# ---------------------------------------------------------------------------
PATTERNS = [("Table Data Gateway", reserve_tdg),
            ("Row Data Gateway", reserve_rdg),
            ("Active Record", reserve_ar),
            ("Data Mapper", reserve_dm)]


def seats_left(conn, event_id):             # an independent check, plain SQL
    return conn.execute(
        "SELECT e.capacity - COUNT(r.id) FROM events e "
        "LEFT JOIN reservations r ON r.event_id = e.id AND r.status = 'confirmed' "
        "WHERE e.id = ? GROUP BY e.id", (event_id,)).fetchone()[0]


if __name__ == "__main__":
    print("ev_103 has capacity 2. Each pattern reserves three times.\n")
    for name, reserve in PATTERNS:
        conn = fresh_db()
        results = []
        for n in (1, 2, 3):
            try:
                reserve(conn, "ev_103", f"res_{n}")
                results.append(f"res_{n} ok")
            except SoldOut:
                results.append(f"res_{n} SOLD OUT")
        print(f"  {name:<20} {' | '.join(results):<38} seats left: "
              f"{seats_left(conn, 'ev_103')}")
    print("\nSame behaviour four times. What differs is WHERE the rule lives:\n"
          "  gateways -> in the transaction script;  Active Record -> beside\n"
          "  its SQL;  Data Mapper -> in a pure Event that never sees SQL.")
