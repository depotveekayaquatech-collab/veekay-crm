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


def test_a_developer_can_build_the_logins_from_the_stores_with_a_preview_first(client, dev, admin, emp, db, make_store):
    import uuid

    tag = uuid.uuid4().hex[:6]
    make_store(code=f"LG-{tag}", platform="blinkit", vendor=f"Vendor Gen {tag}")
    before = {a.email for a in db.query(ExternalAccount).all()}
    gen = f"{API}/external-accounts/generate"
    try:
        for who in (admin, emp):                                                    # only the developer may do this
            assert client.post(gen, headers=who, json={}).status_code == 403
        preview = client.post(gen, headers=dev, json={"platform": "blinkit"}).json()
        assert preview["dry_run"] is True and preview["vendors"]["accounts"] >= 1 and preview["applied"] is None
        assert {a.email for a in db.query(ExternalAccount).all()} == before        # a preview writes nothing
        done = client.post(gen, headers=dev, json={"platform": "blinkit", "dry_run": False}).json()
        assert done["applied"]["created"] >= 1
        db.expire_all()
        mine = db.query(ExternalAccount).filter(ExternalAccount.email == f"vendorgen{tag}@supplier.com").one()
        assert mine.must_change_password is True and mine.store_count == 1
        listed = client.get(f"{API}/external-accounts?q=vendorgen{tag}", headers=admin).json()
        assert listed["total"] == 1
        again = client.post(gen, headers=dev, json={"platform": "blinkit", "dry_run": False}).json()
        assert again["applied"]["created"] == 0                                    # safe to repeat: nothing is created twice
        assert "external_accounts.generated" in str(client.get(f"{API}/activity", headers=dev, params={"page_size": 50}).json())
    finally:
        for a in db.query(ExternalAccount).all():
            if a.email not in before:
                db.delete(a)
        db.commit()
