"""Performance reports must be reproducible, auditable, and any change between two of them must be explained or flagged.

Business rules these tests hold in place: holidays are attendance's business and never change an entry count or percentage; an entry counts for the employee whose
scope holds the store whoever entered it (a spreadsheet upload by the Developer User included); a store nobody is responsible for is credited to nobody and flagged.

Everything here runs on throwaway rows. The employee under test is a Zepto employee whose scope is one made-up state with three throwaway stores, so the numbers
are exactly the ones the test plants. The month is the one BEFORE this one (finished: every day of it is judged whenever the suite runs). Times are real clock
ticks: the database stamps entries and deletions with its own clock, so a test takes an instant, changes something, and takes another.
"""
from __future__ import annotations

import calendar
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.session import SessionLocal
from app.models.order_entry import OrderEntry
from app.models.order_entry_event import OrderEntryEvent
from app.models.organization import Organization
from app.models.performance_snapshot import PerformanceSnapshot
from app.models.state_assignment import StateAssignment
from app.models.user import User
from app.services import assignment_service, holiday_service, performance_reconciliation_service as rec, performance_service as ps

from .conftest import API, auth, login, plant_entry

IST = ZoneInfo("Asia/Kolkata")
TODAY = ps.business_today()
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
N_DAYS = calendar.monthrange(MONTH.year, MONTH.month)[1]
DAYS = [MONTH + timedelta(days=i) for i in range(N_DAYS)]
LAST = DAYS[-1]


def tick() -> datetime:
    time.sleep(0.05)
    t = datetime.now(timezone.utc)
    time.sleep(0.05)
    return t


def act_as(db, uid) -> None:
    db.execute(text("SELECT set_config('app.actor_id', :i, true)"), {"i": str(uid)})


def clear(db, store, day, actor=None) -> None:
    """Delete the entry of a store-day the way the app does: as `actor` (the database names them in the history), or with nobody named."""
    db.commit()                                                                 # a fresh transaction: the deletion is stamped with ITS start, not an older one's
    e = db.query(OrderEntry).filter_by(store_id=store.id, order_date=day).one()
    if actor is not None:
        act_as(db, actor)
    db.delete(e)
    db.commit()


@pytest.fixture()
def admin_user(db) -> User:
    return db.query(User).filter_by(employee_code="ADMIN001").one()


@pytest.fixture()
def zone(db, make_user, make_store):
    """A Zepto employee whose scope is exactly three stores of a made-up state."""
    zepto = db.query(Organization).filter_by(slug="zepto").one()
    org = db.query(Organization).filter_by(slug="veekay").one()
    state = f"Recon-{uuid.uuid4().hex[:6]}"
    code, pw, uid = make_user(platform="zepto", grants=("orders.view", "orders.mark"))
    stores = [make_store(platform="zepto", region=None, state=state, city="Recon City") for _ in range(3)]
    db.add(StateAssignment(organization_id=org.id, partner_organization_id=zepto.id, state=state, assigned_user_id=uid))
    db.commit()
    yield SimpleNamespace(uid=uid, code=code, pw=pw, stores=stores, state=state, zepto=zepto, org=org)
    db.query(StateAssignment).filter(StateAssignment.state == state).delete()
    db.commit()


def state_at(db, z, cutoff):
    return rec.build_state(db, z.org.id, z.zepto, MONTH, cutoff)


def figure(db, z, cutoff=None) -> dict:
    return state_at(db, z, cutoff).figures()[z.uid]


def compare(db, z, t1, t2, employee=None):
    prev = rec.point_for(db, z.org.id, z.zepto, MONTH, at=t1)
    curr = rec.point_for(db, z.org.id, z.zepto, MONTH, at=t2)
    out = rec.compare(db, z.org.id, z.zepto, MONTH, prev, curr, employee or z.uid)
    return out, next((r for r in out["employees"] if r["employee_id"] == (employee or z.uid)), None)


def plant(db, z, pairs, creator="self"):
    who = z.uid if creator == "self" else creator
    for si, di in pairs:
        plant_entry(db, z.stores[si], DAYS[di], 5, creator=who)


# ---------------------------------------------------------------- A, B: normal progress, no activity

def test_a_normal_daily_progress_adds_exactly_what_was_marked(db, zone):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])                  # day 1: 6 store-days
    t1 = tick()
    plant(db, zone, [(2, d) for d in range(3)])                                  # day 2: 3 more
    t2 = tick()
    assert figure(db, zone, t1)["done"] == 6 and figure(db, zone, t2)["done"] == 9
    assert figure(db, zone, t2)["expected"] == 3 * N_DAYS
    out, row = compare(db, zone, t1, t2)
    assert row["delta"] == 3 and row["explained"]["entries_added"] == 3 and row["unexplained"]["total"] == 0
    assert row["explained"]["entries_removed"] == 0 and row["status"] == rec.VERIFIED
    assert row["added_by"] == {"the employee themselves": 3}


def test_b_no_new_activity_changes_nothing_and_never_falls_to_zero(db, zone):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    t1 = tick()
    t2 = tick()
    out, row = compare(db, zone, t1, t2)
    assert row["previous"]["done"] == row["current"]["done"] == 6 and row["delta"] == 0
    assert all(v == 0 for v in row["explained"].values()) and row["unexplained"]["total"] == 0 and row["status"] == rec.VERIFIED
    assert out["summary"]["status"] == rec.VERIFIED


# ---------------------------------------------------------------- C: deletion

def test_c_a_deleted_entry_is_a_flagged_decrease_that_names_who_cleared_it(db, zone):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    victim = db.query(OrderEntry).filter_by(store_id=zone.stores[0].id, order_date=DAYS[0]).one()
    entry_id = victim.id
    t1 = tick()
    clear(db, zone.stores[0], DAYS[0], actor=zone.uid)
    t2 = tick()
    out, row = compare(db, zone, t1, t2)
    assert row["delta"] == -1 and row["explained"]["entries_removed"] == 1 and row["unexplained"]["total"] == 0
    rm = row["records"]["removed"]
    assert len(rm) == 1 and rm[0]["kind"] == "cleared" and rm[0]["entry_id"] == str(entry_id) and rm[0]["date"] == DAYS[0] and rm[0]["explained"]
    assert rm[0]["by"] == db.get(User, zone.uid).full_name and rm[0]["reason_recorded"] is False     # honest: nobody gave a reason
    assert row["status"] == rec.RECONCILED
    # the original activity is still on record, and the earlier moment can still be rebuilt
    kinds = [e.event_type for e in db.query(OrderEntryEvent).filter_by(entry_id=entry_id).order_by(OrderEntryEvent.seq)]
    assert kinds == ["CREATED", "CLEARED"]
    assert figure(db, zone, t1)["done"] == 6 and figure(db, zone, t2)["done"] == 5


