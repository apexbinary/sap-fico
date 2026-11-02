"""Request context: the logged-in user of the current request (set by the auth middleware)."""

from __future__ import annotations

from contextvars import ContextVar

current_user_code: ContextVar[str | None] = ContextVar("current_user_code", default=None)
current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
