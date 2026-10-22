"""Store names are the store's identity: unique per platform, never changed; Outlet IDs can be corrected; duplicates are listed."""
from datetime import date, timedelta

from app.models.order_entry import OrderEntry
from app.models.store import Store

from .conftest import API


def test_a_store_name_cannot_be_changed_by_anyone(client, admin, dev, make_store):
    s = make_store(code="NM-1", name="Fixed Name Mart")
    for who in (admin, dev):
        r = client.patch(f"{API}/stores/{s.id}", json={"name": "Another Name"}, headers=who)
        assert r.status_code == 422 and "can't be changed" in r.json()["detail"]
    same = client.patch(f"{API}/stores/{s.id}", json={"name": "  fixed name   mart ", "city": "Noida"}, headers=admin)
    assert same.status_code == 200 and same.json()["name"] == "Fixed Name Mart" and same.json()["city"] == "Noida"


def test_the_outlet_id_can_be_corrected_and_the_store_keeps_its_orders(client, admin, db, make_store):
    s = make_store(code="NM-TEMP", name="Id Fix Mart")
    db.add(OrderEntry(organization_id=s.organization_id, store_id=s.id, order_date=date.today() - timedelta(days=1), bottle_count=7, source="manual"))
    db.commit()
    r = client.patch(f"{API}/stores/{s.id}", json={"external_code": "NM-REAL"}, headers=admin)
    assert r.status_code == 200 and r.json()["external_code"] == "NM-REAL" and r.json()["name"] == "Id Fix Mart"
    assert db.query(OrderEntry).filter_by(store_id=s.id).count() == 1


def test_an_outlet_id_that_belongs_to_another_store_is_refused_clearly(client, admin, make_store):
    a = make_store(code="NM-A", name="Mart A")
    make_store(code="NM-B", name="Mart B")
    r = client.patch(f"{API}/stores/{a.id}", json={"external_code": "NM-B"}, headers=admin)
    assert r.status_code == 409 and "already belongs to another store" in r.json()["detail"]


def test_a_store_with_an_existing_name_cannot_be_added_by_hand(client, admin, make_store):
    s = make_store(code="NM-C", name="Taken Name Mart")
    body = {"name": "taken name  mart", "external_code": "NM-C2", "start_date": "2026-03-01", "partner_organization_id": str(s.partner_organization_id)}
    r = client.post(f"{API}/stores", json=body, headers=admin)
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_order_import_finds_the_store_by_name_even_with_a_different_outlet_id(client, dev, db, make_store):
    temp = make_store(code="NM-TEMP-9", name="Blinkit - Order Name Mart")
    day = date.today() - timedelta(days=1)
    csv = f"Outlet ID,Outlet Name,{day}\nREAL-ID-9,blinkit - order  name mart,12\nGHOST-1,Blinkit - Nobody,5\n".encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 1 and out["unknown_stores"] == 1
    assert "by Outlet Name" in out["warnings"][0] and "Blinkit - Nobody" in out["warnings"][0]
    assert db.query(OrderEntry).filter_by(store_id=temp.id, order_date=day).one().bottle_count == 12


def test_order_import_uses_the_id_only_when_the_sheet_has_no_name_column(client, dev, db, make_store):
    s = make_store(code="NM-ONLYID", name="Blinkit - Only Id Mart")
    day = date.today() - timedelta(days=1)
    csv = f"Outlet ID,{day}\nNM-ONLYID,4\n".encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["created"] == 1
    assert db.query(OrderEntry).filter_by(store_id=s.id).count() == 1


