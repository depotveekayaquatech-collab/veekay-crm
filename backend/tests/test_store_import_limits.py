"""Store import: bounded memory / CPU whatever the file contains, batched writes, and an import that never blocks the event loop."""
import inspect
import io
import time
import zipfile

import pytest
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from app.api.v1.endpoints import stores as stores_endpoint
from app.models.store import Store
from app.services import store_sync_service as svc
from tests.conftest import API

HEADER = ["Outlet ID", "Outlet Name", "STATUS", "State", "City"]


def _xlsx(rows, *, fill_cells=()) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    fill = PatternFill("solid", fgColor="FFFF00")
    for row, col in fill_cells:
        ws.cell(row=row, column=col).fill = fill
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _rows(n, prefix="LIM"):
    return [[f"{prefix}-{i}", f"Blinkit - {prefix} {i}", "Live", "Delhi", "Delhi"] for i in range(n)]


def test_normal_sheet_parses_unchanged():
    rows = svc._rows_from_xlsx(_xlsx(_rows(50)))
    assert len(rows) == 50 and rows[0]["Outlet ID"] == "LIM-0" and rows[49]["City"] == "Delhi"


def test_a_sheet_formatted_to_the_last_row_and_column_is_read_quickly_and_small():
    # a formatted cell at XFD / row 1,048,576 makes the declared sheet size enormous
    data = _xlsx(_rows(200), fill_cells=[(1048576, 16384), (1, 16384)])
    t = time.time()
    rows = svc._rows_from_xlsx(data)
    assert len(rows) == 200
    assert all(len(r) <= len(HEADER) for r in rows)      # only the header's width is ever read
    assert time.time() - t < 20                           # stops after the blank run instead of walking a million rows


def test_too_many_rows_is_refused_with_a_clear_message(monkeypatch):
    monkeypatch.setattr(svc, "MAX_ROWS", 100)
    with pytest.raises(svc.SyncError, match="more than 100 rows"):
        svc._rows_from_xlsx(_xlsx(_rows(150)))


def test_too_many_columns_is_refused(monkeypatch):
    monkeypatch.setattr(svc, "MAX_COLUMNS", 3)
    with pytest.raises(svc.SyncError, match="more than 3 columns"):
        svc._rows_from_xlsx(_xlsx(_rows(3)))


def test_a_workbook_that_unpacks_hugely_is_refused_before_it_is_read(monkeypatch):
    monkeypatch.setattr(svc, "MAX_UNPACKED_BYTES", 10_000)
    with pytest.raises(svc.SyncError, match="too large to import safely"):
        svc._rows_from_xlsx(_xlsx(_rows(2000)))


def test_not_a_zip_is_a_clean_error():
    with pytest.raises(svc.SyncError, match="could not be read"):
        svc._rows_from_xlsx(b"this is not an excel file")


def test_csv_is_bounded_too(monkeypatch):
    monkeypatch.setattr(svc, "MAX_ROWS", 10)
    body = "Outlet ID,Outlet Name\n" + "\n".join(f"C{i},Name {i}" for i in range(30))
    with pytest.raises(svc.SyncError, match="more than 10 rows"):
        svc._parse_csv_text(body)
    assert len(svc._parse_csv_text("Outlet ID,Outlet Name\nA1,One\n,\nA2,Two\n")) == 2


def test_import_writes_in_batches_and_is_idempotent(client, dev, db, monkeypatch):
    monkeypatch.setattr(svc, "STORE_FLUSH_EVERY", 7)      # force several flushes for a small file
    data = _xlsx(_rows(30, "BATCH"))
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", data, "application/octet-stream")}, headers=dev)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 30
    again = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", data, "application/octet-stream")}, headers=dev)
    assert again.json()["created"] == 0 and again.json()["unchanged"] == 30     # a retry never duplicates or partially repeats
    assert db.query(Store).filter(Store.external_code.like("BATCH-%")).count() == 30
    db.query(Store).filter(Store.external_code.like("BATCH-%")).delete()
    db.commit()