def test_c_a_removal_with_nobody_named_is_not_explained_and_needs_review(db, zone):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    t1 = tick()
    clear(db, zone.stores[1], DAYS[2], actor=None)                              # deleted with no authenticated actor
    t2 = tick()
    out, row = compare(db, zone, t1, t2)
    assert row["delta"] == -1 and row["unexplained"]["removed_without_evidence"] == 1 and row["unexplained"]["total"] == 1
    assert row["status"] == rec.REVIEW and out["summary"]["status"] == rec.REVIEW and out["summary"]["unexplained_total"] >= 1
    assert row["records"]["removed"][0]["explained"] is False and row["records"]["removed"][0]["by"] is None     # the copy proves it was deleted, not by whom


# ---------------------------------------------------------------- D: reassignment

def test_d_reassigned_stores_move_the_figure_but_never_the_creator(db, zone, make_user, admin_user):
    _, _, other = make_user(platform="zepto", grants=("orders.view", "orders.mark"))
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])                  # entered by the first employee
    first = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    assignment_service.assign_state(db, admin_user, zone.zepto.id, zone.state, other)       # the whole state now belongs to someone else
    second = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")

    prev = rec.point_for(db, zone.org.id, zone.zepto, MONTH, snapshot_id=first.id)
    curr = rec.point_for(db, zone.org.id, zone.zepto, MONTH, snapshot_id=second.id)
    out = rec.compare(db, zone.org.id, zone.zepto, MONTH, prev, curr)
    a = next(r for r in out["employees"] if r["employee_id"] == zone.uid)
    b = next(r for r in out["employees"] if r["employee_id"] == other)
    assert a["previous"]["done"] == 6 and a["current"]["done"] == 0 and a["explained"]["stores_lost"] == 6 and a["unexplained"]["total"] == 0
    assert b["previous"]["done"] == 0 and b["current"]["done"] == 6 and b["explained"]["stores_gained"] == 6 and b["unexplained"]["total"] == 0
    assert {s["store_id"] for s in a["records"]["stores_lost"]} == {s.id for s in zone.stores}        # all three stores of the state changed hands
    # who ORIGINALLY marked them is untouched: they are credited to the new owner's stores, but were entered by the first employee
    assert b["covered_by"] == {db.get(User, zone.uid).full_name: 6}
    assert {e.created_by_user_id for e in db.query(OrderEntry).filter(OrderEntry.store_id.in_([s.id for s in zone.stores]))} == {zone.uid}
    # the reassignment is in the audit trail
    from app.models.audit_log import AuditLog
    assert db.query(AuditLog).filter(AuditLog.action == "state.assigned", AuditLog.entity_id == zone.state).count() >= 1
    # entries made (what a person typed) and coverage (whose stores are covered) are different numbers
    rows = {r["employee_id"]: r for r in ps.performance(db, admin_user, "zepto", MONTH, TODAY)["employees"]}
    assert str(zone.uid) not in {str(k) for k in rows if rows[k]["no_stores"] is False}      # no stores any more, so no percentage...
    assert rows[zone.uid]["entries_made"] == 6 and rows[zone.uid]["no_stores"] is True        # ...but the 6 entries they made are still theirs
    assert rows[other]["entries_made"] == 0 and rows[other]["done"] == 6


# ---------------------------------------------------------------- E, F: corrections and duplicates

def test_e_a_correction_is_an_event_not_a_second_entry_and_not_a_loss(db, zone, admin_user):
    plant(db, zone, [(0, 0), (1, 0), (2, 0)])
    entry = db.query(OrderEntry).filter_by(store_id=zone.stores[0].id, order_date=DAYS[0]).one()
    eid = entry.id
    t1 = tick()
    for n in (9, 11):                                                            # the same entry corrected twice
        act_as(db, zone.uid)
        db.query(OrderEntry).filter_by(id=eid).one().bottle_count = n
        db.commit()
    t2 = tick()
    _, row = compare(db, zone, t1, t2)
    assert row["delta"] == 0 and row["previous"]["done"] == row["current"]["done"] == 3                # unique coverage is not doubled
    assert all(v == 0 for v in row["explained"].values()) and row["status"] == rec.VERIFIED
    edits = db.query(OrderEntryEvent).filter_by(entry_id=eid, event_type="EDITED").count()
    assert edits == 2                                                              # the history keeps both corrections
    # entries made / corrected / correction events are three different numbers (current month: that is when the corrections happened)
    this_month = TODAY.replace(day=1)
    if TODAY == this_month:
        pass
    plant_entry(db, zone.stores[2], TODAY, 4, creator=zone.uid)
    act_as(db, zone.uid)
    db.query(OrderEntry).filter_by(store_id=zone.stores[2].id, order_date=TODAY).one().bottle_count = 7
    db.commit()
    act_as(db, zone.uid)
    db.query(OrderEntry).filter_by(store_id=zone.stores[2].id, order_date=TODAY).one().bottle_count = 8
    db.commit()
    mine = next(r for r in ps.performance(db, admin_user, "zepto", this_month, TODAY)["employees"] if r["employee_id"] == zone.uid)
    assert mine["corrected"] == 2 and mine["correction_events"] == 4          # two entries were corrected, twice each: entries and events are different numbers
    assert mine["entries_made"] == 1                                           # and what they typed this month is a third: the one entry dated today


def test_f_duplicates_never_inflate_the_count(db, zone):
    plant(db, zone, [(0, 0)])
    with pytest.raises(IntegrityError):                                            # the database allows one entry per store and day
        plant_entry(db, zone.stores[0], DAYS[0], 6, creator=zone.uid)
    db.rollback()
    t1 = tick()
    clear(db, zone.stores[0], DAYS[0], actor=zone.uid)
    t2 = tick()
    plant(db, zone, [(0, 0)])                                                      # cleared and entered again
    t3 = tick()
    assert [figure(db, zone, t)["done"] for t in (t1, t2, t3)] == [1, 0, 1]        # one store-day, however many rows it has had
    assert figure(db, zone)["done"] == 1
    _, row = compare(db, zone, t1, t3)
    assert row["delta"] == 0 and row["unexplained"]["total"] == 0


# ---------------------------------------------------------------- G: time zone

