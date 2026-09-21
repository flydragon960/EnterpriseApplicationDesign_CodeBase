# Listing 9.3 -- storage.py: reservations with a lifecycle, and an OUTBOX.
# The outbox is the chapter's key idea: an intention to call the outside
# world, written IN THE SAME TRANSACTION as the state change it follows
# from -- so "I decided to charge" and "I recorded the hold" commit
# together or not at all. A separate worker then performs the outbox
# entries. This is how you get atomicity you cannot have across a boundary.
import datetime
from sqlalchemy import (create_engine, select, String, Integer, DateTime,
                        ForeignKey, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)
from domain import Event, Reservation

class Base(DeclarativeBase):
    pass

class EventRow(Base):
    __tablename__ = "events9"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    capacity: Mapped[int] = mapped_column(Integer)
    reservations: Mapped[list["ReservationRow"]] = relationship(
        back_populates="event", lazy="selectin")

class ReservationRow(Base):
    __tablename__ = "reservations9"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events9.id"))
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    hold_expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    event: Mapped[EventRow] = relationship(back_populates="reservations")

class OutboxRow(Base):
    __tablename__ = "outbox9"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)          # "charge" | "refund"
    reservation_id: Mapped[str] = mapped_column(String)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    charge_id: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)

def make_session_factory(url):
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(engine), engine

def _to_domain(row):
    e = Event(row.id, row.title, row.capacity)
    for r in row.reservations:
        dr = Reservation.__new__(Reservation)
        dr.id, dr.event_id, dr.status = r.id, r.event_id, r.status
        dr.created_at, dr.hold_expires_at = r.created_at, r.hold_expires_at
        e.reservations[r.id] = dr
    return e

class Repository:
    def __init__(self, session_factory):
        self.sf = session_factory

    def get(self, event_id):
        with self.sf() as s:
            row = s.get(EventRow, event_id)
            return _to_domain(row) if row else None

    def unit_of_work(self):
        return _UnitOfWork(self.sf)

class _UnitOfWork:
    """One transaction spanning: lock the event, mutate the aggregate,
    AND enqueue the outbox entry -- all committed together."""
    def __init__(self, sf):
        self.sf = sf
    def __enter__(self):
        self.s = self.sf(); return self
    def get_event(self, event_id, lock=False):
        stmt = select(EventRow).where(EventRow.id == event_id)
        if lock:
            stmt = stmt.with_for_update()
        row = self.s.scalars(stmt).first()
        return _to_domain(row) if row else None
    def save_event(self, event):
        for r in event.reservations.values():
            self.s.merge(ReservationRow(
                id=r.id, event_id=r.event_id, status=r.status,
                created_at=r.created_at, hold_expires_at=r.hold_expires_at))
    def enqueue(self, kind, reservation_id, amount=0, charge_id=None):
        self.s.add(OutboxRow(kind=kind, reservation_id=reservation_id,
                             amount=amount, charge_id=charge_id))
    def __exit__(self, exc_type, *a):
        if exc_type is None: self.s.commit()
        else: self.s.rollback()
        self.s.close()
        return False
