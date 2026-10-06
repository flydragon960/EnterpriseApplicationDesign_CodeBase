# Listing 7.1 -- storage.py: the repository grows two disciplines.
# Same tables as Chapter 6 plus one column: events.version. Two new ways
# to perform load-check-save: inside a locking transaction (pessimistic),
# or with a conditional, version-checked write (optimistic).
import json
from sqlalchemy import (create_engine, select, func, text,
                        String, Integer, Boolean, ForeignKey)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)
from domain import Event, Reservation

class ConflictError(Exception):
    """The write's premise no longer holds: someone else changed the
    aggregate between our load and our save."""

class Base(DeclarativeBase):
    pass

class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    capacity: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=0)   # NEW
    reservations: Mapped[list["ReservationRow"]] = relationship(
        back_populates="event")

class ReservationRow(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    event: Mapped[EventRow] = relationship(back_populates="reservations")

class IdempotencyRow(Base):
    __tablename__ = "idempotency"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    ok: Mapped[bool] = mapped_column(Boolean)
    code: Mapped[str] = mapped_column(String, nullable=True)
    value_json: Mapped[str] = mapped_column(String, nullable=True)

def make_session_factory(url):
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(engine), engine

def _to_domain(row):
    e = Event(row.id, row.title, row.capacity)
    for r in row.reservations:
        dr = Reservation(r.id, r.event_id)
        dr.status, dr.created_at = r.status, r.created_at
        e.reservations[r.id] = dr
    return e

def _write_back(session, event):
    for r in event.reservations.values():
        session.merge(ReservationRow(id=r.id, event_id=r.event_id,
                                     status=r.status,
                                     created_at=r.created_at))

class EventRepository:
    def __init__(self, session_factory):
        self.sf = session_factory

    # ---- plain reads (unchanged from Chapter 6) ----
    def get(self, event_id):
        with self.sf() as s:
            row = s.get(EventRow, event_id)
            return _to_domain(row) if row else None

    def list_summaries(self):
        with self.sf() as s:
            confirmed = (select(ReservationRow.event_id,
                                func.count().label("n"))
                         .where(ReservationRow.status == "confirmed")
                         .group_by(ReservationRow.event_id).subquery())
            q = (select(EventRow.id, EventRow.title,
                        (EventRow.capacity -
                         func.coalesce(confirmed.c.n, 0)).label("sl"))
                 .outerjoin(confirmed, confirmed.c.event_id == EventRow.id))
            return [{"id": i, "title": t, "seatsLeft": sl}
                    for i, t, sl in s.execute(q).all()]

    # ---- Chapter 6's unsafe write path, kept for the demo ----
    def save_unsafe(self, event):
        with self.sf() as s:
            _write_back(s, event)
            s.commit()

    # ---- PESSIMISTIC: one transaction spans load, check, and save ----
    def unit_of_work(self):
        return _UnitOfWork(self.sf)

    # ---- OPTIMISTIC: load remembers the version... ----
    def get_versioned(self, event_id):
        with self.sf() as s:
            row = s.get(EventRow, event_id)
            return (_to_domain(row), row.version) if row else (None, None)

    # ...and the save is conditional on it still being current.
    def save_versioned(self, event, expected_version):
        with self.sf() as s:
            claimed = s.execute(text(
                "UPDATE events SET version = version + 1 "
                "WHERE id = :id AND version = :v"),
                {"id": event.id, "v": expected_version}).rowcount
            if claimed == 0:
                s.rollback()
                raise ConflictError()      # premise stale: someone won the race
            _write_back(s, event)
            s.commit()

class _UnitOfWork:
    """One database transaction, held open across load-check-save.
    get_event(lock=True) issues SELECT ... FOR UPDATE: the row is OURS
    until commit; every rival transaction queues at the SELECT."""
    def __init__(self, session_factory):
        self.sf = session_factory

    def __enter__(self):
        self.session = self.sf()
        return self

    def get_event(self, event_id, lock=False):
        stmt = select(EventRow).where(EventRow.id == event_id)
        if lock:
            stmt = stmt.with_for_update()
        row = self.session.scalars(stmt).first()
        return _to_domain(row) if row else None

    def save(self, event):
        _write_back(self.session, event)

    def __exit__(self, exc_type, *a):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
        return False

class IdempotencyStore:
    def __init__(self, session_factory):
        self.sf = session_factory

    def get(self, key):
        with self.sf() as s:
            row = s.get(IdempotencyRow, key)
            if row is None:
                return None
            value = json.loads(row.value_json) if row.value_json else None
            return row.request_hash, {"ok": row.ok, "code": row.code,
                                      "value": value}

    def put(self, key, request_hash, outcome):
        with self.sf() as s:
            s.merge(IdempotencyRow(key=key, request_hash=request_hash,
                                   ok=outcome["ok"], code=outcome["code"],
                                   value_json=json.dumps(outcome["value"])))
            s.commit()