def test_g_the_business_day_changes_at_midnight_ist_not_at_utc(db, zone):
    midnight = datetime.combine(LAST + timedelta(days=1), dtime(0, 0), IST)
    before = rec.build_state(db, zone.org.id, zone.zepto, MONTH, midnight - timedelta(seconds=1))
    after = rec.build_state(db, zone.org.id, zone.zepto, MONTH, midnight + timedelta(seconds=1))
    half_past = rec.build_state(db, zone.org.id, zone.zepto, MONTH, midnight + timedelta(minutes=30))     # still the previous day in UTC
    assert before.today == LAST and before.days[-1] == LAST - timedelta(days=1)
    assert after.today == LAST + timedelta(days=1) and after.days[-1] == LAST
    assert half_past.today == LAST + timedelta(days=1) and half_past.days[-1] == LAST
    assert half_past.cutoff.astimezone(timezone.utc).date() == LAST                                        # the UTC date would have said LAST


def test_g_entries_just_before_and_after_midnight_ist_belong_to_the_right_report(db, zone):
    midnight = datetime.combine(LAST + timedelta(days=1), dtime(0, 0), IST)
    # No signed-in actor on this connection: with one, the database stamps created_at with its own clock and ignores the time given. (Some other tests set an actor for the
    # whole connection, so clear it rather than assume.)
    db.execute(text("SELECT set_config('app.actor_id', '', false)"))
    for store, at in ((zone.stores[0], midnight - timedelta(seconds=1)), (zone.stores[1], midnight + timedelta(seconds=1))):
        db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=LAST, bottle_count=3, source="employee", created_at=at))
    db.commit()
    assert {e.created_at for e in db.query(OrderEntry).filter(OrderEntry.store_id.in_([s.id for s in zone.stores[:2]]))} == {midnight - timedelta(seconds=1), midnight + timedelta(seconds=1)}
    done = lambda c: rec.build_state(db, zone.org.id, zone.zepto, MONTH, c).figures()[zone.uid]["done"]
    assert done(midnight - timedelta(seconds=0.5)) == 0          # before midnight: LAST is not over, so not judged yet
    assert done(midnight + timedelta(seconds=0.5)) == 1          # LAST is judged and only the first entry existed
    assert done(midnight + timedelta(seconds=1.5)) == 2          # then the second one exists too
    assert rec.build_state(db, zone.org.id, zone.zepto, MONTH, midnight + timedelta(seconds=2)).days[-1] == LAST      # a month's days stop at its own last day


# ---------------------------------------------------------------- H: platform isolation

def test_h_each_platform_counts_only_its_own_records(db, zone, make_user, make_store):
    blinkit = db.query(Organization).filter_by(slug="blinkit").one()
    _, _, bl_user = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    bl_store = make_store(platform="blinkit", region="NORTH", state="Recon-Bl")
    plant(db, zone, [(0, 0), (1, 0)])
    plant_entry(db, bl_store, DAYS[0], 5, creator=bl_user)
    t = tick()
    zs = rec.build_state(db, zone.org.id, zone.zepto, MONTH, t)
    bs = rec.build_state(db, zone.org.id, blinkit, MONTH, t)
    zepto_ids = {s.id for s in zone.stores}
    assert zone.uid in zs.scopes and zone.uid not in bs.scopes and bl_user in bs.scopes and bl_user not in zs.scopes
    assert bl_store.id not in {s for cov in zs.cover.values() for s in cov} and not (zepto_ids & {s for cov in bs.cover.values() for s in cov})
    assert zs.figures()[zone.uid]["done"] == 2
    assert bl_store.id in bs.scopes[bl_user] and not (zepto_ids & set(bs.scopes[bl_user]))
    # the stored report of one platform lists only that platform's people
    admin = db.query(User).filter_by(employee_code="ADMIN001").one()
    snap = rec.create_snapshot(admin.id, "zepto", MONTH, source="manual")
    assert str(zone.uid) in {e["employee_id"] for e in snap.employees} and str(bl_user) not in {e["employee_id"] for e in snap.employees}
    assert str(bl_user) not in snap.scopes


# ---------------------------------------------------------------- I: a stored report survives a legitimate correction

def test_i_a_stored_report_is_kept_and_a_revision_is_a_new_one(db, zone, admin_user):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    first = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    mine = lambda snap: next(e for e in snap.employees if e["employee_id"] == str(zone.uid))
    assert mine(first)["done"] == 6 and first.source == "manual" and first.revision_of is None
    clear(db, zone.stores[0], DAYS[0], actor=zone.uid)                                         # a legitimate correction afterwards
    with pytest.raises(Exception) as exc:                                                       # a revision has to say why
        rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual", revision_of=first.id)
    assert getattr(exc.value, "status_code", None) == 422
    revised = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual", revision_of=first.id, revision_reason="Entry cleared by the employee")
    db.expire_all()
    stored = db.get(PerformanceSnapshot, first.id)
    assert mine(stored)["done"] == 6 and stored.content_hash == first.content_hash              # the original is exactly as it was
    assert mine(revised)["done"] == 5 and revised.revision_of == first.id and revised.revision_reason == "Entry cleared by the employee"
    listed = {s["id"]: s for s in rec.list_snapshots(db, zone.org.id, "zepto", MONTH)}
    assert listed[first.id]["revised_by_later"] is True and listed[revised.id]["revision_of"] == first.id
    # the original still reproduces from the records at ITS instant, even though today's data is different
    v = rec.verify_snapshot(db, zone.org.id, first.id)
    assert v["reproduced"] is True and v["hash_intact"] is True and v["status"] == rec.VERIFIED
    # and the difference between the two reports is traceable
    out = rec.compare(db, zone.org.id, rec.ps._partner(db, "zepto"), MONTH, rec.point_for(db, zone.org.id, zone.zepto, MONTH, snapshot_id=first.id),
                      rec.point_for(db, zone.org.id, zone.zepto, MONTH, snapshot_id=revised.id), zone.uid)
    row = out["employees"][0]
    assert row["delta"] == -1 and row["records"]["removed"][0]["by"] == db.get(User, zone.uid).full_name and row["status"] == rec.RECONCILED
    assert out["current"]["revision_of"] == first.id


def test_i_stored_reports_cannot_be_edited_or_deleted(db, zone, admin_user):
    snap = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    for sql in ("UPDATE performance_snapshots SET partner_slug = 'x' WHERE id = :i", "DELETE FROM performance_snapshots WHERE id = :i"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"i": snap.id})
        db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("TRUNCATE performance_snapshots"))
    db.rollback()
    assert db.get(PerformanceSnapshot, snap.id) is not None


