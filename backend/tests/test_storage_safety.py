"""Storage safety: photos are shrunk and stripped of GPS, PDFs are untouched, nothing is ever overwritten, a failed upload leaves
no half-saved record, access is enforced by the server, and the audit report only reads."""
import io
import sys
import uuid
from datetime import date
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from app.core import images, storage
from app.core.config import settings
from app.models.cash_purchase import CashPurchase
from app.models.compliance_document import ComplianceDocument, ComplianceDocumentVersion
from app.services import activity_service

from .conftest import API, PDF_BYTES, jpeg

MONTH = date.today().strftime("%Y-%m")
UP = f"{API}/compliance/upload"
CASH = f"{API}/cash-purchases"


# ---------------------------------------------------------------- helpers
def photo(size=(3200, 2400), orientation: int | None = None, gps: bool = False, fmt="JPEG", mode="RGB") -> bytes:
    """A noisy photo-like image (so it really is several hundred KB), optionally with EXIF orientation / GPS."""
    base = Image.effect_noise(size, 60).convert("RGB")
    img = Image.blend(base, Image.new("RGB", size, (200, 180, 150)), 0.5).convert(mode)
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    if gps:
        exif[0x8825] = {1: "N", 2: (28.0, 36.0, 0.0), 3: "E", 4: (77.0, 12.0, 0.0)}
    buf = io.BytesIO()
    kw = {"exif": exif} if (orientation or gps) and fmt == "JPEG" else {}
    img.save(buf, fmt, **({"quality": 95} if fmt == "JPEG" else {}), **kw)
    return buf.getvalue()


def upload(client, headers, store, files, kind="bill", month=MONTH):
    return client.post(UP, headers=headers, data={"store_id": str(store.id), "month": month, "kind": kind}, files=files)


def one(name, data, ctype="image/jpeg"):
    return [("files", (name, data, ctype))]


@pytest.fixture()
def s3(monkeypatch):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="veekay-test")
        for k, v in (("STORAGE_BACKEND", "s3"), ("S3_BUCKET", "veekay-test"), ("S3_REGION", "us-east-1"), ("S3_ENDPOINT_URL", ""),
                     ("S3_ACCESS_KEY_ID", "test"), ("S3_SECRET_ACCESS_KEY", "test"), ("S3_PREFIX", "veekay/")):
            monkeypatch.setattr(settings, k, v)
        storage.reset_backend()
        yield boto3.client("s3", region_name="us-east-1")
        storage.reset_backend()


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    db.query(CashPurchase).delete()
    db.commit()


# ---------------------------------------------------------------- 1. photos are optimized
def test_a_large_phone_photo_is_shrunk_upright_and_free_of_gps():
    raw = photo(orientation=6, gps=True)                        # 3200x2400, rotated 90 degrees by EXIF, with a GPS position
    assert Image.open(io.BytesIO(raw)).getexif().get_ifd(0x8825)
    out, ext = images.optimize(raw, "jpg")
    res = Image.open(io.BytesIO(out))
    assert ext == "jpg" and max(res.size) <= settings.IMAGE_MAX_DIMENSION
    assert res.size[0] < res.size[1]                            # was landscape + "rotate 90": stored upright (portrait)
    assert not res.getexif() and not res.getexif().get_ifd(0x8825)   # no GPS, no metadata
    assert len(out) < len(raw) / 2


def test_an_already_small_image_is_never_recompressed():
    small = jpeg(size=(900, 600))
    out, ext = images.optimize(small, "jpg")
    assert out == small and ext == "jpg"                        # byte-for-byte the same
    again, _ = images.optimize(images.optimize(photo(), "jpg")[0], "jpg")
    first = images.optimize(photo(), "jpg")[0]
    assert images.optimize(first, "jpg")[0] == first            # a second pass changes nothing


def test_a_small_image_that_carries_gps_is_still_cleaned():
    raw = photo(size=(800, 600), gps=True)
    assert len(raw) < 900_000
    out, _ = images.optimize(raw, "jpg")
    assert not Image.open(io.BytesIO(out)).getexif().get_ifd(0x8825)


