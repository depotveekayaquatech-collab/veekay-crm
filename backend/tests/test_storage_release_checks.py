"""Pre-deployment checks: an older Android upload, the incoming ceiling, oversized output, files saved before this release,
the audit script being read-only, and monitoring that makes no request to the file store."""
import io
import uuid
from datetime import date
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.core import images, storage
from app.core.config import settings
from app.models.cash_purchase import CashPurchase
from app.models.compliance_document import ComplianceDocument, ComplianceDocumentVersion

from .conftest import API, jpeg
from .test_storage_safety import MONTH, UP, one, s3  # noqa: F401  (s3 is a fixture)

CASH = f"{API}/cash-purchases"


def android_photo(w=4000, h=3000, grain=0.5, quality=95) -> bytes:
    """What the installed app sends: a 12-megapixel camera JPEG (several MB), rotated by EXIF, with a GPS position."""
    img = Image.new("RGB", (w, h), (92, 80, 66))
    d = ImageDraw.Draw(img)
    d.rectangle((int(w * .14), int(h * .04), int(w * .86), int(h * .96)), fill=(244, 242, 236))
    for i in range(40):
        d.text((int(w * .18), int(h * .08) + i * int(h * .02)), f"Water bottles 20L x{i:>3}  Rs {i * 137:>6}.00", fill=(25, 25, 25))
    img = Image.blend(img, Image.effect_noise((w, h), 30).convert("RGB"), grain).filter(ImageFilter.GaussianBlur(0.7))
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x8825] = {1: "N", 2: (28.0, 36.0, 0.0), 3: "E", 4: (77.0, 12.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, exif=exif)
    return buf.getvalue()


@pytest.fixture(scope="module")
def raw_photo() -> bytes:
    data = android_photo()
    assert 3 * 1024 * 1024 < len(data) < settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024     # really a several-MB camera file
    return data


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    db.query(CashPurchase).delete()
    db.commit()


# ---------------------------------------------------------------- the stored-photo limit and older Android uploads
def test_a_several_mb_android_photo_is_accepted_and_stored_under_one_mb(client, emp, make_store, db, raw_photo):
    assert settings.PHOTO_MAX_STORED_KB == 1024 and settings.COMPLIANCE_MAX_FILE_MB == 12      # the shipped defaults, not a patched value
    s = make_store()                                                                          # a Blinkit North store: EMP001's own
    r = client.post(UP, headers=emp, data={"store_id": str(s.id), "month": MONTH, "kind": "card"}, files=one("IMG_2026.jpg", raw_photo))
    assert r.status_code == 200, r.text
    row = db.query(ComplianceDocument).filter_by(id=r.json()["id"]).one()
    stored = storage.read(row.file_key)
    assert len(stored) == row.size_bytes <= 1024 * 1024
    res = Image.open(io.BytesIO(stored))
    assert max(res.size) <= settings.IMAGE_MAX_DIMENSION and res.size[0] < res.size[1]       # upright (the EXIF said "rotate")
    assert not res.getexif().get_ifd(0x8825)                                                  # no GPS position kept


def test_the_same_photo_works_for_a_cash_receipt(client, emp, raw_photo):
    r = client.post(CASH, headers=emp, data={"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "MILK", "amount": "40"},
                    files={"proof": ("IMG_2026.jpg", raw_photo, "image/jpeg")})
    assert r.status_code == 201, r.text
    assert len(client.get(f"{CASH}/{r.json()['id']}/proof", headers=emp).content) <= 1024 * 1024


def test_ticket_photos_are_held_to_the_same_limit(raw_photo):
    from fastapi import UploadFile

    from app.services import external_uploads

    photos = external_uploads.read_photos([UploadFile(filename="IMG.jpg", file=io.BytesIO(raw_photo))])
    assert len(photos) == 1 and len(photos[0].data) <= 1024 * 1024
    assert not Image.open(io.BytesIO(photos[0].data)).getexif()


def test_a_file_above_the_incoming_ceiling_is_refused_before_any_work(client, admin, make_store, monkeypatch):
    big = b"\xff\xd8\xff" + b"0" * (settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024 + 10)
    r = client.post(UP, headers=admin, data={"store_id": str(make_store().id), "month": MONTH, "kind": "card"}, files=one("huge.jpg", big))
    assert r.status_code == 413 and "larger than 12 MB" in r.json()["detail"]


def test_the_ceiling_and_the_stored_limit_are_separate_settings(client, admin, make_store, monkeypatch, raw_photo):
    """Setting the ceiling to 1 MB (once every client shrinks photos) refuses the raw camera file; the stored limit is untouched."""
    monkeypatch.setattr(settings, "COMPLIANCE_MAX_FILE_MB", 1)
    r = client.post(UP, headers=admin, data={"store_id": str(make_store().id), "month": MONTH, "kind": "card"}, files=one("IMG.jpg", raw_photo))
    assert r.status_code == 413 and "larger than 1 MB" in r.json()["detail"]
    assert settings.PHOTO_MAX_STORED_KB == 1024


def test_even_pure_noise_never_ends_up_over_the_default_limit_and_never_corrupted():
    noise = io.BytesIO()
    Image.effect_noise((3000, 2000), 128).convert("RGB").save(noise, "JPEG", quality=95)
    assert len(noise.getvalue()) > 5 * 1024 * 1024
    try:
        out, _ = images.optimize(noise.getvalue(), "jpg")
    except images.ImageTooLarge:
        return                                                    # refused cleanly: also acceptable
    assert len(out) <= 1024 * 1024
    Image.open(io.BytesIO(out)).load()                            # decodes completely: not corrupted


def test_output_that_cannot_fit_is_refused_and_nothing_is_stored(client, admin, make_store, db, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_MAX_STORED_KB", 100)
    noise = io.BytesIO()
    Image.effect_noise((3000, 2000), 128).convert("RGB").save(noise, "JPEG", quality=95)
    s = make_store()
    r = client.post(UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "card"}, files=one("n.jpg", noise.getvalue()))
    assert r.status_code == 413 and "still larger than 100 KB" in r.json()["detail"]
    assert db.query(ComplianceDocument).filter_by(store_id=s.id).count() == 0


def test_many_photos_merge_into_a_pdf_inside_the_pdf_limit_quickly(client, admin, make_store):
    import time

    pages = [("files", (f"p{i}.jpg", android_photo(w=2400, h=1800, grain=0.3, quality=88), "image/jpeg")) for i in range(12)]
    started = time.perf_counter()
    r = client.post(UP, headers=admin, data={"store_id": str(make_store().id), "month": MONTH, "kind": "bill"}, files=pages)
    assert r.status_code == 200, r.text
    assert r.json()["size_bytes"] <= settings.PDF_MAX_FILE_MB * 1024 * 1024
    assert time.perf_counter() - started < 30


# ---------------------------------------------------------------- files saved before this release keep opening
def test_a_file_saved_under_the_old_key_format_still_opens(client, admin, make_store, db, s3):
    """Records created before this release have keys like `.../CODE-bill-v1.jpg` (no random suffix). Nothing rewrites them."""
    s = make_store(code="OLD-KEY-1")
    legacy_key = "Bills/October 2026/DELHI/BCPL/OLD-KEY-1-bill-v1.jpg"
    data = jpeg("blue", (300, 200))
    storage.save(legacy_key, data)
    doc = ComplianceDocument(
        organization_id=s.organization_id, store_id=s.id, month=date(2026, 10, 1), kind="bill", file_key=legacy_key,
        file_name="OLD-KEY-1_bill_2026-10.jpg", content_type="image/jpeg", size_bytes=len(data), storage_backend="s3")
    db.add(doc)
    db.commit()
    assert client.get(f"{API}/compliance/{doc.id}/file", headers=admin).content == data
    link = client.get(f"{API}/compliance/{doc.id}/url", headers=admin).json()
    assert link["url"].startswith("https://") and "OLD-KEY-1-bill-v1.jpg" in link["url"]
    db.delete(doc)
    db.commit()


def test_a_database_row_is_unchanged_by_an_upload_elsewhere(client, admin, make_store, db):
    s, other = make_store(), make_store()
    first = client.post(UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "card"}, files=one("a.jpg", jpeg())).json()
    before = {c.name: getattr(db.query(ComplianceDocument).filter_by(id=first["id"]).one(), c.name) for c in ComplianceDocument.__table__.columns}
    client.post(UP, headers=admin, data={"store_id": str(other.id), "month": MONTH, "kind": "card"}, files=one("b.jpg", jpeg("blue")))
    db.expire_all()
    after = {c.name: getattr(db.query(ComplianceDocument).filter_by(id=first["id"]).one(), c.name) for c in ComplianceDocument.__table__.columns}
    assert before == after


# ---------------------------------------------------------------- the audit script is read-only
def test_the_audit_script_cannot_write_by_construction():
    source = (Path(__file__).resolve().parent.parent / "scripts" / "storage_audit.py").read_text(encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in source                  # PostgreSQL itself refuses any write in its session
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith(("#", '"')))
    for forbidden in ("storage.save", "storage.delete", "save_verified", "put_object", "delete_object", ".commit(", ".add(", ".merge(",
                      "INSERT ", "UPDATE ", "DELETE FROM", "storage.backend().save"):
        assert forbidden not in code, forbidden


def test_a_read_only_session_really_refuses_a_write(db):
    from sqlalchemy import text
    from sqlalchemy.exc import InternalError, OperationalError, ProgrammingError

    from app.db.session import SessionLocal

    s = SessionLocal()
    try:
        s.execute(text("SET TRANSACTION READ ONLY"))
        with pytest.raises((InternalError, OperationalError, ProgrammingError)):
            s.execute(text("CREATE TEMP TABLE should_fail (x int)"))
    finally:
        s.rollback()
        s.close()


# ---------------------------------------------------------------- monitoring costs the file store nothing
def test_the_daily_usage_check_makes_no_request_to_the_file_store(client, admin, make_store, db, monkeypatch):
    from app.core.storage import LocalBackend
    from app.services import storage_monitor

    s = make_store()
    r = client.post(UP, headers=admin, data={"store_id": str(s.id), "month": MONTH, "kind": "card"}, files=one("a.jpg", jpeg(size=(800, 600))))
    size = r.json()["size_bytes"]
    for name in ("save", "read", "exists", "stat", "delete", "list_objects", "signed_url", "healthcheck"):
        monkeypatch.setattr(LocalBackend, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("the usage check touched the file store")))
    usage = storage_monitor.usage_from_database(db)
    assert usage["total_bytes"] >= size and usage["objects"] >= 1
    assert storage_monitor.check_and_log() is not None


def test_readiness_asks_the_bucket_at_most_once_every_ten_minutes(client, monkeypatch):
    from app.api.v1.endpoints import health

    calls = []
    monkeypatch.setattr(storage, "healthcheck", lambda: calls.append(1))
    for _ in range(50):                                            # a monitor polling every minute for almost an hour
        assert client.get(f"{API}/ready").json()["checks"]["storage"]["ok"] is True
    assert len(calls) == 1                                         # an uptime monitor can poll /ready without costing a request each time
    health.reset_storage_probe()
    monkeypatch.setattr(storage, "healthcheck", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.get(f"{API}/ready").status_code == 503           # and a real outage still shows (once the answer has expired)


def test_the_application_reads_only_the_s3_names_not_the_aws_names():
    root = Path(__file__).resolve().parent.parent / "app"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "AWS_ACCESS_KEY_ID" not in text.replace("aws_access_key_id=", "") or path.name == "storage.py"
    assert {"S3_BUCKET", "S3_ENDPOINT_URL", "S3_REGION", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"} <= set(settings.model_fields)
    assert not any(name.startswith("AWS_") or name == "BUCKET_NAME" for name in settings.model_fields)