def test_i_a_stored_figure_the_records_do_not_reproduce_is_flagged(db, zone, admin_user, monkeypatch):
    plant(db, zone, [(0, 0), (1, 0)])
    honest = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    real = ps.performance

    def inflated(*a, **k):                                                                     # a report that says more than the records support
        out = real(*a, **k)
        for r in out["employees"]:
            if r["employee_id"] == zone.uid:
                r["done"] += 5
        return out
    monkeypatch.setattr(ps, "performance", inflated)
    bad = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    monkeypatch.undo()
    v = rec.verify_snapshot(db, zone.org.id, bad.id)
    row = next(r for r in v["employees"] if r["employee_id"] == zone.uid)
    assert v["reproduced"] is False and v["status"] == rec.REVIEW and row["difference"] == -5 and row["matches"] is False
    out = rec.compare(db, zone.org.id, zone.zepto, MONTH, rec.point_for(db, zone.org.id, zone.zepto, MONTH, snapshot_id=honest.id),
                      rec.point_for(db, zone.org.id, zone.zepto, MONTH, snapshot_id=bad.id), zone.uid)
    r = out["employees"][0]
    assert r["delta"] == 5 and r["unexplained"]["stored_figure_difference"] == 5 and r["status"] == rec.REVIEW      # nothing happened, yet the report rose by 5


# ---------------------------------------------------------------- J: concurrent updates

def test_j_a_report_built_while_entries_arrive_is_one_consistent_state(db, zone, admin_user, monkeypatch):
    plant(db, zone, [(0, 0), (1, 0)])
    seen = {}
    real = ps._partner

    def partner_then_a_late_entry(s, slug):
        if seen:                                                                               # performance() asks for the platform again; the entry arrives once
            return real(s, slug)
        seen["isolation"] = s.execute(text("SHOW transaction_isolation")).scalar()
        other = SessionLocal()                                                                 # someone else saves an entry after the snapshot began
        try:
            other.execute(text("SELECT set_config('app.actor_id', :i, false)"), {"i": str(zone.uid)})        # entered by the employee, stamped by the database's own clock
            other.execute(text("INSERT INTO order_entries (id, organization_id, store_id, order_date, bottle_count, source, created_at, updated_at) "
                               "VALUES (gen_random_uuid(), :o, :s, :d, 2, 'employee', clock_timestamp(), clock_timestamp())"),
                          {"o": zone.org.id, "s": zone.stores[2].id, "d": DAYS[0]})
            other.execute(text("SELECT set_config('app.actor_id', '', false)"))
            other.commit()
        finally:
            other.close()
        return real(s, slug)
    monkeypatch.setattr(ps, "_partner", partner_then_a_late_entry)
    snap = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    monkeypatch.undo()
    mine = next(e for e in snap.employees if e["employee_id"] == str(zone.uid))
    assert seen["isolation"] == "repeatable read"
    assert mine["done"] == 2 and mine["expected"] == 3 * N_DAYS                                  # the late entry is in none of the snapshot, not half of it
    assert figure(db, zone)["done"] == 3                                                         # a fresh look sees it
    v = rec.verify_snapshot(db, zone.org.id, snap.id)
    assert v["reproduced"] is True, ([e for e in v["employees"] if not e["matches"]], v["judged_days_match"])      # and the snapshot still rebuilds from the records at its instant


# ---------------------------------------------------------------- K: authorization

def test_k_reconciliation_is_refused_to_ordinary_staff_by_the_backend(client, db, zone, admin, emp, make_user):
    _, _, lead_id = make_user(role="team_lead", platform="zepto")
    lead_code = db.get(User, lead_id).employee_code
    lead = auth(login(client, lead_code).json()["access_token"])
    month = f"{MONTH:%Y-%m}"
    calls = [
        ("get", f"{API}/orders/performance/reconciliation", {"params": {"partner": "zepto", "month": month}}),
        ("get", f"{API}/orders/performance/snapshots", {"params": {"partner": "zepto", "month": month}}),
        ("post", f"{API}/orders/performance/snapshots", {"json": {"partner": "zepto", "month": month}}),
        ("get", f"{API}/orders/performance/snapshots/{uuid.uuid4()}", {"params": {"partner": "zepto"}}),
    ]
    for method, url, kw in calls:
        assert getattr(client, method)(url, **kw).status_code == 401                                  # nobody signed in
        for who in (emp, lead):
            if who is lead and url.endswith("/reconciliation"):
                continue                                                                              # a Team Lead MAY reconcile their own team (see the next tests)
            r = getattr(client, method)(url, headers=who, **kw)
            assert r.status_code == 403, (method, url, r.text)                                        # an employee; a Team Lead for anything platform-wide
        assert client.get(calls[0][1], headers=emp, **calls[0][2]).status_code == 403                  # an ordinary employee: never
    ok = client.get(calls[1][1], headers=admin, params=calls[1][2]["params"])
    assert ok.status_code == 200 and ok.json()["partner_slug"] == "zepto"
    made = client.post(calls[2][1], headers=admin, json=calls[2][2]["json"])
    assert made.status_code == 200 and made.json()["source"] == "manual"
    assert client.post(calls[2][1], headers=admin, json={"partner": "zepto", "month": month, "source": "scheduled"}).status_code == 422     # only the job writes those


def test_k_the_reconciliation_route_returns_the_explanation(client, db, zone, admin):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    t1 = tick()
    clear(db, zone.stores[0], DAYS[0], actor=zone.uid)
    t2 = tick()
    r = client.get(f"{API}/orders/performance/reconciliation", headers=admin, params={
        "partner": "zepto", "month": f"{MONTH:%Y-%m}", "previous_at": t1.isoformat(), "current_at": t2.isoformat(), "employee_id": str(zone.uid)})
    assert r.status_code == 200, r.text
    body = r.json()
    row = body["employees"][0]
    assert row["delta"] == -1 and row["status"] == "reconciled" and row["records"]["removed"][0]["kind"] == "cleared"
    assert body["summary"]["unexplained_total"] == 0 and body["definition"]["version"] == ps.DEFINITION_VERSION
    assert client.get(f"{API}/orders/performance/reconciliation", headers=admin, params={
        "partner": "zepto", "month": f"{MONTH:%Y-%m}", "previous_at": "2026-10-01T10:00:00"}).status_code == 422       # a time needs its zone


# ---------------------------------------------------------------- L: one definition everywhere

