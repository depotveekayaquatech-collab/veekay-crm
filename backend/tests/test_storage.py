"""File storage: the local backend and the S3-compatible one (exercised against an in-process fake S3)."""
import boto3
import pytest
from moto import mock_aws

from app.core import storage
from app.core.config import settings


# ---------------------------------------------------------------- local
def test_local_roundtrip_exists_and_delete():
    storage.save("Bills/October 2026/DELHI/BCPL/1-bill.pdf", b"hello")
    assert storage.exists("Bills/October 2026/DELHI/BCPL/1-bill.pdf")
    assert storage.read("Bills/October 2026/DELHI/BCPL/1-bill.pdf") == b"hello"
    storage.delete("Bills/October 2026/DELHI/BCPL/1-bill.pdf")
    assert not storage.exists("Bills/October 2026/DELHI/BCPL/1-bill.pdf")
    storage.delete("never/existed.pdf")                       # deleting a missing file is not an error


@pytest.mark.parametrize("key", ["../escape.txt", "a/../../escape.txt", "/etc/passwd", "a//b.txt", "", "a/./b"])
def test_local_rejects_keys_that_could_escape_the_storage_root(key):
    with pytest.raises(ValueError):
        storage.save(key, b"x")
    assert storage.exists(key) is False


def test_save_replaces_atomically_and_leaves_no_partial_files(tmp_path):
    storage.save("x/file.bin", b"one")
    storage.save("x/file.bin", b"twotwo")
    assert storage.read("x/file.bin") == b"twotwo"
    root = storage.LocalBackend()._root()
    assert not list(root.rglob("*.part"))


def test_local_healthcheck_passes():
    storage.healthcheck()


def test_safe_segment_strips_separators_and_traversal():
    assert ".." not in storage.safe_segment("../../etc") and "/" not in storage.safe_segment("../../etc")
    assert "/" not in storage.safe_segment("a/b\\c")
    assert storage.safe_segment("   ") == "Unknown"
    assert storage.safe_segment("Zepto Pvt. Ltd. (BCPL)") == "Zepto Pvt. Ltd. (BCPL)"


# ---------------------------------------------------------------- S3
@pytest.fixture()
def s3(monkeypatch):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="veekay-test")
        monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
        monkeypatch.setattr(settings, "S3_BUCKET", "veekay-test")
        monkeypatch.setattr(settings, "S3_REGION", "us-east-1")
        monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
        monkeypatch.setattr(settings, "S3_ACCESS_KEY_ID", "test")
        monkeypatch.setattr(settings, "S3_SECRET_ACCESS_KEY", "test")
        monkeypatch.setattr(settings, "S3_PREFIX", "veekay/")
        storage.reset_backend()
        yield boto3.client("s3", region_name="us-east-1")
        storage.reset_backend()


def test_s3_roundtrip_exists_delete(s3):
    storage.save("Bills/Oct/1-bill.pdf", b"pdf-bytes")
    assert storage.exists("Bills/Oct/1-bill.pdf")
    assert storage.read("Bills/Oct/1-bill.pdf") == b"pdf-bytes"
    storage.delete("Bills/Oct/1-bill.pdf")
    assert not storage.exists("Bills/Oct/1-bill.pdf")
    storage.delete("Bills/Oct/never-existed.pdf")             # no error


def test_s3_objects_live_under_the_configured_prefix(s3):
    storage.save("a/b.bin", b"1")
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="veekay-test")["Contents"]]
    assert keys == ["veekay/a/b.bin"]


def test_s3_rejects_traversal_keys(s3):
    with pytest.raises(ValueError):
        storage.save("../x", b"1")
    assert storage.exists("../x") is False


def test_s3_healthcheck_ok_and_fails_for_a_missing_bucket(s3, monkeypatch):
    storage.healthcheck()
    monkeypatch.setattr(settings, "S3_BUCKET", "no-such-bucket")
    storage.reset_backend()
    with pytest.raises(Exception):
        storage.healthcheck()


def test_s3_without_a_bucket_name_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    storage.reset_backend()
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        storage.save("a", b"1")
    storage.reset_backend()


def test_unknown_backend_name_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "floppy-disk")
    storage.reset_backend()
    with pytest.raises(RuntimeError, match="Unknown STORAGE_BACKEND"):
        storage.save("a", b"1")
    storage.reset_backend()


def test_compliance_uploads_use_whichever_backend_is_configured(s3, client, admin, make_store):
    from .conftest import jpeg
    store = make_store(code="S3-STORE-1")
    r = client.post("/api/v1/compliance/upload", headers=admin, data={"store_id": str(store.id), "month": "2026-10", "kind": "bill"},
                    files=[("files", ("a.jpg", jpeg(), "image/jpeg"))])
    assert r.status_code == 200, r.text
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="veekay-test")["Contents"]]
    assert len(keys) == 1 and keys[0].startswith("veekay/Bills/October 2026/")
    view = client.get(f"/api/v1/compliance/{r.json()['id']}/file", headers=admin)
    assert view.status_code == 200 and view.content[:3] == b"\xff\xd8\xff"
