"""The 1 MB photo / 2 MB PDF policy, safe retries, verified writes, usage monitoring, and "nothing deletes business files"."""
import io
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from PIL import Image

from app.core import storage
from app.core.config import settings
from app.models.compliance_document import ComplianceDocument, ComplianceDocumentVersion

from .conftest import API, PDF_BYTES, jpeg
from .test_storage_safety import MONTH, UP, one, photo, upload


def test_the_default_policy_is_one_mb_photos_and_two_mb_pdfs():
    from app.core.config import Settings

    s = Settings()
    assert (s.PHOTO_MAX_STORED_KB, s.PDF_MAX_FILE_MB, s.IMAGE_MAX_DIMENSION) == (1024, 2, 1600)
    with pytest.raises(Exception):
        Settings(PHOTO_MAX_STORED_KB=10)                         # limits are validated: a typo cannot switch them off
    with pytest.raises(Exception):
        Settings(PDF_MAX_FILE_MB=0)


def test_the_upload_policy_endpoint_tells_clients_the_limits_and_needs_a_login(client, emp):
    assert client.get(f"{API}/uploads/policy").status_code == 401
    p = client.get(f"{API}/uploads/policy", headers=emp).json()
    assert p["photo_max_stored_kb"] == settings.PHOTO_MAX_STORED_KB and p["pdf_max_mb"] == settings.PDF_MAX_FILE_MB
    assert p["max_dimension"] == settings.IMAGE_MAX_DIMENSION and p["photo_max_upload_mb"] == settings.COMPLIANCE_MAX_FILE_MB


def test_a_pdf_over_two_mb_is_refused_by_default(client, admin, make_store):
    big = PDF_BYTES + b"0" * (2 * 1024 * 1024 + 10)
    r = upload(client, admin, make_store(), one("scan.pdf", big, "application/pdf"))
    assert r.status_code == 413 and "larger than 2 MB" in r.json()["detail"]
    ok = PDF_BYTES + b"0" * 1_800_000
    assert upload(client, admin, make_store(), one("ok.pdf", ok, "application/pdf")).status_code == 200


def test_merged_photos_obey_the_pdf_limit(client, admin, make_store):
    many = [("files", (f"p{i}.jpg", photo(size=(2400, 1800)), "image/jpeg")) for i in range(8)]
    r = upload(client, admin, make_store(), many)
    assert r.status_code == 200, r.text
    assert 0 < r.json()["size_bytes"] <= settings.PDF_MAX_FILE_MB * 1024 * 1024


def test_a_store_can_have_several_optional_attachments_and_none_is_required(client, admin, make_store, db):
    s, empty = make_store(), make_store()
    card = upload(client, admin, s, one("c.jpg", photo(size=(2000, 1500))), kind="card").json()
    bill = upload(client, admin, s, one("b.pdf", PDF_BYTES, "application/pdf"), kind="bill").json()
    pay = upload(client, admin, s, one("p.jpg", jpeg("green")), kind="payment").json()
    last_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    earlier = upload(client, admin, s, one("c2.jpg", jpeg("blue")), kind="card", month=last_month).json()
    assert len({card["id"], bill["id"], pay["id"], earlier["id"]}) == 4            # three kinds this month plus last month's card
    keys = {d.file_key for d in db.query(ComplianceDocument).filter_by(store_id=s.id)}
    assert len(keys) == 4 and all(storage.exists(k) for k in keys)
    # a store with nothing uploaded is simply listed as having nothing: no error, nothing is forced
    rows = client.get(f"{API}/compliance/stores", headers=admin, params={"month": MONTH, "page_size": 200, "q": empty.external_code}).json()["items"]
    row = next(r for r in rows if r["store_id"] == str(empty.id))
    assert row["card"] is None and row["bill"] is None and row["payment"] is None


