"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class LineIn(BaseModel):
    bschl: str = Field(..., description="Posting key (e.g. 40 debit G/L, 50 credit G/L, 01 customer, 31 vendor)")
    account: str = Field(..., description="G/L account, or customer/vendor number")
    wrbtr: Decimal = Field(..., description="Amount in document currency")
    mwskz: str | None = Field(None, description="Tax code")
    calculate_tax: bool = Field(False, description="Auto-generate the tax line from this base line")
    sgtxt: str | None = None
    zuonr: str | None = None
    gsber: str | None = None
    kostl: str | None = None
    aufnr: str | None = None
    prctr: str | None = None
    zterm: str | None = None
    umskz: str | None = None
    zlsch: str | None = Field(None, description="Payment method (e.g. T bank transfer)")
    zlspr: str | None = Field(None, description="Payment block (e.g. A blocked for payment)")


class DocumentIn(BaseModel):
    bukrs: str = Field(..., description="Company code")
    blart: str = Field(..., description="Document type (SA, DR, KR, ...)")
    bldat: date = Field(..., description="Document date")
    budat: date = Field(..., description="Posting date")
    waers: str = Field(..., description="Document currency")
    kursf: Decimal | None = Field(None, description="Exchange rate to local currency (default: TCURR rate M)")
    xblnr: str | None = None
    bktxt: str | None = None
    usnam: str = "SYSTEM"
    tcode: str | None = None
    kokrs: str | None = None
    lines: list[LineIn]


class LineOut(BaseModel):
    buzei: int
    bschl: str
    koart: str
    shkzg: str
    hkont: str
    kunnr: str | None
    lifnr: str | None
    wrbtr: Decimal
    dmbtr: Decimal
    mwskz: str | None
    sgtxt: str | None
    zterm: str | None = None
    augbl: str | None = None
    rebzg: str | None = None

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    bukrs: str
    belnr: str
    gjahr: int
    blart: str
    budat: date
    bldat: date | None = None
    monat: int
    waers: str
    xblnr: str | None = None
    bktxt: str | None = None
    tcode: str | None = None
    bstat: str = " "
    stblg: str | None = None
    stjah: int | None = None
    stgrd: str | None = None
    items: list[LineOut]

    class Config:
        from_attributes = True