def test_l_the_api_the_snapshot_and_the_rebuild_give_the_same_numbers(client, db, zone, admin, admin_user):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(4)] + [(2, 0)])
    api = client.get(f"{API}/orders/performance", headers=admin, params={"partner": "zepto", "month": f"{MONTH:%Y-%m}"})
    assert api.status_code == 200, api.text
    a = next(e for e in api.json()["employees"] if e["employee_id"] == str(zone.uid))
    snap = rec.create_snapshot(admin_user.id, "zepto", MONTH, source="manual")
    s = next(e for e in snap.employees if e["employee_id"] == str(zone.uid))
    live = figure(db, zone)
    rebuilt = figure(db, zone, snap.generated_at)
    keys = ("done", "expected", "percent", "stores")
    assert [a[k] for k in keys] == [s[k] for k in keys] == [live[k] for k in keys] == [rebuilt[k] for k in keys]
    assert a["done"] == 9 and a["expected"] == 3 * N_DAYS
    assert sum(d["done"] for d in a["daily"]) == a["done"]                                          # the per-day tiles add up to the headline
    assert api.json()["definition"]["version"] == snap.definition_version == ps.DEFINITION_VERSION
    # the same pure formula as the report
    daily, done, expected = ps.score({s_.id for s_ in zone.stores}, DAYS, {d: {st.id for st in zone.stores if (st.id, d) in
                                     {(e.store_id, e.order_date) for e in db.query(OrderEntry).filter(OrderEntry.store_id.in_([x.id for x in zone.stores]))}} for d in DAYS})
    assert (done, expected) == (a["done"], a["expected"])


def test_the_report_names_what_it_measures(client, db, zone, admin):
    r = client.get(f"{API}/orders/performance", headers=admin, params={"partner": "zepto", "month": f"{MONTH:%Y-%m}"})
    d = r.json()["definition"]
    assert "whoever entered it" in d["entries"] and "Asia/Kolkata" in d["judged_days"] and r.json()["generated_at"]


# ================================================================ the business rules: holidays are attendance's, uploads count

def _sheet(monkeypatch, pages: dict[str, str], slug: str = "zepto"):
    from app.core.config import settings
    from app.services import store_sync_service

    monkeypatch.setattr(store_sync_service, "fetch_csv_text", lambda sheet_id, gid: pages[gid])
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", [f"{slug}=SHEETID:0"])
    monkeypatch.setattr(settings, "ORDER_SYNC_OVERWRITE", False)


def _row(client, admin, uid):
    r = client.get(f"{API}/orders/performance", headers=admin, params={"partner": "zepto", "month": f"{MONTH:%Y-%m}"})
    assert r.status_code == 200, r.text
    return next(e for e in r.json()["employees"] if e["employee_id"] == str(uid))


def test_rule_b_declaring_a_holiday_removes_no_entry_from_any_count(client, db, zone, admin, admin_user):
    plant(db, zone, [(s, d) for s in (0, 1, 2) for d in range(4)])               # 12 store-days; DAYS[0..3] each have 3
    before = _row(client, admin, zone.uid)
    t1 = tick()
    holiday_service.add(db, admin_user, DAYS[0], "Recon holiday")                 # a day that has entries...
    holiday_service.add(db, admin_user, DAYS[7], "Another")                       # ...and one that has none
    t2 = tick()
    try:
        after = _row(client, admin, zone.uid)
        for k in ("done", "expected", "missing", "percent", "stores"):
            assert after[k] == before[k], k                                          # nothing moved: not the count, not the total, not the percentage
        assert after["done"] == 12 and after["expected"] == 3 * N_DAYS
        assert DAYS[0].isoformat() in {d["date"] for d in after["daily"]}           # the holiday is still a judged day, with its entries
        assert next(d for d in after["daily"] if d["date"] == DAYS[0].isoformat())["done"] == 3
        assert figure(db, zone, t1) == figure(db, zone, t2) == figure(db, zone)       # rebuilt at either moment: identical
        _, row = compare(db, zone, t1, t2)
        assert row["delta"] == 0 and all(v == 0 for v in row["explained"].values()) and row["unexplained"]["total"] == 0 and row["status"] == rec.VERIFIED
    finally:
        holiday_service.remove(db, admin_user, DAYS[0])                              # changing a PAST holiday afterwards: still nothing moves
        holiday_service.remove(db, admin_user, DAYS[7])
    assert _row(client, admin, zone.uid)["done"] == 12 and figure(db, zone)["done"] == 12


def test_rule_b_an_entry_dated_on_a_holiday_counts_even_when_the_holiday_came_first(client, db, zone, admin, admin_user):
    holiday_service.add(db, admin_user, DAYS[1], "Recon holiday")
    try:
        plant(db, zone, [(0, 1), (1, 1)])                                           # entered on a day that is already a holiday
        assert _row(client, admin, zone.uid)["done"] == 2 and figure(db, zone)["done"] == 2
    finally:
        holiday_service.remove(db, admin_user, DAYS[1])


def test_rule_b_attendance_responds_to_holidays_but_entry_performance_does_not(client, db, zone, admin):
    month = f"{MONTH:%Y-%m}"
    day = next(d for d in DAYS if d.weekday() != 6 and d <= LAST)                    # a working day of the month
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])

    def att():
        data = client.get(f"{API}/attendance/month", params={"month": month}, headers=admin).json()
        return next(r for r in data["rows"] if str(r["user_id"]) == str(zone.uid)), data

    perf_before, (att_before, _) = _row(client, admin, zone.uid), att()
    assert client.post(f"{API}/attendance/holidays", headers=admin, json={"holiday_date": day.isoformat(), "name": "Attendance only"}).status_code == 200
    try:
        att_after, data = att()
        assert data["holidays"][day.isoformat()] == "Attendance only"                  # attendance knows about it...
        assert att_after["absent_days"] <= att_before["absent_days"]                   # ...and never counts it as an absence
        perf_after = _row(client, admin, zone.uid)
        assert {k: perf_after[k] for k in ("done", "expected", "percent", "stores")} == {k: perf_before[k] for k in ("done", "expected", "percent", "stores")}
    finally:
        client.delete(f"{API}/attendance/holidays/{day.isoformat()}", headers=admin)
    assert att()[0]["absent_days"] == att_before["absent_days"]                        # removing it restores attendance exactly; entries were never involved
    assert _row(client, admin, zone.uid)["done"] == perf_before["done"]