def test_png_without_transparency_becomes_jpeg_and_with_transparency_stays_png():
    flat = photo(size=(2600, 1800), fmt="PNG")
    out, ext = images.optimize(flat, "png")
    assert ext == "jpg" and len(out) < len(flat)
    logo = io.BytesIO()                                          # a simple transparent graphic: small as PNG, so it stays PNG
    Image.new("RGBA", (2000, 1200), (10, 80, 160, 90)).save(logo, "PNG")
    out2, ext2 = images.optimize(logo.getvalue(), "png")
    assert ext2 == "png" and Image.open(io.BytesIO(out2)).mode == "RGBA" and max(Image.open(io.BytesIO(out2)).size) <= settings.IMAGE_MAX_DIMENSION
    busy = photo(size=(2600, 1800), fmt="PNG", mode="RGBA")      # transparent AND detailed: cannot stay PNG inside the limit
    out3, ext3 = images.optimize(busy, "png")
    assert ext3 == "jpg" and len(out3) <= settings.PHOTO_MAX_STORED_KB * 1024


def test_a_truncated_image_is_refused_with_a_clear_message(client, admin, make_store):
    broken = photo(size=(1600, 1200))[:2000]                    # valid JPEG header, rest missing
    r = upload(client, admin, make_store(), one("a.jpg", broken))
    assert r.status_code == 422 and "not a photo we can read" in r.json()["detail"]


