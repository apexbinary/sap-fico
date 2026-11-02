"""REST endpoints: cockpit (home screen) data and the user's widget layout."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.admin import CockpitWidget
from app.services import cockpit

router = APIRouter()
def _user() -> str:
    from app.context import current_user_code

    return current_user_code.get() or "manager"


@router.get("/cockpit", tags=["Cockpit"], summary="KPIs, analyses, open documents and alerts")
def data(on: date | None = None, s: Session = Depends(get_session)) -> dict:
    return cockpit.cockpit(s, on)


def _layout(s: Session) -> list[dict]:
    saved = {w.widget_id: w for w in s.scalars(select(CockpitWidget).where(CockpitWidget.user_sign == _user()))}
    titles = dict(cockpit.WIDGETS)
    rows = [{"id": wid, "title": titles[wid], "visible": saved[wid].visible == "Y" if wid in saved else True,
             "position": saved[wid].position if wid in saved else 100 + n} for n, (wid, _) in enumerate(cockpit.WIDGETS)]
    return sorted(rows, key=lambda r: r["position"])


@router.get("/cockpit/layout", tags=["Cockpit"], summary="Widgets of the user's cockpit in their order")
def layout(s: Session = Depends(get_session)) -> list[dict]:
    return _layout(s)


class WidgetIn(BaseModel):
    id: str
    visible: bool


@router.put("/cockpit/layout", tags=["Cockpit"], summary="Save the order and visibility of the widgets")
def save_layout(body: list[WidgetIn], s: Session = Depends(get_session)) -> list[dict]:
    known = dict(cockpit.WIDGETS)
    for n, w in enumerate(body):
        if w.id not in known:
            raise HTTPException(status_code=422, detail=f"Unknown widget {w.id}")
        s.merge(CockpitWidget(user_sign=_user(), widget_id=w.id, position=n, visible="Y" if w.visible else "N"))
    s.commit()
    return _layout(s)
