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