def test_optimization_can_be_switched_off_but_the_size_policy_still_applies(monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_OPTIMIZE", False)
    small = photo(size=(1200, 900))
    assert len(small) < settings.PHOTO_MAX_STORED_KB * 1024
    assert images.optimize(small, "jpg") == (small, "jpg")
    with pytest.raises(images.ImageTooLarge):
        images.optimize(photo(size=(3200, 2400)), "jpg")             # over the stored limit and nothing may shrink it


def test_a_photo_is_always_brought_under_the_stored_limit(monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_MAX_STORED_KB", 150)       # a tight policy forces several quality / size steps
    out, _ = images.optimize(photo(), "jpg")
    assert len(out) <= 150 * 1024 and Image.open(io.BytesIO(out)).size[0] >= 900 - 1
    monkeypatch.setattr(settings, "PHOTO_MAX_STORED_KB", 40)
    noise = io.BytesIO()
    Image.effect_noise((3000, 2000), 128).convert("RGB").save(noise, "JPEG", quality=95)
    with pytest.raises(images.ImageTooLarge):                        # pure noise cannot be made readable AND that small: refused, not corrupted
        images.optimize(noise.getvalue(), "jpg")


def test_an_over_limit_photo_is_refused_with_a_clear_message(client, admin, make_store, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_MAX_STORED_KB", 40)
    noise = io.BytesIO()
    Image.effect_noise((3000, 2000), 128).convert("RGB").save(noise, "JPEG", quality=95)
    r = upload(client, admin, make_store(), one("n.jpg", noise.getvalue()))
    assert r.status_code == 413 and "still larger than 40 KB after shrinking" in r.json()["detail"]


def test_an_uploaded_card_is_stored_small_and_opens(client, admin, make_store):
    raw = photo(gps=True)
    s = make_store()
    r = upload(client, admin, s, one("big.jpg", raw))
    assert r.status_code == 200, r.text
    assert 0 < r.json()["size_bytes"] < len(raw) / 2
    f = client.get(f"{API}/compliance/{r.json()['id']}/file", headers=admin)
    assert f.status_code == 200 and f.headers["content-type"] == "image/jpeg"
    assert not Image.open(io.BytesIO(f.content)).getexif().get_ifd(0x8825)


def test_a_cash_receipt_is_stored_small_too(client, emp, make_user):
    raw = photo()
    r = client.post(CASH, headers=emp, data={"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "MILK", "amount": "10"},
                    files={"proof": ("r.jpg", raw, "image/jpeg")})
    assert r.status_code == 201, r.text
    proof = client.get(f"{CASH}/{r.json()['id']}/proof", headers=emp)
    assert proof.status_code == 200 and len(proof.content) < len(raw) / 2


# ---------------------------------------------------------------- 2. PDFs and limits
def test_a_pdf_is_stored_byte_for_byte(client, admin, make_store):
    r = upload(client, admin, make_store(), one("bill.pdf", PDF_BYTES, "application/pdf"))
    assert r.status_code == 200
    assert client.get(f"{API}/compliance/{r.json()['id']}/file", headers=admin).content == PDF_BYTES


def test_a_pdf_over_its_cap_is_refused_with_advice(client, admin, make_store, monkeypatch):
    monkeypatch.setattr(settings, "PDF_MAX_FILE_MB", 1)
    big = PDF_BYTES + b"0" * (1024 * 1024 + 10)
    r = upload(client, admin, make_store(), one("scan.pdf", big, "application/pdf"))
    assert r.status_code == 413 and "larger than 1 MB" in r.json()["detail"] and "photos" in r.json()["detail"]
    # a photo of the same size is fine: it is shrunk, not refused
    assert upload(client, admin, make_store(), one("p.jpg", photo(), "image/jpeg")).status_code == 200


def test_the_overall_file_limit_is_enforced_by_the_server(client, admin, make_store, monkeypatch):
    monkeypatch.setattr(settings, "COMPLIANCE_MAX_FILE_MB", 1)
    big = photo(size=(4000, 3000))
    assert len(big) > 1024 * 1024
    assert upload(client, admin, make_store(), one("p.jpg", big)).status_code == 413


def test_the_file_type_is_judged_by_content_not_name_or_content_type(client, admin, make_store):
    r = upload(client, admin, make_store(), one("receipt.pdf", b"<html>not a pdf</html>", "application/pdf"))
    assert r.status_code == 422
    assert upload(client, admin, make_store(), one("x.jpg", b"", "image/jpeg")).status_code == 422


# ---------------------------------------------------------------- 3. never overwrite, never lose the old file
def test_every_upload_gets_its_own_key_even_for_the_same_store_month_and_version(db, make_store):
    from app.services.compliance_service import _key_for
    s = make_store()
    keys = {_key_for(s, date.today().replace(day=1), "bill", "jpg", 1) for _ in range(50)}
    assert len(keys) == 50                                      # two simultaneous uploads can no longer land on one object


def test_replacing_a_document_keeps_the_previous_file(client, admin, make_store, db):
    s = make_store()
    a = upload(client, admin, s, one("a.jpg", jpeg("red"))).json()
    first_key = db.query(ComplianceDocument).filter_by(id=a["id"]).one().file_key
    b = upload(client, admin, s, one("b.jpg", jpeg("blue"))).json()
    db.expire_all()
    doc = db.query(ComplianceDocument).filter_by(id=b["id"]).one()
    keys = [v.file_key for v in db.query(ComplianceDocumentVersion).filter_by(document_id=doc.id)]
    assert len(set(keys)) == 2 and first_key in keys and doc.file_key != first_key
    assert all(storage.exists(k) for k in keys)                 # the earlier file is still there
    v1 = client.get(f"{API}/compliance/{doc.id}/file", headers=admin, params={"version": 1})
    assert v1.status_code == 200


def test_a_failed_storage_write_creates_no_record_and_keeps_the_old_file(client, admin, make_store, db, monkeypatch):
    s = make_store()
    good = upload(client, admin, s, one("a.jpg", jpeg("red"))).json()
    old_key = db.query(ComplianceDocument).filter_by(id=good["id"]).one().file_key

    def down(self, key, data):
        raise ConnectionError("storage unreachable")

    from app.core.storage import LocalBackend
    monkeypatch.setattr(LocalBackend, "save", down)
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app, raise_server_exceptions=False).post(UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "bill"}, files=one("b.jpg", jpeg("blue")))
    assert r.status_code == 503 and "nothing was recorded" in r.json()["detail"] and r.headers["retry-after"]
    monkeypatch.undo()
    db.expire_all()
    doc = db.query(ComplianceDocument).filter_by(id=good["id"]).one()
    assert doc.file_key == old_key and db.query(ComplianceDocumentVersion).filter_by(document_id=doc.id).count() == 1
    assert storage.exists(old_key)


def test_a_database_failure_after_the_upload_never_damages_the_current_document(client, admin, make_store, db, monkeypatch):
    s = make_store()
    good = upload(client, admin, s, one("a.jpg", jpeg("red"))).json()
    old = db.query(ComplianceDocument).filter_by(id=good["id"]).one().file_key

    def boom(*a, **k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(activity_service, "record", boom)
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app, raise_server_exceptions=False).post(UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "bill"}, files=one("b.jpg", jpeg("blue")))
    assert r.status_code >= 500
    monkeypatch.undo()
    db.expire_all()
    doc = db.query(ComplianceDocument).filter_by(id=good["id"]).one()
    assert doc.file_key == old and storage.exists(old)          # the record still points at the earlier, intact file
    assert doc.size_bytes == good["size_bytes"]
    # the new object may now exist unreferenced: harmless, and the audit report lists it as an orphan candidate (never auto-deleted)


def test_a_lost_response_resend_does_not_store_the_receipt_twice(client, emp, s3):
    body = {"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "MILK", "amount": "55"}
    h = {**emp, "Idempotency-Key": uuid.uuid4().hex}
    a = client.post(CASH, headers=h, data=body, files={"proof": ("r.jpg", photo(size=(1500, 1000)), "image/jpeg")})
    b = client.post(CASH, headers=h, data=body, files={"proof": ("r.jpg", photo(size=(1500, 1000)), "image/jpeg")})
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="veekay-test").get("Contents", [])]
    assert len(keys) == 1


