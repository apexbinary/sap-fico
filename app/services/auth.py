"""Authentication and general authorizations.

Passwords are stored as PBKDF2-SHA256 hashes with a random salt. A login creates a session
(OUSS) whose token travels in the B1SESSION cookie (or an Authorization: Bearer header).
Every /api request is checked against the general authorizations (USR3): reading needs R or
F for the area of the path, changing needs F; superusers may do everything. Reference data the
forms of every area need (company, lookups, lists of accounts, partners, items ...) can be read
by any logged-in user.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.users import User, UserPermission, UserSession
from app.services.admin import B1Error

ITERATIONS = 200_000
SESSION_HOURS = 12

# general authorization areas (USR3 PermId) and their names
PERMISSIONS = {
    "ADMIN": "Administration (setup, users, tax setup)",
    "COA": "Chart of accounts",
    "JE": "Journal entries",
    "FINRPT": "Financial reports",
    "BP": "Business partner master data",
    "ITEMS": "Items, warehouses, price lists",
    "SALES": "Sales - A/R documents",
    "PURCH": "Purchasing - A/P documents",
    "INV": "Inventory documents",
    "BANK": "Banking (payments, deposits, bank statements, payment wizard)",
    "DUNNING": "Dunning",
    "FXREVAL": "Exchange rate differences",
    "COCKPIT": "Cockpit",
}
SALES_OBJS, PURCH_OBJS, INV_OBJS = {"23", "17", "15", "16", "13", "14"}, {"540000006", "22", "20", "21", "18", "19"}, {"59", "60", "67"}

# (path prefix, area); the first match wins. None: any logged-in user may read and write
ROUTES = [
    ("/api/auth/", None), ("/api/cockpit", "COCKPIT"),
    ("/api/users", "ADMIN"), ("/api/admin", "ADMIN"), ("/api/tax", "ADMIN"), ("/api/sales-employees", "ADMIN"),
    ("/api/projects", "ADMIN"), ("/api/manufacturers", "ITEMS"), ("/api/transaction-codes", "ADMIN"),
    ("/api/master", "ADMIN"), ("/api/print-layouts", "ADMIN"),
    ("/api/accounts", "COA"), ("/api/journal-entries", "JE"),
    ("/api/reports", "FINRPT"), ("/api/gst-returns", "FINRPT"), ("/api/e-documents", "SALES"), ("/api/withholding-tax", "ADMIN"), ("/api/exchange-rate-differences", "FXREVAL"),
    ("/api/partners", "BP"), ("/api/partner-groups", "BP"),
    ("/api/items", "ITEMS"), ("/api/item-groups", "ITEMS"), ("/api/warehouses", "ITEMS"), ("/api/price-lists", "ITEMS"),
    ("/api/inventory", "INV"),
    ("/api/payments", "BANK"), ("/api/checks", "BANK"), ("/api/deposits", "BANK"), ("/api/house-banks", "BANK"),
    ("/api/banks", "BANK"), ("/api/house-bank-accounts", "BANK"), ("/api/bank-statements", "BANK"),
    ("/api/bank-reconciliation", "BANK"), ("/api/payment-wizard", "BANK"),
    ("/api/dunning", "DUNNING"),
]
# reference data every logged-in user may read (GET), whatever the area
SHARED_READS = re.compile(r"^/api/(admin/(company|lookups|exchange-rates)|master/lookups|tax/setup|accounts$|partners(/[^/]+)?$|"
                          r"partner-groups$|items(/[^/]+(/price)?)?$|item-groups$|warehouses$|price-lists$|documents/types$|"
                          r"payments/open-items$|house-banks$|dunning/terms$|print-layouts$|withholding-tax$)")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(check, digest)


def check_password_rules(password: str) -> None:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise B1Error("A password needs at least 8 characters with letters and digits")


# ------------------------------------------------------------- sessions
def login(session: Session, user_code: str, password: str) -> tuple[User, str]:
    user = session.scalar(select(User).where(func.lower(User.user_code) == (user_code or "").strip().lower()))
    if user is None or not verify_password(password or "", user.password):
        raise B1Error("Wrong user code or password")
    if user.locked == "Y":
        raise B1Error(f"User {user.user_code} is locked")
    now = datetime.utcnow()
    session.query(UserSession).filter(UserSession.expires < now).delete()
    token = secrets.token_urlsafe(32)
    session.add(UserSession(token=token, user_id=user.user_id, created=now, expires=now + timedelta(hours=SESSION_HOURS)))
    user.last_login = now
    session.commit()
    return user, token


def logout(session: Session, token: str | None) -> None:
    if token:
        session.query(UserSession).filter(UserSession.token == token).delete()
        session.commit()


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    s = session.get(UserSession, token)
    if s is None or s.expires < datetime.utcnow():
        return None
    user = session.get(User, s.user_id)
    return None if user is None or user.locked == "Y" else user


# ------------------------------------------------------------- authorizations
def permissions(session: Session, user: User) -> dict[str, str]:
    if user.superuser == "Y":
        return {p: "F" for p in PERMISSIONS}
    saved = {p.perm_id: p.permission for p in session.scalars(select(UserPermission).where(UserPermission.user_link == user.user_id))}
    return {p: saved.get(p, "N") for p in PERMISSIONS}


def area_of(path: str) -> str | None:
    """Authorization area of an API path (documents by their object type)."""
    m = re.match(r"^/api/documents/([0-9]+)", path)
    if m:
        obj = m.group(1)
        return "SALES" if obj in SALES_OBJS else "PURCH" if obj in PURCH_OBJS else "INV" if obj in INV_OBJS else "ADMIN"
    for prefix, area in ROUTES:
        if path.startswith(prefix):
            return area
    return "ADMIN"  # anything not listed needs administration rights


def authorize(session: Session, user: User, method: str, path: str) -> None:
    """Raise B1Error when the user may not call the path with the method."""
    if user.superuser == "Y":
        return
    if method == "GET" and SHARED_READS.match(path):
        return
    area = area_of(path)
    if area is None:
        return
    level = permissions(session, user).get(area, "N")
    if level == "F" or (level == "R" and method in {"GET", "HEAD", "OPTIONS"}):
        return
    what = "read" if method == "GET" else "change"
    raise B1Error(f"No authorization to {what} {PERMISSIONS[area].lower()}")


# ------------------------------------------------------------- maintenance
def save_user(session: Session, data: dict, user_id: int | None = None, acting: User | None = None) -> User:
    if user_id is None:
        code = (data.get("user_code") or "").strip()
        if not re.match(r"^[A-Za-z0-9_.-]{2,25}$", code):
            raise B1Error("A user code has 2-25 letters, digits, '.', '_' or '-'")
        if session.scalar(select(User).where(func.lower(User.user_code) == code.lower())) is not None:
            raise B1Error(f"User {code} already exists")
        if not data.get("password"):
            raise B1Error("Enter an initial password")
        user = User(user_id=(session.scalar(select(func.max(User.user_id))) or 0) + 1, user_code=code)
        session.add(user)
    else:
        user = session.get(User, user_id)
        if user is None:
            raise B1Error(f"User {user_id} does not exist")
    for key in ("u_name", "e_mail", "department"):
        if key in data and data[key] is not None:
            setattr(user, key, data[key])
    if not user.u_name:
        user.u_name = user.user_code
    if data.get("password"):
        check_password_rules(data["password"])
        user.password = hash_password(data["password"])
        session.query(UserSession).filter(UserSession.user_id == user.user_id).delete()  # log out everywhere
    for key, col in (("superuser", "superuser"), ("locked", "locked")):
        if data.get(key) is not None:
            setattr(user, col, "Y" if data[key] else "N")
    if acting is not None and acting.user_id == user.user_id and (user.locked == "Y" or user.superuser != "Y" and acting.superuser == "Y"):
        raise B1Error("You cannot lock yourself or remove your own superuser rights")
    session.flush()
    if not session.scalar(select(func.count()).select_from(User).where(User.superuser == "Y", User.locked == "N")):
        raise B1Error("At least one unlocked superuser must remain")
    if user.locked == "Y":
        session.query(UserSession).filter(UserSession.user_id == user.user_id).delete()
    session.commit()
    return user


def save_permissions(session: Session, user_id: int, perms: dict[str, str]) -> None:
    if session.get(User, user_id) is None:
        raise B1Error(f"User {user_id} does not exist")
    for perm, value in perms.items():
        if perm not in PERMISSIONS or value not in {"F", "R", "N"}:
            raise B1Error(f"Unknown authorization {perm}={value}")
        session.merge(UserPermission(user_link=user_id, perm_id=perm, permission=value))
    session.commit()


def change_password(session: Session, user: User, old: str, new: str) -> None:
    if not verify_password(old or "", user.password):
        raise B1Error("The current password is wrong")
    check_password_rules(new)
    user.password = hash_password(new)
    session.commit()
