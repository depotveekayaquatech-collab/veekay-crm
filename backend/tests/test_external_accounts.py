"""Vendor / POC login format: names -> emails, passwords, shared names split by phone, placeholders skipped."""
import uuid

from app.services.external_account_service import local_part, plan_for, primary_number


def _rows(*items):
    return [{"name": n, "number": num, "store_id": uuid.uuid4(), "platform": "blinkit"} for n, num in items]


def test_local_part_and_numbers():
    assert local_part("Ajay Singh") == "ajaysingh" and local_part("M.S Enterprises") == "msenterprises"
    assert local_part("#N/A") == "na"
    assert primary_number("9035454807 / 9108505863") == "9035454807"
    assert primary_number("+91 90354-54807") == "9035454807"
    assert primary_number("#N/A") is None


def test_vendor_format_and_one_account_per_person():
    people, skipped, split = plan_for(_rows(("ARUN", "9845300066"), ("Arun", "98453 00066"), ("Sahil Arora", None)), "vendor")
    by = {p.email: p for p in people}
    assert set(by) == {"arun@supplier.com", "sahilarora@supplier.com"} and not skipped and not split
    assert by["arun@supplier.com"].password == "123456" and len(by["arun@supplier.com"].store_ids) == 2


def test_poc_format():
    people, _, _ = plan_for(_rows(("Ajay Singh", "8718062031")), "poc")
    assert (people[0].email, people[0].password) == ("ajaysingh@blinkit.com", "ajaysingh@123")


def test_same_name_different_phones_are_different_people():
    people, _, split = plan_for(_rows(("Sanjay", "8607000435"), ("SANJAY", "7488815366"), ("Sanjay", "8607000435")), "poc")
    assert split == {"sanjay": 2}
    assert {(p.email, p.password) for p in people} == {("sanjay0435@blinkit.com", "sanjay0435@123"), ("sanjay5366@blinkit.com", "sanjay5366@123")}


def test_same_last_four_falls_back_to_the_full_number():
    people, _, _ = plan_for(_rows(("Rahul", "9000011111"), ("Rahul", "9111111111")), "vendor")
    assert {p.email for p in people} == {"rahul9000011111@supplier.com", "rahul9111111111@supplier.com"}


def test_placeholders_and_blanks_are_skipped():
    people, skipped, _ = plan_for(_rows(("#N/A", None), ("NA", None), ("", None), ("-", None), ("Real Person", None)), "poc")
    assert [p.email for p in people] == ["realperson@blinkit.com"] and len(skipped) == 3


def test_creating_many_logins_hashes_each_distinct_password_once(db, make_store, monkeypatch):
    """500 logins used to mean 500 slow password hashes (minutes). Every vendor starts with the same password, so it is hashed once;
    the POCs' own passwords are hashed once each, and every account still verifies."""
    from app.core.security import verify_password
    from app.models.external_account import ExternalAccount
    from app.models.organization import Organization
    from app.services import external_account_service as svc

    org = db.query(Organization).filter_by(slug="veekay").one()
    stores = [make_store(code=f"EXT-B{i}", name=f"Ext Bulk Mart {i}") for i in range(6)]
    vendors, _, _ = plan_for([{"name": f"Bulkvendor{i}", "number": None, "store_id": stores[i].id, "platform": "blinkit"} for i in range(6)], "vendor")
    pocs, _, _ = plan_for([{"name": f"Bulkpoc{i}", "number": None, "store_id": stores[i].id, "platform": "blinkit"} for i in range(6)], "poc")
    calls = []
    real = svc.hash_password
    monkeypatch.setattr(svc, "hash_password", lambda p: (calls.append(p), real(p))[1])
    out = svc.apply(db, org.id, [svc.Plan(vendors, [], {}), svc.Plan(pocs, [], {})])
    assert out == {"created": 12, "updated": 0}
    assert len(calls) == 1 + 6                                   # one for every vendor's "123456", one per POC
    rows = {a.email: a for a in db.query(ExternalAccount).filter(ExternalAccount.email.like("bulk%@%"))}
    assert verify_password("123456", rows["bulkvendor3@supplier.com"].password_hash)
    assert verify_password("bulkpoc2@123", rows["bulkpoc2@blinkit.com"].password_hash)
    # running it again creates nothing and keeps the passwords
    again = svc.apply(db, org.id, [svc.Plan(vendors, [], {}), svc.Plan(pocs, [], {})])
    assert again == {"created": 0, "updated": 12} and len(calls) == 7
    for a in rows.values():
        db.query(ExternalAccount).filter_by(id=a.id).delete()
    db.commit()