def test_rule_a_entries_uploaded_by_the_developer_count_for_the_employee_whose_store_it_is(client, db, zone, dev, admin, monkeypatch):
    dates = DAYS[:17]
    cells = {(si, di) for si in range(3) for di in range(17)} - {(2, 16)}              # 3 stores x 17 days, minus one blank cell = 50 entries
    head = "Outlet ID,Outlet Name," + ",".join(d.isoformat() for d in dates)
    body = "\n".join(f"{st.external_code},{st.name}," + ",".join(str(4) if (si, di) in cells else "" for di in range(17)) for si, st in enumerate(zone.stores))
    _sheet(monkeypatch, {"0": f"{head}\n{body}\n"})
    r = client.post(f"{API}/orders/sync?platform=zepto", headers=dev)
    assert r.status_code == 200, r.text
    assert r.json()[0]["created"] == 50 and r.json()[0]["unknown_stores"] == 0

    mine = _row(client, admin, zone.uid)
    assert mine["done"] == 50 and mine["expected"] == 3 * N_DAYS and mine["percent"] == ps._pct(50, 3 * N_DAYS)       # all 50 count for the employee...
    assert mine["entries_made"] == 0                                                # ...though they typed none of them: those are two different numbers
    st = state_at(db, zone, None)
    out, row = compare(db, zone, tick(), tick())
    dev_name = "Test Developer"
    assert row["covered_by"] == {dev_name: 50}                                      # the real creator stays on record, for audit
    assert sum(row["covered_via"].values()) == 50 and "not recorded" not in row["covered_via"]       # and so does where it came from (the import source)
    assert all(e.created_by_name == dev_name for e in db.query(OrderEntry).filter(OrderEntry.store_id.in_([x.id for x in zone.stores])))
    assert st.figures()[zone.uid]["done"] == 50


def test_rule_a_syncing_the_same_sheet_again_never_counts_an_entry_twice(client, db, zone, dev, admin, monkeypatch):
    head = "Outlet ID,Outlet Name," + ",".join(d.isoformat() for d in DAYS[:3])
    body = "\n".join(f"{st.external_code},{st.name},5,6,7" for st in zone.stores)
    _sheet(monkeypatch, {"0": f"{head}\n{body}\n"})
    ids = lambda: {e.id for e in db.query(OrderEntry).filter(OrderEntry.store_id.in_([x.id for x in zone.stores]))}
    assert client.post(f"{API}/orders/sync?platform=zepto", headers=dev).json()[0]["created"] == 9
    first = ids()
    again = client.post(f"{API}/orders/sync?platform=zepto", headers=dev).json()[0]
    assert again["created"] == 0 and again["updated"] == 0 and again["unchanged"] == 9
    db.expire_all()
    assert ids() == first and _row(client, admin, zone.uid)["done"] == 9              # the same 9 business entries, counted once
    overwritten = client.post(f"{API}/orders/sync?platform=zepto&overwrite=true", headers=dev).json()[0]
    db.expire_all()
    assert overwritten["created"] == 0 and ids() == first and _row(client, admin, zone.uid)["done"] == 9


def test_rule_a_an_entry_of_another_employees_store_is_not_credited_to_the_wrong_person(client, db, zone, admin, admin_user, make_user, make_store):
    code2, pw2, other = make_user(platform="zepto", grants=("orders.view", "orders.mark"))
    state2 = f"Recon2-{uuid.uuid4().hex[:6]}"
    theirs = make_store(platform="zepto", region=None, state=state2, city="Elsewhere")
    db.add(StateAssignment(organization_id=zone.org.id, partner_organization_id=zone.zepto.id, state=state2, assigned_user_id=other))
    db.commit()
    try:
        plant(db, zone, [(0, 0)])
        plant_entry(db, theirs, DAYS[0], 3, creator=zone.uid)                         # the FIRST employee typed an entry for the SECOND one's store
        mine, his = _row(client, admin, zone.uid), _row(client, admin, other)
        assert mine["done"] == 1 and his["done"] == 1                               # each is credited for their own store only
        assert mine["entries_made"] == 2 and his["entries_made"] == 0              # who typed it is a different question from whose store it is
        assert figure(db, zone)["done"] == 1 and state_at(db, zone, None).figures()[other]["done"] == 1
    finally:
        db.query(StateAssignment).filter(StateAssignment.state == state2).delete()
        db.commit()


def test_rule_a_a_store_nobody_is_responsible_for_is_flagged_not_guessed(db, zone, admin_user, make_store):
    orphan = make_store(platform="zepto", region=None, state=f"Nobody-{uuid.uuid4().hex[:6]}", city="Nowhere")      # a live store in no one's scope
    plant_entry(db, orphan, DAYS[0], 4, creator=zone.uid)
    summary = ps.performance(db, admin_user, "zepto", MONTH, TODAY)["summary"]
    assert summary["unassigned_stores"] >= 1 and summary["unassigned_store_days"] >= 1
    assert figure(db, zone)["done"] == 0                                              # nobody's count includes it


def test_an_entry_genuinely_added_changes_exactly_the_right_count(client, db, zone, admin):
    plant(db, zone, [(0, 0)])
    assert _row(client, admin, zone.uid)["done"] == 1
    plant(db, zone, [(1, 5)])
    assert _row(client, admin, zone.uid)["done"] == 2                                 # a real new entry moves it by exactly one
    plant_entry(db, zone.stores[2], LAST + timedelta(days=1), 3, creator=zone.uid)    # dated in the NEXT month: not part of this month's report
    assert _row(client, admin, zone.uid)["done"] == 2 and figure(db, zone)["done"] == 2


def test_an_invalidated_entry_leaves_the_count_and_stays_auditable_with_its_reason(db, zone):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    entry_id = db.query(OrderEntry).filter_by(store_id=zone.stores[0].id, order_date=DAYS[0]).one().id
    t1 = tick()
    db.commit()
    act_as(db, zone.uid)
    db.execute(text("SELECT set_config('app.reason', 'entered against the wrong store', true)"))
    db.delete(db.query(OrderEntry).filter_by(id=entry_id).one())
    db.commit()
    t2 = tick()
    _, row = compare(db, zone, t1, t2)
    assert row["delta"] == -1 and row["status"] == rec.RECONCILED and row["unexplained"]["total"] == 0
    rm = row["records"]["removed"][0]
    assert rm["entry_id"] == str(entry_id) and rm["reason"] == "entered against the wrong store" and rm["reason_recorded"] is True
    assert [e.event_type for e in db.query(OrderEntryEvent).filter_by(entry_id=entry_id).order_by(OrderEntryEvent.seq)] == ["CREATED", "CLEARED"]
    assert db.execute(text("SELECT count(*) FROM deleted_rows WHERE table_name = 'order_entries' AND row_id = :i"), {"i": str(entry_id)}).scalar() == 1      # and the row itself is kept


