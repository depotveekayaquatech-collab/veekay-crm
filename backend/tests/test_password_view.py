"""Developer password view (encrypted readable copy + days since change) and the sign-in fixes: a stray space around the password or the
Employee ID must not turn a correct password into 'incorrect', and a password a person set stays exactly what they set."""
from app.models.user import User

from .conftest import API, auth, login

PASSWORDS = f"{API}/employees/passwords"
DEV_PW = "Dev-Pass-2026x"        # the `dev` fixture's own password: the section stays locked until it is given


def _open(client, who, password=DEV_PW):
    return client.post(PASSWORDS, headers=who, json={"password": password})


def _create(client, admin, code, password):
    r = client.post(f"{API}/employees", headers=admin, json={"employee_code": code, "full_name": "Pw Test", "password": password})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _row(client, dev, code):
    r = _open(client, dev)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    return next(x for x in r.json() if x["employee_code"] == code)


def test_only_the_developer_can_open_the_password_list(client, admin, emp, dev):
    assert _open(client, dev).status_code == 200
    for who in (admin, emp):                                           # not even a full admin: the route looks like it does not exist
        r = _open(client, who, "Pass@123")
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_a_password_set_by_an_admin_is_readable_and_dated(client, admin, dev, db):
    uid = _create(client, admin, "T-PW-ONE", "Start-Pw-2026a")
    try:
        row = _row(client, dev, "T-PW-ONE")
        assert row["password"] == "Start-Pw-2026a" and row["days_since_change"] == 0 and row["changed_date_exact"] is True
        assert row["must_change_password"] is True
        assert "Start-Pw-2026a" not in db.get(User, uid).password_enc            # stored encrypted, never plain
    finally:
        db.query(User).filter(User.id == uid).delete(); db.commit()


def test_the_view_follows_the_password_the_person_chose_and_it_keeps_working(client, admin, dev, db):
    uid = _create(client, admin, "T-PW-TWO", "Start-Pw-2026b")
    try:
        token = login(client, "T-PW-TWO", "Start-Pw-2026b").json()["access_token"]
        r = client.post(f"{API}/auth/change-password", headers=auth(token),
                        json={"current_password": "Start-Pw-2026b", "new_password": "My-Own-Pw-2026"})
        assert r.status_code == 200, r.text
        assert _row(client, dev, "T-PW-TWO")["password"] == "My-Own-Pw-2026"
        for _ in range(3):                                                         # signing in again and again never alters it
            assert login(client, "T-PW-TWO", "My-Own-Pw-2026").status_code == 200
        assert _row(client, dev, "T-PW-TWO")["password"] == "My-Own-Pw-2026"
        assert login(client, "T-PW-TWO", "Start-Pw-2026b").status_code == 401      # the old one is gone
    finally:
        db.query(User).filter(User.id == uid).delete(); db.commit()


def test_a_stray_space_around_the_password_does_not_lock_anyone_out(client, admin, dev, db):
    uid = _create(client, admin, "T-PW-SPACE", "  Spaced-Pw-2026  ")                # pasted with spaces
    try:
        assert _row(client, dev, "T-PW-SPACE")["password"] == "Spaced-Pw-2026"     # stored as the visible text
        for typed in ("Spaced-Pw-2026", "Spaced-Pw-2026 ", " Spaced-Pw-2026", "  Spaced-Pw-2026  "):
            assert login(client, "T-PW-SPACE", typed).status_code == 200, repr(typed)
        assert login(client, "T-PW-SPACE", "Spaced-Pw-2027").status_code == 401
    finally:
        db.query(User).filter(User.id == uid).delete(); db.commit()


def test_a_password_saved_with_a_space_before_this_fix_still_signs_in(client, make_user, dev, db):
    code, _, uid = make_user(password="Old-Spaced-Pw1 ")                            # hashed exactly as typed, trailing space included
    assert login(client, code, "Old-Spaced-Pw1 ").status_code == 200               # the exact text keeps working...
    assert _row(client, dev, code)["password"] == "Old-Spaced-Pw1"                 # ...and is then stored as what the person sees
    assert login(client, code, "Old-Spaced-Pw1").status_code == 200                # so typing it without the space works from now on
    assert login(client, code, "Old-Spaced-Pw1 ").status_code == 200               # and with it still does


def test_an_existing_account_is_filled_in_by_its_next_sign_in(client, make_user, dev, db):
    code, pw, uid = make_user(password="Legacy-Pw-2026")
    row = _row(client, dev, code)
    assert row["password"] is None                                                 # bcrypt can't be reversed: not recorded yet
    assert login(client, code, pw).status_code == 200
    assert _row(client, dev, code)["password"] == "Legacy-Pw-2026"


def test_an_employee_id_stored_with_a_stray_space_still_signs_in(client, make_user, db):
    code, pw, uid = make_user(password="Spacey-Code-1")
    u = db.get(User, uid)
    u.employee_code = f" {code} "
    db.commit()
    assert login(client, code, pw).status_code == 200
    assert login(client, code.lower(), pw).status_code == 200


def test_reset_shows_the_same_temporary_password_to_the_developer(client, admin, dev, db):
    uid = _create(client, admin, "T-PW-RESET", "Start-Pw-2026c")
    try:
        temp = client.post(f"{API}/employees/{uid}/reset-password", headers=admin).json()["temp_password"]
        row = _row(client, dev, "T-PW-RESET")
        assert row["password"] == temp and row["must_change_password"] is True
        assert login(client, "T-PW-RESET", temp).status_code == 200
    finally:
        db.query(User).filter(User.id == uid).delete(); db.commit()


def test_opening_the_list_writes_nothing_to_the_audit_log(client, dev, db):
    from app.models.audit_log import AuditLog

    before = db.query(AuditLog).count()
    _open(client, dev)
    db.expire_all()
    assert db.query(AuditLog).count() == before


def test_the_section_stays_locked_without_the_developers_own_password(client, dev):
    assert client.post(PASSWORDS, headers=dev, json={}).status_code == 422
    for wrong in ("", "nope-nope-nope", "Pass@123"):
        r = _open(client, dev, wrong)
        assert r.status_code == 403 and r.json()["detail"] == "Incorrect password."
    assert _open(client, dev).status_code == 200
    assert client.get(PASSWORDS, headers=dev).status_code in (405, 422)             # a plain GET returns nothing: only the unlock call does


def test_too_many_wrong_unlock_attempts_are_slowed_down(client, dev):
    codes = {_open(client, dev, f"wrong-{i}").status_code for i in range(12)}
    assert codes == {403, 429}


def test_a_developers_own_login_is_never_listed_or_kept(client, dev, db):
    rows = _open(client, dev).json()
    assert not any(r["category"] == "developer" or r["employee_code"].startswith("TD") for r in rows)
    mine = db.query(User).filter(User.employee_code.like("TD%")).all()
    assert mine and all(u.password_enc is None for u in mine)                       # signing in did not store a readable copy