def test_duplicates_are_listed_with_their_order_days(client, admin, db, make_store):
    a = make_store(code="NM-D1", name="Dup List Mart")
    make_store(code="NM-D2", name="Dup List Mart")
    make_store(code="nm d3", name="Id Lookalike A")
    make_store(code="NM-D3", name="Id Lookalike B")
    db.add(OrderEntry(organization_id=a.organization_id, store_id=a.id, order_date=date.today() - timedelta(days=1), bottle_count=3, source="manual"))
    db.commit()
    got = client.get(f"{API}/stores/duplicates", headers=admin).json()
    names = [g for g in got["groups"] if g["kind"] == "name" and g["label"] == "Dup List Mart"]
    assert len(names) == 1 and sorted(s["external_code"] for s in names[0]["stores"]) == ["NM-D1", "NM-D2"]
    assert {s["external_code"]: s["order_days"] for s in names[0]["stores"]} == {"NM-D1": 1, "NM-D2": 0}
    assert any(g["kind"] == "id" and len(g["stores"]) == 2 for g in got["groups"])
    assert got["total_groups"] >= 2 and got["total_stores"] >= 4


def test_merging_a_duplicate_keeps_every_order(client, dev, db, make_store):
    old = make_store(code="NM-M1", name="Merge Keep Mart")
    new = make_store(code="NM-M2", name="Merge Keep Mart")
    d1, d2 = date.today() - timedelta(days=2), date.today() - timedelta(days=1)
    for d, n in ((d1, 2), (d2, 5)):
        db.add(OrderEntry(organization_id=old.organization_id, store_id=old.id, order_date=d, bottle_count=n, source="manual"))
    db.commit()
    nid = new.id
    r = client.post(f"{API}/stores/merge", json={"platform": "blinkit", "dry_run": False, "pairs": [{"old_code": "NM-M1", "new_code": "NM-M2"}]}, headers=dev)
    assert r.status_code == 200 and r.json()["merged"] == 1
    assert sorted((e.order_date, e.bottle_count) for e in db.query(OrderEntry).filter_by(store_id=nid)) == [(d1, 2), (d2, 5)]
    assert db.query(Store).filter(Store.name == "Merge Keep Mart").count() == 1


def _closed(make_store, code, name):
    return make_store(code=code, name=name, status="CLOSE")


def test_only_closed_stores_without_history_are_deleted(client, admin, db, make_store):
    empty = _closed(make_store, "DC-1", "Del Empty Mart")
    used = _closed(make_store, "DC-2", "Del Used Mart")
    live = make_store(code="DC-3", name="Del Live Mart", status="LIVE")
    db.add(OrderEntry(organization_id=used.organization_id, store_id=used.id, order_date=date.today() - timedelta(days=3), bottle_count=4, source="manual"))
    db.commit()
    ids = [str(empty.id), str(used.id), str(live.id)]
    eid, uid, lid = empty.id, used.id, live.id

    prev = client.post(f"{API}/stores/delete-closed", json={"store_ids": ids}, headers=admin).json()
    assert prev["dry_run"] is True and prev["deleted"] == 0
    assert prev["closed"] == 2 and prev["deletable_count"] == 1 and prev["kept_with_orders"] == 1
    assert [d["external_code"] for d in prev["deletable"]] == ["DC-1"]
    db.expire_all()
    assert db.get(Store, eid) is not None                                  # a preview deletes nothing

    done = client.post(f"{API}/stores/delete-closed", json={"store_ids": ids, "dry_run": False}, headers=admin).json()
    assert done["deleted"] == 1
    db.expire_all()
    assert db.get(Store, eid) is None
    assert db.get(Store, uid) is not None and db.query(OrderEntry).filter_by(store_id=uid).count() == 1   # history untouched
    assert db.get(Store, lid) is not None                                  # live stores are never touched


def test_a_closed_store_with_other_records_is_kept(client, admin, db, make_store):
    from app.models.cash_purchase import CashPurchase
    s = _closed(make_store, "DC-4", "Del Cash Mart")
    sid = s.id
    row = CashPurchase(organization_id=s.organization_id, kind="STORE", store_id=s.id, purchase_date=date.today(), category="EMERGENCY_REQUIREMENT",
                       amount=10, created_by_user_id=None)
    db.add(row)
    db.commit()
    r = client.post(f"{API}/stores/delete-closed", json={"store_ids": [str(sid)], "dry_run": False}, headers=admin).json()
    assert r["deleted"] == 0 and r["kept_with_other_records"] == 1
    db.expire_all()
    assert db.get(Store, sid) is not None
    db.delete(db.get(CashPurchase, row.id))
    db.commit()


