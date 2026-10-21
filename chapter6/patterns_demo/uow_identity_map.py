# uow_identity_map.py -- Identity Map and Unit of Work, built by hand so you
# can SEE what an ORM session does for you. Runs on the tiny schema in
# schema.py and reuses the pure Event / EventMapper from four_patterns.py.
#
#   python3 uow_identity_map.py
from schema import fresh_db, SoldOut
from four_patterns import Event, EventMapper


# ===========================================================================
#  IDENTITY MAP -- one object per row, for the life of ONE unit of work
# ===========================================================================
class IdentityMap:
    def __init__(self):
        self._objects = {}                  # (type, id) -> the ONE live object

    def get(self, cls, id):
        return self._objects.get((cls, id))

    def add(self, obj):
        self._objects[(type(obj), obj.id)] = obj


# ===========================================================================
#  UNIT OF WORK -- collect the changes, write them in ONE transaction
# ===========================================================================
class IdempotencyRecord:                    # a plain record: written once
    def __init__(self, key, reservation_id):
        self.id = key                       # its identity field is the key
        self.key, self.reservation_id = key, reservation_id


class IdempotencyMapper:
    def __init__(self, conn):
        self.conn = conn

    def insert(self, rec):
        self.conn.execute("INSERT INTO idempotency VALUES (?, ?)",
                          (rec.key, rec.reservation_id))


class UnitOfWork:
    """One use case = one UnitOfWork = one transaction.
    Repositories are bound to it, so the service never calls register_*."""

    def __init__(self, conn):
        self.conn = conn
        self.identity_map = IdentityMap()
        self._new, self._dirty = [], []
        self.mappers = {Event: EventMapper(conn),
                        IdempotencyRecord: IdempotencyMapper(conn)}
        self.events = EventRepository(self)          # repositories bound
        self.idempotency = IdempotencyStore(self)    #   to THIS unit of work

    # --- registration (called by repositories, not by the service) ---
    def register_new(self, obj):
        if obj not in self._new:
            self._new.append(obj)           # -> INSERT at commit

    def register_dirty(self, obj):
        if obj not in self._dirty and obj not in self._new:
            self._dirty.append(obj)         # -> UPDATE / upsert at commit

    # --- the boundary ---
    def commit(self):
        with self.conn:                     # BEGIN ... COMMIT (or ROLLBACK)
            for o in self._new:
                self.mappers[type(o)].insert(o)
            for o in self._dirty:
                self.mappers[type(o)].save(o)
        self._new.clear(); self._dirty.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Leaving without commit() -- e.g. after a crash -- writes NOTHING:
        # the registered changes were only ever in memory.
        self._new.clear(); self._dirty.clear()
        return False                        # let any exception propagate


class EventRepository:                      # the interface the service sees
    def __init__(self, uow):
        self.uow = uow

    def get(self, event_id):
        cached = self.uow.identity_map.get(Event, event_id)
        if cached is not None:              # loaded already in this UoW?
            return cached                   #   -> the SAME object, no SQL
        event = self.uow.mappers[Event].find(event_id)
        if event is not None:
            self.uow.identity_map.add(event)
        return event

    def save(self, event):                  # same interface as Section 6.1 ...
        self.uow.register_dirty(event)      # ... but it only REGISTERS


class IdempotencyStore:
    def __init__(self, uow):
        self.uow = uow

    def get(self, key):
        row = self.uow.conn.execute(
            "SELECT reservation FROM idempotency WHERE key = ?", (key,)).fetchone()
        return row["reservation"] if row else None

    def put(self, key, reservation_id):
        self.uow.register_new(IdempotencyRecord(key, reservation_id))


# ===========================================================================
#  The service-layer use case -- as on the Unit of Work slide
# ===========================================================================
def reserve(conn, event_id, idem_key, res_id, crash_before_commit=False):
    with UnitOfWork(conn) as uow:           # one per use case
        seen = uow.idempotency.get(idem_key)
        if seen:
            return f"{seen} (replayed)"
        event = uow.events.get(event_id)    # (1) load (identity map)
        r = event.reserve(res_id)           # (2) the rule, pure domain
        uow.events.save(event)              # seat   -> register_dirty
        uow.idempotency.put(idem_key, r.id) # replay -> register_new
        if crash_before_commit:
            raise RuntimeError("process crashed")
        uow.commit()                        # (3) both rows, or neither
        return r.id