def test_the_api_the_reconciliation_and_the_copied_report_agree(client, db, zone, admin):
    plant(db, zone, [(s, d) for s in (0, 1) for d in range(5)])
    t0 = tick()
    api = _row(client, admin, zone.uid)
    prev = rec.point_for(db, zone.org.id, zone.zepto, MONTH, at=t0)
    now = rec.point_for(db, zone.org.id, zone.zepto, MONTH)
    out = rec.compare(db, zone.org.id, zone.zepto, MONTH, prev, now, zone.uid)
    cur = out["employees"][0]["current"]
    assert (cur["done"], cur["expected"], cur["percent"], cur["stores"]) == (api["done"], api["expected"], api["percent"], api["stores"]) == (10, 3 * N_DAYS, ps._pct(10, 3 * N_DAYS), 3)
    # the group report is built (src/lib/performanceReport.ts) from exactly these API fields: done / expected / percent / stores
    assert {"done", "expected", "percent", "stores", "entries_made", "corrected", "correction_events"} <= set(api)


def test_the_read_only_command_line_tool_explains_a_removal(db, zone, capsys, monkeypatch):
    from scripts import performance_reconcile as cli

    plant(db, zone, [(s, d) for s in (0, 1) for d in range(3)])
    t1 = tick()
    clear(db, zone.stores[0], DAYS[0], actor=zone.uid)
    t2 = tick()
    monkeypatch.setattr("sys.argv", ["performance_reconcile", "--partner", "zepto", "--month", f"{MONTH:%Y-%m}", "--previous", t1.isoformat(), "--current", t2.isoformat(), "--employee", str(zone.uid)])
    assert cli.main() == 0
    out = capsys.readouterr().out
    name = db.get(User, zone.uid).full_name
    assert name in out and "-1" in out and "entries removed -1" in out and f"by {name}" in out and "nothing unexplained" in out and "holiday" not in out.lower().replace("holidays are not special", "")


# ================================================================ "+80 / -12": the change shown next to each employee in the group message

def _change(client, admin, uid):
    r = client.get(f"{API}/orders/performance/change", headers=admin, params={"partner": "zepto", "month": f"{MONTH:%Y-%m}"})
    assert r.status_code == 200, r.text
    return r.json(), r.json()["changes"].get(str(uid))


def test_the_change_is_plus_for_new_entries_and_minus_when_entries_drop(client, db, zone, admin, admin_user):
    old = datetime.now(timezone.utc) - timedelta(days=2)
    db.execute(text("SELECT set_config('app.actor_id', '', false)"))
    for si, di in [(s, d) for s in (0, 1) for d in range(3)]:                      # six entries that already existed two days ago
        db.add(OrderEntry(organization_id=zone.org.id, store_id=zone.stores[si].id, order_date=DAYS[di], bottle_count=3, source="employee", created_at=old))
    db.commit()
    body, change = _change(client, admin, zone.uid)
    assert change == 0 and body["basis"] == "rebuilt" and body["since"]                # nothing happened since the previous report: 0, not missing
    plant(db, zone, [(2, 0), (2, 1), (2, 2)])                                       # three new entries today
    assert _change(client, admin, zone.uid)[1] == 3
    for si, di in [(0, 0), (0, 1), (0, 2), (1, 0)]:                                  # four of the older ones disappear
        clear(db, zone.stores[si], DAYS[di], actor=zone.uid)
    assert _change(client, admin, zone.uid)[1] == 3 - 4 == -1                        # a drop is negative
    assert figure(db, zone)["done"] == 5

    # a report copied or saved, now or long ago, never moves the baseline: the difference is always against the previous day
    rec.create_snapshot(admin_user.id, "zepto", MONTH, source="report", report_text="copied just now")
    db.add(PerformanceSnapshot(
        organization_id=zone.org.id, partner_slug="zepto", month=MONTH, as_of=LAST, generated_at=datetime.now(timezone.utc) - timedelta(days=2), generated_by_user_id=admin_user.id,
        generated_by_name="x", source="manual", definition_version=ps.DEFINITION_VERSION, judged_days=[], scopes={}, summary={}, content_hash="test",
        employees=[{"employee_id": str(zone.uid), "done": 2, "no_stores": False}]))
    db.commit()
    body, change = _change(client, admin, zone.uid)
    assert body["basis"] == "rebuilt" and change == -1


def test_looking_again_right_after_copying_the_report_shows_the_same_change(client, db, zone, admin, admin_user):
    plant(db, zone, [(0, 0), (0, 1)])
    first = _change(client, admin, zone.uid)[1]
    rec.create_snapshot(admin_user.id, "zepto", MONTH, source="report", report_text="sent")        # the report is copied / sent
    assert _change(client, admin, zone.uid)[1] == first == 2
    r = client.get(f"{API}/orders/performance/reconciliation", headers=admin, params={"partner": "zepto", "month": f"{MONTH:%Y-%m}", "employee_id": str(zone.uid)})
    row = r.json()["employees"][0]
    assert r.json()["previous"]["source"] == "rebuilt from the records" and row["delta"] == 2           # the page too compares with the previous day, not with the copy


def test_the_change_is_only_for_people_in_view_and_never_for_platform_logins(client, db, zone, emp):
    r = client.get(f"{API}/orders/performance/change", headers=emp, params={"partner": "blinkit"})
    assert r.status_code == 200 and str(zone.uid) not in r.json()["changes"]            # an employee sees at most their own line
    assert client.get(f"{API}/orders/performance/change", params={"partner": "blinkit"}).status_code == 401


def test_the_entries_a_person_marked_in_the_period_are_counted_per_day_for_that_person(db, zone, make_user):
    _, _, colleague = make_user(platform="zepto", grants=("orders.view", "orders.mark"))
    plant(db, zone, [(0, 0)])                                                         # before the period: not counted
    t1 = tick()
    plant(db, zone, [(0, 1), (0, 2), (1, 0)])                                         # three marked by the employee in the period
    plant(db, zone, [(2, 0)], creator=colleague)                                      # one by a colleague
    clear(db, zone.stores[1], DAYS[0], actor=zone.uid)                                # one of the employee's three is cleared afterwards: still marked by them
    t2 = tick()
    _, mine = compare(db, zone, t1, t2)
    today_ist = datetime.now(IST).date().isoformat()
    assert mine["made"] == {"total": 3, "by_day": {today_ist: 3}}
    assert compare(db, zone, t1, t2, employee=colleague)[1] is None or compare(db, zone, t1, t2, employee=colleague)[1]["made"]["total"] == 1
    _, none_before = compare(db, zone, tick(), tick())
    assert none_before["made"] == {"total": 0, "by_day": {}}                           # nothing marked in an empty period