def test_deleting_closed_stores_needs_the_manage_permission(client, emp):
    assert client.post(f"{API}/stores/delete-closed", json={}, headers=emp).status_code == 403


def test_stores_sharing_an_outlet_id_are_merged_by_store_id(client, dev, db, make_store):
    a = make_store(code="DUP-ID-1", name="Share Id Mart One")
    b = make_store(code="DUP-ID-1", name="Share Id Mart Two")
    day = date.today() - timedelta(days=1)
    db.add(OrderEntry(organization_id=a.organization_id, store_id=a.id, order_date=day, bottle_count=6, source="manual"))
    db.commit()
    by_code = client.post(f"{API}/stores/merge", json={"platform": "blinkit", "pairs": [{"old_code": "DUP-ID-1", "new_code": "DUP-ID-1"}]}, headers=dev).json()
    assert by_code["merged"] == 0 and "share Outlet ID" in by_code["results"][0]["reason"]      # an ambiguous ID is refused, never guessed
    exact = client.post(f"{API}/stores/merge", headers=dev, json={"platform": "blinkit", "dry_run": False,
                                                                   "pairs": [{"old_id": str(a.id), "new_id": str(b.id)}]}).json()
    assert exact["merged"] == 1
    assert db.query(OrderEntry).filter_by(store_id=b.id, order_date=day).one().bottle_count == 6


def test_the_upload_keeps_a_list_of_rows_it_could_not_use(client, dev, admin, db, make_store):
    from .test_store_import_limits import _xlsx
    make_store(code="IS-1", name="Blinkit - Issue Twin")
    make_store(code="IS-2", name="Blinkit - Issue Twin")
    rows = [
        ["IS-3", "Blinkit - Issue Twin", "Live", "Delhi", "Delhi", ""],          # two stores already carry this name, neither has IS-3
        ["IS-4", "Blinkit - Issue Fresh", "Live", "Delhi", "Delhi", ""],
        ["IS-5", "Blinkit - Issue Fresh", "Live", "Delhi", "Delhi", ""],         # the same name again in the sheet
        ["IS-6", "Blinkit - Issue Odd Status", "somewhat ok", "Delhi", "Delhi", ""],
        ["IS-7", "", "Live", "Delhi", "Delhi", ""],                              # an ID with no name
    ]
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", _xlsx(rows), "application/octet-stream")}, headers=dev)
    assert r.status_code == 200, r.text
    got = client.get(f"{API}/stores/import-issues", headers=admin).json()
    run = next(x for x in got["runs"] if x["platform_slug"] == "blinkit")
    reasons = {i["reason"] for i in run["issues"]}
    assert {"name_matches_several_stores", "name_repeated_in_sheet", "status_not_understood", "missing_name_or_id"} <= reasons
    twin = next(i for i in run["issues"] if i["reason"] == "name_matches_several_stores")
    assert twin["row"] == 2 and sorted(c["external_code"] for c in twin["crm_stores"]) == ["IS-1", "IS-2"]
    db.query(Store).filter(Store.external_code.in_(["IS-4", "IS-6"])).delete(synchronize_session=False)
    db.commit()


def test_a_store_manager_can_merge_but_an_employee_cannot(client, emp, admin, make_store):
    a, b = make_store(name="Merge Perm Mart"), make_store(name="Merge Perm Mart")
    body = {"platform": "blinkit", "pairs": [{"old_id": str(a.id), "new_id": str(b.id)}]}
    assert client.post(f"{API}/stores/merge", json=body, headers=emp).status_code == 403
    assert client.post(f"{API}/stores/merge", json=body, headers=admin).status_code == 200      # a preview


