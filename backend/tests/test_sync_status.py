"""Sheet sync visibility and "Sync now": same routine as the daily 10:00 job, recorded so every app can show it."""
from app.core.config import settings
from app.services import store_sync_service

from .conftest import API


class _Result:
    def __init__(self, warnings=()):
        self.warnings = list(warnings)

    def as_dict(self):
        return {"platform": "blinkit", "created": 2, "updated": 1, "unchanged": 5, "rows_read": 8, "warnings": self.warnings}


def test_status_is_open_to_any_signed_in_user_and_says_when_it_runs(client, emp):
    r = client.get(f"{API}/sync/status", headers=emp)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["schedule"] == f"{settings.STORE_SYNC_HOUR:02d}:{settings.STORE_SYNC_MINUTE:02d} {settings.STORE_SYNC_TIMEZONE}"
    assert s["next_run_at"] and s["can_sync"] is False
    assert client.get(f"{API}/sync/status").status_code == 401


def test_sync_now_needs_the_permission_and_sheets(client, emp, admin, dev, monkeypatch):
    monkeypatch.setattr(settings, "STORE_SYNC_SHEETS", [])
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", [])
    assert client.post(f"{API}/sync/run", headers=emp).status_code == 403
    assert client.post(f"{API}/sync/run", headers=admin).status_code == 403
    r = client.post(f"{API}/sync/run", headers=dev)
    assert r.status_code == 422 and "No sheets are configured" in r.json()["detail"]


def test_sync_now_runs_the_job_records_it_and_status_shows_it(client, dev, monkeypatch):
    monkeypatch.setattr(settings, "STORE_SYNC_SHEETS", ["blinkit=abc:0"])
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", [])
    monkeypatch.setattr(store_sync_service, "sync_all", lambda db, actor: [_Result(["row 3 skipped"])])
    r = client.post(f"{API}/sync/run", headers=dev)
    assert r.status_code == 200, r.text
    assert r.json()["stores"][0]["created"] == 2 and r.json()["orders"] == []
    s = client.get(f"{API}/sync/status", headers=dev).json()
    assert s["last_run_source"] == "manual" and s["last_run_at"] and s["last_run_warnings"] == 1
    assert s["last_run_by"] and s["can_sync"] is True and s["stores_sheets"] == 1


def test_external_scheduler_trigger(client, admin, monkeypatch, db):
    from app.models.audit_log import AuditLog

    db.query(AuditLog).filter(AuditLog.action == "sheet_sync.run").delete()     # earlier tests in this file ran syncs
    db.commit()
    url = f"{API}/sync/trigger"
    monkeypatch.setattr(settings, "SYNC_TRIGGER_KEY", "")
    assert client.post(url).status_code == 503                                   # off unless a key is configured
    monkeypatch.setattr(settings, "SYNC_TRIGGER_KEY", "cron-secret-123")
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"X-Sync-Key": "wrong"}).status_code == 401

    monkeypatch.setattr(settings, "STORE_SYNC_SHEETS", ["blinkit=abc:0"])
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", [])
    monkeypatch.setattr(store_sync_service, "sync_all", lambda db, actor: [_Result()])
    first = client.post(url, headers={"X-Sync-Key": "cron-secret-123"})
    assert first.status_code == 200 and first.json() == {"ran": True, "stores": 1, "orders": 0}
    second = client.post(url, headers={"X-Sync-Key": "cron-secret-123"})        # a retrying scheduler does no harm
    assert second.json()["ran"] is False
    s = client.get(f"{API}/sync/status", headers=admin).json()
    assert s["last_run_source"] == "scheduled"