# ---------------------------------------------------------------- 4. access control
def test_uploads_and_downloads_need_a_login(client, admin, make_store):
    s = make_store()
    doc = upload(client, admin, s, one("a.jpg", jpeg())).json()
    assert client.post(UP, data={"store_id": str(s.id), "month": MONTH, "kind": "bill"}, files=one("a.jpg", jpeg())).status_code == 401
    for path in (f"/compliance/{doc['id']}/file", f"/compliance/{doc['id']}/url", f"/compliance/{doc['id']}/versions"):
        assert client.get(f"{API}{path}").status_code == 401, path


def test_an_employee_cannot_reach_another_stores_files_by_changing_the_id(client, admin, emp, zepto_emp, make_store):
    other = make_store(platform="zepto", region=None, state="Karnataka")
    doc = upload(client, admin, other, one("a.jpg", jpeg())).json()
    for path in (f"/compliance/{doc['id']}/file", f"/compliance/{doc['id']}/url", f"/compliance/{doc['id']}/versions"):
        assert client.get(f"{API}{path}", headers=emp).status_code in (403, 404), path
    assert upload(client, emp, other, one("a.jpg", jpeg())).status_code == 403
    assert client.delete(f"{API}/compliance/{doc['id']}", headers=emp).status_code in (403, 404)


def test_a_cash_receipt_is_only_visible_to_its_owner_and_the_accounts_team(client, emp, zepto_emp, admin):
    r = client.post(CASH, headers=emp, data={"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "MILK", "amount": "9"},
                    files={"proof": ("r.jpg", jpeg(), "image/jpeg")})
    pid = r.json()["id"]
    assert client.get(f"{CASH}/{pid}/proof", headers=emp).status_code == 200
    assert client.get(f"{CASH}/{pid}/proof", headers=zepto_emp).status_code == 404       # someone else's: indistinguishable from missing
    assert client.get(f"{CASH}/{pid}/proof").status_code == 401


def test_a_filename_or_key_from_the_client_never_decides_where_a_file_is_stored(client, admin, make_store, db):
    s = make_store(code="KEY-TEST-1")
    r = client.post(UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "bill", "file_key": "../../etc/passwd"},
                    files=one("../../evil.jpg", jpeg()))
    assert r.status_code == 200
    row = db.query(ComplianceDocument).filter_by(id=r.json()["id"]).one()
    assert ".." not in row.file_key and "evil" not in row.file_key and "passwd" not in row.file_key
    assert row.file_key.startswith("Bills/") and "KEY-TEST-1-bill-v1-" in row.file_key      # built by the server from its own data
    assert row.file_name == f"KEY-TEST-1_bill_{MONTH}.jpg"                                 # the display name is server-made too
    with pytest.raises(ValueError):
        storage.save("../outside.jpg", b"x")


# ---------------------------------------------------------------- 5. links and persistence (S3 mocked)
def test_a_signed_link_is_short_lived_fresh_each_time_and_never_stored(client, admin, make_store, db, s3, monkeypatch):
    monkeypatch.setattr(settings, "S3_URL_EXPIRE_SECONDS", 120)
    s = make_store()
    doc = upload(client, admin, s, one("a.jpg", jpeg())).json()
    first = client.get(f"{API}/compliance/{doc['id']}/url", headers=admin).json()
    assert first["url"].startswith("https://") and "Expires=120" in first["url"] and first["expires_in"] == 120
    again = client.get(f"{API}/compliance/{doc['id']}/url", headers=admin).json()      # an expired link is simply asked for again
    assert again["url"].startswith("https://")
    row = db.query(ComplianceDocument).filter_by(id=doc["id"]).one()
    assert "http" not in row.file_key and "Signature" not in row.file_key                # the database holds the stable key only