def test_a_helper_with_no_stores_is_shown_with_how_their_entries_split_across_the_owners(db, zone, make_user, make_store):
    _, _, helper = make_user(platform="zepto", grants=("orders.view", "orders.mark"))              # like Vishwanjali: no state, no stores of their own
    code2, pw2, second = make_user(platform="zepto", grants=("orders.view", "orders.mark"))
    state2 = f"Recon2-{uuid.uuid4().hex[:6]}"
    theirs = make_store(platform="zepto", region=None, state=state2, city="Elsewhere")
    orphan = make_store(platform="zepto", region=None, state=f"Nobody-{uuid.uuid4().hex[:6]}", city="Nowhere")
    db.add(StateAssignment(organization_id=zone.org.id, partner_organization_id=zone.zepto.id, state=state2, assigned_user_id=second))
    db.commit()
    try:
        t1 = tick()
        for st, d in ((zone.stores[0], 0), (zone.stores[0], 1), (zone.stores[1], 0)):               # three on the first employee's stores
            plant_entry(db, st, DAYS[d], 4, creator=helper)
        plant_entry(db, theirs, DAYS[0], 4, creator=helper)                                        # one on the second employee's store
        plant_entry(db, orphan, DAYS[0], 4, creator=helper)                                        # one on a store nobody owns
        plant(db, zone, [(2, 0)])                                                                  # and the first employee marks one of their own
        t2 = tick()
        prev = rec.point_for(db, zone.org.id, zone.zepto, MONTH, at=t1)
        curr = rec.point_for(db, zone.org.id, zone.zepto, MONTH, at=t2)
        out = rec.compare(db, zone.org.id, zone.zepto, MONTH, prev, curr)
        mine = next(h for h in out["helpers"] if h["employee_id"] == helper)
        assert mine["made"]["total"] == 5 and mine["unowned_entries"] == 1                         # the helper is listed, with everything they marked
        split = {o["employee_id"]: (o["entries"], o["share_percent"]) for o in mine["for_owners"]}
        assert split == {zone.uid: (3, 60.0), second: (1, 20.0)}                                    # and how much of it went to each owner's stores
        first_row = next(r for r in out["employees"] if r["employee_id"] == zone.uid)
        assert first_row["made"]["total"] == 1                                                      # their own marking is separate
        assert first_row["entered_by_others"] == [{"employee_id": helper, "name": db.get(User, helper).full_name, "entries": 3, "share_of_their_entries": 60.0}]
        only = rec.compare(db, zone.org.id, zone.zepto, MONTH, prev, curr, second)                  # filtering to one employee keeps only the helpers who worked for them
        assert [h["employee_id"] for h in only["helpers"]] == [helper] and [o["employee_id"] for o in only["helpers"][0]["for_owners"]] == [second]
        assert helper not in {r["employee_id"] for r in out["employees"]}                           # a helper is not a row of the table: they have no percentage
    finally:
        db.query(StateAssignment).filter(StateAssignment.state == state2).delete()
        db.commit()


def test_a_team_lead_reconciles_only_their_own_team(client, db, zone, make_user, make_store):
    from app.models.role import Role
    from app.models.user import UserRole

    _, _, lead_id = make_user(role="employee", platform="zepto", grants=("orders.view", "orders.mark"))      # a Team Lead is an employee who also holds the Team Lead role
    db.add(UserRole(user_id=lead_id, role_id=db.query(Role).filter_by(code="team_lead").one().id))
    db.commit()
    lead = auth(login(client, db.get(User, lead_id).employee_code).json()["access_token"])
    _, _, helper = make_user(platform="zepto", grants=("orders.view", "orders.mark"))
    _, _, stranger = make_user(platform="zepto", grants=("orders.view", "orders.mark"))             # not in the Team Lead's team
    state2 = f"Recon2-{uuid.uuid4().hex[:6]}"
    other_store = make_store(platform="zepto", region=None, state=state2, city="Elsewhere")
    db.add(StateAssignment(organization_id=zone.org.id, partner_organization_id=zone.zepto.id, state=state2, assigned_user_id=stranger))
    db.query(User).filter(User.id.in_([zone.uid, helper])).update({"reports_to_user_id": lead_id})      # the first employee and the helper report to the lead
    db.commit()
    month = f"{MONTH:%Y-%m}"
    try:
        t1 = tick()
        plant(db, zone, [(0, 0), (0, 1)])
        plant_entry(db, zone.stores[1], DAYS[0], 4, creator=helper)                                # the helper marks one of the team's stores...
        plant_entry(db, other_store, DAYS[0], 4, creator=helper)                                   # ...and one of a store outside the team
        plant_entry(db, other_store, DAYS[1], 4, creator=stranger)
        t2 = tick()
        params = {"partner": "zepto", "month": month, "previous_at": t1.isoformat(), "current_at": t2.isoformat()}
        r = client.get(f"{API}/orders/performance/reconciliation", headers=lead, params=params)
        assert r.status_code == 200, r.text
        body = r.json()
        ids = {e["employee_id"] for e in body["employees"]}
        assert str(zone.uid) in ids and str(stranger) not in ids                                    # their employee yes, someone else's employee no
        mine = next(e for e in body["employees"] if e["employee_id"] == str(zone.uid))
        assert mine["delta"] == 3 and mine["made"]["total"] == 2
        assert body["summary"]["employees"] == len(ids)                                             # the summary is about the team too
        helped = next(h for h in body["helpers"] if h["employee_id"] == str(helper))
        assert [o["employee_id"] for o in helped["for_owners"]] == [str(zone.uid)] and helped["made"]["total"] == 1      # only what landed on the team's stores
        assert helped["unowned_entries"] == 0 and helped["made"]["by_day"] == {}
        assert str(stranger) not in {o["employee_id"] for h in body["helpers"] for o in h["for_owners"]}
        # asking about someone outside the team, or for the platform-wide saved reports, is refused by the backend
        assert client.get(f"{API}/orders/performance/reconciliation", headers=lead, params={**params, "employee_id": str(stranger)}).status_code == 403
        assert client.get(f"{API}/orders/performance/reconciliation", headers=lead, params={"partner": "zepto", "month": month, "previous_snapshot": str(uuid.uuid4())}).status_code == 403
        for method, url in (("get", "/orders/performance/snapshots"), ("post", "/orders/performance/snapshots")):
            kw = {"params": {"partner": "zepto", "month": month}} if method == "get" else {"json": {"partner": "zepto", "month": month}}
            assert getattr(client, method)(f"{API}{url}", headers=lead, **kw).status_code == 403
    finally:
        db.query(User).filter(User.id.in_([zone.uid, helper])).update({"reports_to_user_id": None})
        db.query(StateAssignment).filter(StateAssignment.state == state2).delete()
        db.commit()