# ---------------------------------------------------------------- wrong-platform check / move, and employees correcting their own entries
def test_a_store_on_the_wrong_platform_is_flagged_and_moves_with_its_history_and_loses_its_zepto_cap(client, admin, db, make_store):
    from app.models.store_cap import StoreCap
    z = make_store(code="55123", name="SS Wrongly On Zepto Mart", platform="zepto", region=None)
    day = date.today() - timedelta(days=1)
    db.add(OrderEntry(organization_id=z.organization_id, store_id=z.id, order_date=day, bottle_count=4, source="manual"))
    db.add(StoreCap(store_id=z.id, daily_cap=10, source="manual"))
    db.commit()
    zid, zpid = z.id, z.partner_organization_id
    found = client.get(f"{API}/stores/platform-check", headers=admin).json()
    row = next(r for r in found["stores"] if r["store"]["id"] == str(zid))
    assert row["suggested_platform"] == "blinkit" and row["has_capping"] is True and row["order_days"] == 1

    moved = client.post(f"{API}/stores/{zid}/move-platform", json={"to_platform": "blinkit"}, headers=admin)
    assert moved.status_code == 200 and moved.json()["capping_removed"] == 1
    db.expire_all()
    assert db.get(Store, zid).partner_organization_id != zpid                                           # it is on the other platform now
    assert db.query(StoreCap).filter_by(store_id=zid).count() == 0                                   # the Zepto cap did not follow it
    assert db.query(OrderEntry).filter_by(store_id=zid).count() == 1                                  # its orders did
    again = client.post(f"{API}/stores/{zid}/move-platform", json={"to_platform": "blinkit"}, headers=admin)
    assert again.status_code == 422                                                                     # already there


def test_moving_to_a_platform_that_already_has_that_name_is_refused(client, admin, make_store):
    a = make_store(code="MP-1", name="Same Name Both Platforms", platform="zepto", region=None)
    make_store(code="MP-2", name="Same Name Both Platforms", platform="blinkit")
    r = client.post(f"{API}/stores/{a.id}/move-platform", json={"to_platform": "blinkit"}, headers=admin)
    assert r.status_code == 409 and "already has a store named" in r.json()["detail"]
    flagged = client.get(f"{API}/stores/platform-check", headers=admin).json()["stores"]
    assert any(x["store"]["id"] == str(a.id) and any("also exists" in why for why in x["reasons"]) for x in flagged)


def test_an_employee_can_correct_or_clear_their_own_entry_but_not_someone_elses(client, emp, admin, db, make_store):
    s = make_store(code="OC-1", region="NORTH")
    today = date.today().isoformat()
    mark = client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(s.id), "order_date": today, "bottle_count": 5})
    assert mark.status_code == 200, mark.text
    again = client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(s.id), "order_date": today, "bottle_count": 9})
    assert again.status_code == 409                                                                      # marking twice is still refused

    fixed = client.patch(f"{API}/orders/my-entry", headers=emp, json={"store_id": str(s.id), "order_date": today, "bottle_count": 8})
    assert fixed.status_code == 200, fixed.text
    assert db.query(OrderEntry).filter_by(store_id=s.id).one().bottle_count == 8
    from app.models.audit_log import AuditLog
    log = db.query(AuditLog).filter_by(action="order.corrected_by_employee").order_by(AuditLog.created_at.desc()).first()
    assert log.metadata_json["previous_count"] == 5 and log.metadata_json["bottle_count"] == 8        # what was there is on record

    cleared = client.patch(f"{API}/orders/my-entry", headers=emp, json={"store_id": str(s.id), "order_date": today})
    assert cleared.status_code == 200
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=s.id).count() == 0
    assert client.patch(f"{API}/orders/my-entry", headers=emp, json={"store_id": str(s.id), "order_date": today, "bottle_count": 3}).status_code == 404   # nothing to correct

    db.add(OrderEntry(organization_id=s.organization_id, store_id=s.id, order_date=date.today(), bottle_count=6, source="admin"))
    db.commit()
    theirs = client.patch(f"{API}/orders/my-entry", headers=emp, json={"store_id": str(s.id), "order_date": today, "bottle_count": 1})
    assert theirs.status_code == 403 and "marked yourself" in theirs.json()["detail"]
    old = (date.today().replace(day=1) - timedelta(days=70)).isoformat()
    assert client.patch(f"{API}/orders/my-entry", headers=emp, json={"store_id": str(s.id), "order_date": old, "bottle_count": 1}).status_code == 422


