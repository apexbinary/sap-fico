"""REST endpoints: print layouts per document type (RDOC) and the company logo."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api_finance import run
from app.database import get_session
from app.services import printing

router = APIRouter()


@router.get("/print-layouts", tags=["Printing"], summary="Print layouts, styles and document types")
def list_layouts(obj: str | None = None, s: Session = Depends(get_session)) -> dict:
    return {"layouts": [printing.layout_out(l) for l in printing.layouts(s, obj)],
            "styles": printing.STYLES, "types": printing.TITLES}


class LayoutIn(BaseModel):
    doc_code: str | None = Field(None, max_length=20)
    doc_name: str | None = Field(None, max_length=100)
    type_code: str | None = Field(None, max_length=20)
    style: str | None = None
    color: str | None = Field(None, max_length=7)
    show_logo: bool | None = None
    show_hsn: bool | None = None
    show_bank: bool | None = None
    show_sign: bool | None = None
    footer: str | None = Field(None, max_length=254)
    default: bool | None = None


@router.post("/print-layouts", tags=["Printing"], summary="Add a print layout")
def add_layout(body: LayoutIn, s: Session = Depends(get_session)) -> dict:
    return printing.layout_out(run(lambda: printing.save_layout(s, body.model_dump(exclude_unset=True))))


@router.patch("/print-layouts/{code}", tags=["Printing"], summary="Change a print layout")
def update_layout(code: str, body: LayoutIn, s: Session = Depends(get_session)) -> dict:
    return printing.layout_out(run(lambda: printing.save_layout(s, body.model_dump(exclude_unset=True), code)))


@router.delete("/print-layouts/{code}", tags=["Printing"], summary="Remove a print layout (not the default)")
def remove_layout(code: str, s: Session = Depends(get_session)) -> dict:
    run(lambda: printing.delete_layout(s, code))
    return {"deleted": code}


class LogoIn(BaseModel):
    image: str | None = Field(None, max_length=800_000)  # data URL; None removes the logo


@router.get("/admin/company/logo", tags=["Administration"], summary="Company logo (data URL) for printed documents")
def get_logo(s: Session = Depends(get_session)) -> dict:
    from app.services.admin import company

    return {"image": run(lambda: company(s)).logo_image}


@router.put("/admin/company/logo", tags=["Administration"], summary="Upload (or remove) the company logo")
def put_logo(body: LogoIn, s: Session = Depends(get_session)) -> dict:
    run(lambda: printing.save_logo(s, body.image))
    return {"has_logo": bool(body.image)}