def test_oversized_upload_is_refused_cleanly(client, dev):
    big = b"x" * (svc.MAX_UPLOAD_BYTES + 10)
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", big, "application/octet-stream")}, headers=dev)
    assert r.status_code == 422 and "too large" in r.json()["detail"]


def test_the_import_endpoint_does_not_block_the_event_loop():
    assert not inspect.iscoroutinefunction(stores_endpoint.import_stores)


# ---- order history archived by "Remove all stores" comes back in constant memory
def _seed_archive(db, codes=1000, days=150):
    from sqlalchemy import text
    db.execute(text("""
        INSERT INTO order_entry_archive (id, created_at, updated_at, organization_id, partner_organization_id, external_code,
                                         store_name, state, city, order_date, bottle_count, cash_adjustment, source, reason)
        SELECT gen_random_uuid(), now(), now(), (SELECT id FROM organizations WHERE slug='veekay'),
               (SELECT id FROM organizations WHERE slug='blinkit'), 'ARC-' || s, 'Blinkit - Arc ' || s, 'Delhi', 'Delhi',
               DATE '2026-01-01' + d, 5, 0, 'employee', 'stores_wiped'
        FROM generate_series(0, :c - 1) s, generate_series(0, :d - 1) d
    """), {"c": codes, "d": days})
    db.commit()


def test_a_huge_archive_is_restored_inside_the_database_not_in_python(client, dev, db):
    import tracemalloc
    from app.models.order_archive import OrderEntryArchive
    from app.models.order_entry import OrderEntry

    _seed_archive(db, codes=1000, days=150)                         # 150,000 archived order days
    assert db.query(OrderEntryArchive).count() == 150_000
    data = _xlsx([[f"ARC-{i}", f"Blinkit - Arc {i}", "Live", "Delhi", "Delhi"] for i in range(1000)])
    tracemalloc.start()
    t = time.time()
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", data, "application/octet-stream")}, headers=dev)
    secs = time.time() - t
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1000
    assert peak < 60 * 1024 * 1024, f"Python heap peaked at {peak / 1e6:.0f} MB"       # the old code needed hundreds of MB here
    db.expire_all()
    assert db.query(OrderEntryArchive).filter(OrderEntryArchive.external_code.like("ARC-%")).count() == 0
    n = db.query(OrderEntry).join(Store, Store.id == OrderEntry.store_id).filter(Store.external_code.like("ARC-%")).count()
    assert n == 150_000
    print(f"\nrestore of 150,000 archived days: {secs:.1f}s total request, python heap peak {peak / 1e6:.1f} MB")
    db.query(Store).filter(Store.external_code.like("ARC-%")).delete(synchronize_session=False)   # cascades the entries
    db.commit()


def test_restore_never_overwrites_a_day_the_store_already_has(db, make_store):
    from sqlalchemy import text
    from app.models.order_entry import OrderEntry
    from app.services import store_service

    s = make_store(platform="blinkit", code="ARC-KEEP", name="Keep")
    org = s.organization_id
    db.add(OrderEntry(organization_id=org, store_id=s.id, order_date=__import__("datetime").date(2026, 1, 1), bottle_count=99))
    db.commit()
    db.execute(text("""
        INSERT INTO order_entry_archive (id, created_at, updated_at, organization_id, partner_organization_id, external_code, store_name,
                                         order_date, bottle_count, cash_adjustment, source, reason)
        SELECT gen_random_uuid(), now(), now(), :o, :p, 'ARC-KEEP', 'Keep', DATE '2026-01-01' + d, 5, 0, 'employee', 'stores_wiped'
        FROM generate_series(0, 2) d"""), {"o": org, "p": s.partner_organization_id})
    db.commit()
    store_service.restore_archived_history(db, org, s.partner_organization_id)
    db.commit()
    got = {e.order_date.day: e.bottle_count for e in db.query(OrderEntry).filter_by(store_id=s.id)}
    assert got == {1: 99, 2: 5, 3: 5}                                # the existing day (99) is untouched