def test_dashboard_numbers_are_per_platform_and_never_added_together(client, admin, db, make_store):
    b = make_store(code="DB-B", name="Dash Blinkit Mart", platform="blinkit")
    z = make_store(code="DB-Z", name="Dash Zepto Mart", platform="zepto", region=None)
    today = date.today()
    for s, n in ((b, 7), (z, 11)):
        db.add(OrderEntry(organization_id=s.organization_id, store_id=s.id, order_date=today, bottle_count=n, source="manual"))
    db.commit()
    both = client.get(f"{API}/orders/insights", headers=admin).json()
    blk = client.get(f"{API}/orders/insights", params={"partner": "blinkit"}, headers=admin).json()
    zpt = client.get(f"{API}/orders/insights", params={"partner": "zepto"}, headers=admin).json()
    key = "bottles_today" if "bottles_today" in blk else "bottlesToday"
    assert blk[key] + zpt[key] == both[key]                                    # the two channels add up to the old mixed number, never inside one view
    assert {p["slug"] for p in blk["platforms"]} == {"blinkit"} and {p["slug"] for p in zpt["platforms"]} == {"zepto"}
    assert {p["slug"] for p in blk["status_by_platform"]} == {"blinkit"}
    assert all(sc["partner_slug"] == "blinkit" for sc in blk["scopes"])
    assert client.get(f"{API}/orders/insights", params={"partner": "nope"}, headers=admin).status_code == 404


def test_every_store_gets_a_permanent_system_code_unique_across_platforms(client, admin, db, make_store):
    import re
    b = make_store(code="9001", name="East Patel Nagar", platform="blinkit")
    z = make_store(code="9001", name="East Patel Nagar", platform="zepto", region=None)      # same name AND same Outlet ID on both platforms
    assert re.fullmatch(r"BKT\d{6}", b.crm_code) and re.fullmatch(r"ZPT\d{6}", z.crm_code) and b.crm_code != z.crm_code
    got = client.get(f"{API}/stores", params={"search": z.crm_code}, headers=admin).json()
    assert [s["crm_code"] for s in got["items"]] == [z.crm_code]                            # one code finds exactly one store
    again = client.patch(f"{API}/stores/{b.id}", json={"crm_code": "ZPT000001", "city": "Delhi"}, headers=admin)
    assert again.status_code == 200 and again.json()["crm_code"] == b.crm_code             # the code can never be edited


def test_moving_a_store_to_the_other_platform_gives_it_that_platforms_prefix(client, admin, db, make_store):
    z = make_store(code="MV-1", name="Move Code Mart", platform="zepto", region=None)
    before = z.crm_code
    r = client.post(f"{API}/stores/{z.id}/move-platform", json={"to_platform": "blinkit"}, headers=admin)
    assert r.status_code == 200
    db.expire_all()
    assert before.startswith("ZPT") and db.get(Store, z.id).crm_code.startswith("BKT")


def test_a_sheet_with_the_crm_code_matches_exactly_and_refuses_the_other_platforms_code(client, dev, db, make_store):
    from .test_store_import_limits import _xlsx, HEADER
    from openpyxl import Workbook
    import io as _io
    s = make_store(code="CC-1", name="Blinkit - Crm Code Mart")
    other = make_store(code="CC-2", name="Zepto Crm Code Mart", platform="zepto", region=None)
    wb = Workbook(); ws = wb.active
    ws.append(["CRM Code", "Outlet ID", "Outlet Name", "STATUS", "State", "City"])
    ws.append([s.crm_code, "CC-NEW", "Blinkit - Crm Code Mart", "Live", "Delhi", "Delhi"])       # the code settles it; the ID is corrected
    ws.append([other.crm_code, "CC-X", "Blinkit - Wrong Platform Row", "Live", "Delhi", "Delhi"])  # a Zepto code in a Blinkit upload
    buf = _io.BytesIO(); wb.save(buf)
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", buf.getvalue(), "application/octet-stream")}, headers=dev)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 0 and any("not a store of" in w for w in out["warnings"])
    db.expire_all()
    assert db.get(Store, s.id).external_code == "CC-NEW"


