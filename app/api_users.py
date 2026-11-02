"""REST endpoints: login / logout, the current user, user maintenance and authorizations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.models.users import User
from app.services import auth

router = APIRouter()
COOKIE = "B1SESSION"


def token_of(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else request.cookies.get(COOKIE)


def _user_out(s: Session, u: User) -> dict:
    return {"user_id": u.user_id, "user_code": u.user_code, "u_name": u.u_name, "e_mail": u.e_mail,
            "department": u.department, "superuser": u.superuser == "Y", "locked": u.locked == "Y",
            "last_login": u.last_login, "permissions": auth.permissions(s, u)}


class LoginIn(BaseModel):
    user_code: str
    password: str


@router.post("/auth/login", tags=["Users"], summary="Log in: sets the B1SESSION cookie")
def login(body: LoginIn, response: Response, s: Session = Depends(get_session)) -> dict:
    try:
        user, token = auth.login(s, body.user_code, body.password)
    except auth.B1Error as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=auth.SESSION_HOURS * 3600)
    return {**_user_out(s, user), "token": token}


@router.post("/auth/logout", tags=["Users"], summary="Log out")
def logout(request: Request, response: Response, s: Session = Depends(get_session)) -> dict:
    auth.logout(s, token_of(request))
    response.delete_cookie(COOKIE)
    return {"logged_out": True}


def current_user(request: Request, s: Session = Depends(get_session)) -> User:
    user = auth.user_for_token(s, token_of(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


@router.get("/auth/me", tags=["Users"], summary="The logged-in user with its authorizations")
def me(user: User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    return {**_user_out(s, user), "areas": auth.PERMISSIONS}


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/auth/password", tags=["Users"], summary="Change the own password")
def change_password(body: PasswordIn, user: User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    run(lambda: auth.change_password(s, user, body.old_password, body.new_password))
    return {"changed": True}


@router.get("/users", tags=["Users"], summary="Users (OUSR) with their authorizations (USR3)")
def users(s: Session = Depends(get_session)) -> dict:
    return {"areas": auth.PERMISSIONS,
            "users": [_user_out(s, u) for u in s.scalars(select(User).order_by(User.user_code))]}


class UserIn(BaseModel):
    user_code: str | None = Field(None, max_length=25)
    u_name: str | None = Field(None, max_length=155)
    e_mail: str | None = Field(None, max_length=100)
    department: str | None = Field(None, max_length=50)
    superuser: bool | None = None
    locked: bool | None = None
    password: str | None = None
    permissions: dict[str, str] | None = None


def _save(s: Session, body: UserIn, user_id: int | None, acting: User) -> dict:
    data = body.model_dump()
    user = run(lambda: auth.save_user(s, data, user_id, acting))
    if body.permissions:
        run(lambda: auth.save_permissions(s, user.user_id, body.permissions))
    return _user_out(s, user)


@router.post("/users", tags=["Users"], summary="Add a user")
def add_user(body: UserIn, acting: User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    return _save(s, body, None, acting)


@router.patch("/users/{user_id}", tags=["Users"], summary="Change a user, its password or authorizations")
def update_user(user_id: int, body: UserIn, acting: User = Depends(current_user), s: Session = Depends(get_session)) -> dict:
    return _save(s, body, user_id, acting)