def test_an_interrupted_upload_can_be_retried_safely_with_the_same_key(client, admin, make_store, db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.storage import LocalBackend
    from app.main import app

    s = make_store()
    key = uuid.uuid4().hex
    real = LocalBackend.save

    def reset(self, k, d):
        raise TimeoutError("connection reset")

    monkeypatch.setattr(LocalBackend, "save", reset)
    first = TestClient(app, raise_server_exceptions=False).post(
        UP, headers={**admin, "Idempotency-Key": key}, data={"store_id": str(s.id), "month": MONTH, "kind": "bill"}, files=one("a.jpg", jpeg()))
    assert first.status_code == 503                                  # nothing was recorded, and the key is free again
    assert db.query(ComplianceDocument).filter_by(store_id=s.id).count() == 0
    monkeypatch.setattr(LocalBackend, "save", real)
    send = lambda: client.post(UP, headers={**admin, "Idempotency-Key": key}, data={"store_id": str(s.id), "month": MONTH, "kind": "bill"}, files=one("a.jpg", jpeg()))  # noqa: E731
    retry, again = send(), send()
    assert retry.status_code == again.status_code == 200 and retry.json()["id"] == again.json()["id"]
    db.expire_all()
    count = db.query(ComplianceDocumentVersion).join(ComplianceDocument).filter(ComplianceDocument.store_id == s.id).count()
    assert count == 1                                                # one version, however many times it was sent


def test_a_write_the_store_does_not_confirm_is_never_recorded(client, admin, make_store, db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.storage import LocalBackend
    from app.main import app

    s = make_store()
    monkeypatch.setattr(LocalBackend, "stat", lambda self, k: 1)     # the store claims it holds 1 byte
    r = TestClient(app, raise_server_exceptions=False).post(
        UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "bill"}, files=one("a.jpg", jpeg()))
    assert r.status_code == 503
    assert db.query(ComplianceDocument).filter_by(store_id=s.id).count() == 0


def test_a_missing_file_is_logged_for_alerting_without_a_link(client, admin, make_store, db, caplog):
    import logging

    doc = upload(client, admin, make_store(), one("a.jpg", jpeg())).json()
    key = db.query(ComplianceDocument).filter_by(id=doc["id"]).one().file_key
    storage.delete(key)                                              # simulate the loss (the application itself never does this)
    caplog.set_level(logging.WARNING, logger="veekay.storage")
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=admin).status_code == 404
    rec = next(r for r in caplog.records if r.getMessage() == "stored file missing")
    assert rec.file_key == key and rec.where == "compliance_documents"
    assert "http" not in rec.getMessage() and "Signature" not in str(rec.__dict__)


def test_usage_watch_flags_the_quota_and_unusual_growth_and_never_raises(monkeypatch):
    from datetime import datetime, timezone

    from app.services import storage_monitor as m

    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    mb = 1_000_000
    quiet = [("a", 200 * mb, now - timedelta(days=60)), ("b", 40 * mb, now - timedelta(days=20)), ("c", 40 * mb, now - timedelta(days=2))]
    s = m.summarize(quiet, now=now, quota_gb=5, warn_percent=80)
    assert s["total_bytes"] == 280 * mb and s["used_percent"] == 5.6 and not (s["near_quota"] or s["unusual_growth"])
    near = m.summarize([("x", 4_100 * mb, now - timedelta(days=100))], now=now, quota_gb=5, warn_percent=80)
    assert near["near_quota"] and not near["over_quota"]
    assert m.summarize([("x", 5_100 * mb, now - timedelta(days=100))], now=now, quota_gb=5, warn_percent=80)["over_quota"]
    spike = [("old", 100 * mb, now - timedelta(days=14)), ("new", 600 * mb, now - timedelta(days=1))]      # 600 MB vs ~25 MB a week
    assert m.summarize(spike, now=now)["unusual_growth"]
    monkeypatch.setattr(m, "usage_from_database", lambda db: (_ for _ in ()).throw(ConnectionError("down")))
    assert m.check_and_log() is None                                  # a failed check never breaks the sync it rides on


def test_no_code_in_the_app_deletes_stored_business_files():
    """Retention: files are kept indefinitely. Only storage.delete can remove an object, and nothing in the application calls it
    (the storage module itself, tests and the migration script are the only places)."""
    root = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "storage.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "storage.delete(" in line or "delete_object(" in line or "backend().delete(" in line:
                offenders.append(f"{path.relative_to(root)}:{n}")
    assert offenders == []


def test_replacing_a_photo_keeps_the_old_one_and_the_new_one_obeys_the_limit(client, admin, make_store, db):
    s = make_store()
    first = upload(client, admin, s, one("a.jpg", photo(size=(2400, 1800))), kind="card").json()
    old = db.query(ComplianceDocument).filter_by(id=first["id"]).one().file_key
    second = upload(client, admin, s, one("b.jpg", photo(size=(3000, 2000))), kind="card").json()
    db.expire_all()
    new = db.query(ComplianceDocument).filter_by(id=second["id"]).one()
    assert new.file_key != old and storage.exists(old) and storage.exists(new.file_key)
    assert new.size_bytes <= settings.PHOTO_MAX_STORED_KB * 1024
    assert Image.open(io.BytesIO(storage.read(new.file_key))).size[0] <= settings.IMAGE_MAX_DIMENSION