def test_the_calendar_says_who_entered_each_day(client, emp, admin, db, make_store):
    s = make_store(code="PV-1", region="NORTH")
    today = date.today().isoformat()
    client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(s.id), "order_date": today, "bottle_count": 4})
    cal = client.get(f"{API}/orders/calendar", params={"store_id": str(s.id)}, headers=emp).json()
    day = next(d for d in cal["days"] if d["date"] == today)
    assert day["source"] == "employee" and day["entered_by"] and day["entered_at"]


def test_an_order_import_can_be_undone_for_one_month_and_nothing_else(client, dev, admin, db, make_store):
    from datetime import datetime
    from app.models.audit_log import AuditLog
    from app.models.deleted_row import DeletedRow
    s = make_store(code="RV-1", name="Revert Mart One")
    t = make_store(code="RV-2", name="Revert Mart Two")
    today = date.today()
    first = today.replace(day=1)
    last_month = first - timedelta(days=5)
    csv = f"Outlet ID,Outlet Name,{last_month.isoformat()},{first.isoformat()},{(first + timedelta(days=1)).isoformat() if first + timedelta(days=1) <= today else first.isoformat()}\n".encode()
    # an employee marks day 1 on store t first; the import will overwrite it
    emp_day = first
    db.add(OrderEntry(organization_id=t.organization_id, store_id=t.id, order_date=emp_day, bottle_count=3, source="employee"))
    db.commit()
    body = f"Outlet ID,Outlet Name,{last_month},{emp_day}\nRV-1,{s.name},9,9\nRV-2,{t.name},,20\n".encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit", "overwrite": "true"}, files={"file": ("o.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    assert db.query(OrderEntry).filter_by(store_id=t.id, order_date=emp_day).one().bottle_count == 20     # the import overwrote the employee's 3

    month = emp_day.strftime("%Y-%m")
    runs = client.get(f"{API}/orders/import-runs", params={"platform": "blinkit", "month": month}, headers=dev).json()["runs"]
    mine = [x for x in runs if x["created_in_month"] >= 1]
    assert mine and mine[0]["overwrote_in_month"] >= 1
    rid = mine[0]["run_id"]
    pre = client.post(f"{API}/orders/import-revert", headers=dev, json={"platform": "blinkit", "month": month, "run_ids": [rid]}).json()
    assert pre["dry_run"] is True and pre["will_delete"] >= 1 and pre["will_restore"] >= 1
    assert db.query(OrderEntry).filter_by(store_id=s.id, order_date=emp_day).count() == 1               # a preview deletes nothing

    assert client.post(f"{API}/orders/import-revert", headers=dev, json={"platform": "blinkit", "month": month, "run_ids": [rid], "dry_run": False}).status_code == 422   # needs the confirm text
    done = client.post(f"{API}/orders/import-revert", headers=dev, json={"platform": "blinkit", "month": month, "run_ids": [rid], "dry_run": False, "confirm": f"REVERT BLINKIT {month}"})
    assert done.status_code == 200, done.text
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=s.id, order_date=emp_day).count() == 0                  # what the import created this month is gone
    back = db.query(OrderEntry).filter_by(store_id=t.id, order_date=emp_day).one()
    assert back.bottle_count == 3 and back.source == "employee"                                           # the employee's own number is back
    if last_month.strftime("%Y-%m") != month:
        assert db.query(OrderEntry).filter_by(store_id=s.id, order_date=last_month).count() == 1           # other months are untouched
    assert db.query(DeletedRow).filter(DeletedRow.table_name == "order_entries", DeletedRow.row_id.isnot(None)).count() >= 1   # and the deleted rows are kept
    assert client.get(f"{API}/orders/import-runs", params={"platform": "blinkit", "month": month}, headers=admin).status_code == 403   # developer only