def test_files_survive_a_server_restart(client, admin, make_store, s3):
    doc = upload(client, admin, make_store(), one("a.jpg", jpeg())).json()
    storage.reset_backend()                                      # a fresh process: no cached client, nothing in memory
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=admin).status_code == 200


def test_a_missing_object_gives_a_clean_message_not_a_crash(client, admin, make_store, db, s3):
    doc = upload(client, admin, make_store(), one("a.jpg", jpeg())).json()
    key = db.query(ComplianceDocument).filter_by(id=doc["id"]).one().file_key
    s3.delete_object(Bucket="veekay-test", Key="veekay/" + key)
    for path in (f"/compliance/{doc['id']}/file", f"/compliance/{doc['id']}/url"):
        r = client.get(f"{API}{path}", headers=admin)
        assert r.status_code == 404 and "missing from storage" in r.json()["detail"]


def test_pdf_and_image_are_served_with_the_right_headers_for_inline_viewing(client, admin, make_store):
    s = make_store()
    pdf = upload(client, admin, s, one("a.pdf", PDF_BYTES, "application/pdf"), kind="payment").json()
    r = client.get(f"{API}/compliance/{pdf['id']}/file", headers=admin)
    assert r.headers["content-type"] == "application/pdf" and r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff" and "no-store" in r.headers["cache-control"]


# ---------------------------------------------------------------- 6. the audit report only reads
def test_the_audit_report_never_deletes_or_changes_anything(client, admin, make_store, db, capsys, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import storage_audit

    s = make_store()
    doc = upload(client, admin, s, one("a.jpg", jpeg())).json()
    key = db.query(ComplianceDocument).filter_by(id=doc["id"]).one().file_key
    storage.save("Strays/never-referenced.jpg", b"stray")        # an object nothing points to
    ghost = ComplianceDocumentVersion(document_id=uuid.UUID(doc["id"]), version=99, file_key="Ghost/missing.jpg", file_name="g.jpg",
                                      content_type="image/jpeg", size_bytes=10, sha256="0" * 64, storage_backend="local", source_files=1)
    db.add(ghost)
    db.commit()
    before = (db.query(ComplianceDocument).count(), db.query(ComplianceDocumentVersion).count())

    monkeypatch.setattr(sys, "argv", ["storage_audit.py", "--grace-days", "0"])
    code = storage_audit.main()
    out = capsys.readouterr().out
    assert code == 1                                             # a broken reference exists, so it reports failure
    assert "REFERENCED BUT MISSING" in out and "Ghost/missing.jpg" in out
    assert "Strays/never-referenced.jpg" in out                  # listed as an orphan candidate ...
    assert storage.exists("Strays/never-referenced.jpg") and storage.exists(key)    # ... and nothing was deleted
    db.expire_all()
    assert (db.query(ComplianceDocument).count(), db.query(ComplianceDocumentVersion).count()) == before
    assert "http" not in out and "Signature" not in out          # no link or secret is ever printed
    storage.delete("Strays/never-referenced.jpg")
    db.delete(db.get(ComplianceDocumentVersion, ghost.id))
    db.commit()


def test_a_fresh_unreferenced_object_is_not_called_an_orphan_yet(capsys, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import storage_audit

    storage.save("Strays/just-uploaded.jpg", b"x")
    monkeypatch.setattr(sys, "argv", ["storage_audit.py", "--grace-days", "14"])
    storage_audit.main()
    out = capsys.readouterr().out
    assert "just-uploaded.jpg" not in out and "orphan candidates, NOT deleted): 0" in out
    storage.delete("Strays/just-uploaded.jpg")


def test_upload_endpoints_do_not_block_the_server_while_they_work():
    """They are plain functions, so FastAPI runs them in worker threads instead of on the event loop."""
    import inspect

    from app.api.v1.endpoints import cash_purchases, compliance, test_reports
    for fn in (compliance.upload, compliance.bulk, cash_purchases.create, test_reports.upload):
        assert not inspect.iscoroutinefunction(fn), fn.__name__