# --- the same use case WITHOUT a unit of work: two separate commits --------
def reserve_without_uow(conn, event_id, idem_key, res_id, crash_between=False):
    mapper = EventMapper(conn)
    event = mapper.find(event_id)
    r = event.reserve(res_id)
    with conn:                              # commit #1: the seat
        mapper.save(event)
    if crash_between:
        raise RuntimeError("process crashed")
    with conn:                              # commit #2: the replay record
        IdempotencyMapper(conn).insert(IdempotencyRecord(idem_key, r.id))
    return r.id


# ===========================================================================
#  Helpers for the demo output
# ===========================================================================
def count_rows(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def seats_left(conn, event_id):
    return EventMapper(conn).find(event_id).seats_left


def selects(trace):
    return sum(s.lstrip().upper().startswith("SELECT") for s in trace)


def banner(title):
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


# ===========================================================================
if __name__ == "__main__":
    # -----------------------------------------------------------------------
    banner("1. IDENTITY MAP -- the same row asked for twice")
    trace = []
    conn = fresh_db(trace)
    mapper = EventMapper(conn)
    a = mapper.find("ev_101"); n1 = selects(trace)
    b = mapper.find("ev_101"); n2 = selects(trace) - n1
    print(f"  without a map: a is b -> {a is b}   "
          f"(SELECTs: first find {n1}, second find {n2})")

    trace.clear()
    uow = UnitOfWork(conn)
    a = uow.events.get("ev_101"); n1 = selects(trace)
    b = uow.events.get("ev_101"); n2 = selects(trace) - n1
    print(f"  with a map:    a is b -> {a is b}    "
          f"(SELECTs: first get {n1}, second get {n2})")

    # -----------------------------------------------------------------------
    banner("2. IDENTITY MAP -- why copies are dangerous INSIDE one request\n"
           "   ev_103 has 2 seats, 1 already taken. One request books a group\n"
           "   of two through two code paths that each load the event.")
    for label, load in [("without a map", lambda c: EventMapper(c).find),
                        ("with a map", None)]:
        conn = fresh_db()
        reserve(conn, "ev_103", "k0", "res_0")          # 1 seat left
        uow = UnitOfWork(conn)
        get = load(conn) if load else uow.events.get
        try:
            first = get("ev_103");  first.reserve("res_1")
            second = get("ev_103"); second.reserve("res_2")  # 2nd code path
            with conn:
                for ev in (first, second):
                    EventMapper(conn).save(ev)
            outcome = "both reserved"
        except SoldOut:
            outcome = "2nd path refused; nothing saved"
        print(f"  {label:<14} -> {outcome:<32} "
              f"seats left in DB: {seats_left(conn, 'ev_103')}")
    print("  Two copies each guarded '1 seat left' honestly -- and overbooked.\n"
          "  One object per row lets the second guard see the first change.")

    # -----------------------------------------------------------------------
    banner("3. UNIT OF WORK -- a crash between the two writes")
    conn = fresh_db()
    try:
        reserve_without_uow(conn, "ev_101", "key-A", "res_1", crash_between=True)
    except RuntimeError:
        pass
    print(f"  without UoW: reservations={count_rows(conn, 'reservations')}  "
          f"idempotency={count_rows(conn, 'idempotency')}   "
          "<- a seat with NO replay record:\n"
          "                a retry with key-A would book a SECOND seat")

    conn = fresh_db()
    try:
        reserve(conn, "ev_101", "key-A", "res_1", crash_before_commit=True)
    except RuntimeError:
        pass
    print(f"  with UoW:    reservations={count_rows(conn, 'reservations')}  "
          f"idempotency={count_rows(conn, 'idempotency')}   "
          "<- nothing was written: the retry starts clean")

    # -----------------------------------------------------------------------
    banner("4. UNIT OF WORK -- a normal run, and its retry")
    trace = []
    conn = fresh_db(trace)
    print(f"  first attempt -> {reserve(conn, 'ev_101', 'key-B', 'res_7')}")
    writes = [s.split()[0].upper() for s in trace
              if s.split()[0].upper() in ("BEGIN", "INSERT", "COMMIT")]
    print(f"  statements sent at commit: {' -> '.join(writes)}")
    print(f"  retry, new UoW -> {reserve(conn, 'ev_101', 'key-B', 'res_8')}")
    print(f"  reservations={count_rows(conn, 'reservations')}  "
          f"idempotency={count_rows(conn, 'idempotency')}  "
          f"seats left={seats_left(conn, 'ev_101')}")
    print("\n  Scope reminder: each call to reserve() had its OWN unit of work\n"
          "  and its OWN identity map. They never see each other -- which is\n"
          "  why five simultaneous requests can still overbook (Chapter 7).")
