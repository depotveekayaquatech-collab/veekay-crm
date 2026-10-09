"""The vendor / POC logins page: admin-only, no hashes, CSV with initial passwords."""
from app.core.security import hash_password
from app.models.external_account import ExternalAccount
from app.models.organization import Organization

from .conftest import API


def test_logins_page_is_admin_only_and_exports_initial_passwords(client, admin, emp, db):
    org = db.query(Organization).filter_by(slug="veekay").one()
    made = [
        ExternalAccount(organization_id=org.id, kind="vendor", email="t-vend@supplier.com", full_name="T Vend", password_hash=hash_password("123456"), platforms=["blinkit"], store_count=0),
        ExternalAccount(organization_id=org.id, kind="poc", email="t-poc@blinkit.com", full_name="T Poc", password_hash=hash_password("x1y2z3"), platforms=["blinkit"], store_count=0),
        ExternalAccount(organization_id=org.id, kind="poc", email="t-done@blinkit.com", full_name="T Done", password_hash=hash_password("x1y2z3"), must_change_password=False, platforms=["blinkit"], store_count=0),
    ]
    db.add_all(made)
    db.commit()
    try:
        assert client.get(f"{API}/external-accounts", headers=emp).status_code == 403
        r = client.get(f"{API}/external-accounts?q=t-", headers=admin).json()
        assert r["total"] == 3 and r["vendors"] >= 1 and r["pocs"] >= 2
        assert "password" not in str(r["items"][0].keys()).replace("must_change_password", "")
        assert client.get(f"{API}/external-accounts?kind=vendor&q=t-vend", headers=admin).json()["total"] == 1
        csv_text = client.get(f"{API}/external-accounts/export?q=t-", headers=admin).text
        assert "t-vend@supplier.com,123456" in csv_text and "t-poc@blinkit.com,t-poc@123" in csv_text
        assert "t-done@blinkit.com,," in csv_text                       # already changed: no password shown
        d = client.get(f"{API}/external-accounts/{made[0].id}", headers=admin).json()
        assert d["account"]["email"] == "t-vend@supplier.com" and d["stores"] == []
    finally:
        for a in made:
            db.delete(a)
        db.commit()
