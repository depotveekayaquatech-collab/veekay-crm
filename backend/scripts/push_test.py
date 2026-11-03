"""
Send ONE test push message to one person's registered phones and say, phone by phone, whether Firebase accepted it.  Writes nothing to the database.

    python scripts/push_test.py --employee EMP001                 # lists the phones only (nothing is sent)
    python scripts/push_test.py --employee EMP001 --send          # sends "Aquatrack test"
    python scripts/push_test.py --vendor someone@example.com --send

Without --send it only shows how many phones are registered and whether the server has Firebase set up. With --send each phone gets one message and its
answer is printed: "sent" means Firebase accepted it for that phone; an "UNREGISTERED" / "INVALID_ARGUMENT" answer means that stored token is dead (app
uninstalled, data cleared, or a different Firebase project) and the phone will never receive anything until it logs in again.
Run it inside the API container to use production:   fly ssh console -C "python scripts/push_test.py --employee EMP001 --send"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.external_account import ExternalAccount  # noqa: E402
from app.models.external_activity import ExternalDevice, StaffDevice  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import external_notify  # noqa: E402

TITLE = "Aquatrack test"
BODY = "Push messages are working on this phone."


def find_devices(db, args) -> tuple[str, list[tuple[str, str, str]]]:
    """(who, [(platform, token, last seen)]) for the chosen person."""
    if args.employee:
        user = db.execute(select(User).where(func.lower(User.employee_code) == args.employee.strip().lower())).scalars().first()
        if user is None:
            sys.exit(f"No employee with code {args.employee!r}.")
        rows = db.execute(select(StaffDevice.platform, StaffDevice.token, StaffDevice.last_seen_at).where(StaffDevice.user_id == user.id)).all()
        return f"{user.full_name} ({user.employee_code})", [(p, t, str(s)) for p, t, s in rows]
    acct = db.execute(select(ExternalAccount).where(func.lower(ExternalAccount.email) == args.vendor.strip().lower())).scalars().first()
    if acct is None:
        sys.exit(f"No vendor / POC account with email {args.vendor!r}.")
    rows = db.execute(select(ExternalDevice.platform, ExternalDevice.token, ExternalDevice.last_seen_at).where(ExternalDevice.account_id == acct.id)).all()
    return f"{acct.full_name} <{acct.email}>", [(p, t, str(s)) for p, t, s in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--employee", help="employee code of a Veekay employee / admin")
    who.add_argument("--vendor", help="email of a vendor / POC account")
    ap.add_argument("--send", action="store_true", help="really send the message (default: only list the phones)")
    args = ap.parse_args()

    print(f"Firebase configured on this server: {external_notify.push_configured()}")
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        name, devices = find_devices(db, args)
    finally:
        db.close()
    print(f"{name}: {len(devices)} registered phone(s)")
    for platform, token, seen in devices:
        print(f"  {platform:8} last seen {seen}  token ...{token[-8:]}")
    if not args.send:
        print("Nothing sent (add --send to send the test message).")
        return 0
    if not devices:
        print("No phone to send to: this person must open the app and allow notifications first.")
        return 1
    messaging = external_notify._firebase()  # noqa: SLF001
    if messaging is None:
        print("Firebase is not available on this server (missing FIREBASE_CREDENTIALS_JSON or the package); nothing was sent.")
        return 1
    messages = [messaging.Message(token=t, notification=messaging.Notification(title=TITLE, body=BODY), data={"kind": "test", "ref_id": ""}) for _p, t, _s in devices]
    result = messaging.send_each(messages)
    for (platform, token, _seen), r in zip(devices, result.responses):
        if r.success:
            print(f"  {platform:8} ...{token[-8:]}  sent (Firebase accepted it)")
        else:
            code = getattr(r.exception, "code", None) or type(r.exception).__name__
            print(f"  {platform:8} ...{token[-8:]}  FAILED: {code} - {r.exception}")
    print(f"{result.success_count} accepted, {result.failure_count} failed.")
    return 0 if result.success_count else 1


if __name__ == "__main__":
    sys.exit(main())
