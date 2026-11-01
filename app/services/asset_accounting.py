"""Asset Accounting services — create asset, post acquisition, run depreciation.

Acquisitions post through the FI engine (asset debit line, account type 'A');
the engine resolves the APC account and writes ANEP/ANLC. The depreciation run
computes straight-line depreciation per asset and posts an FI document (debit
depreciation expense, credit accumulated depreciation) plus the ANLP record.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import (
    Asset,
    AssetAccountDetermination,
    AssetAllocation,
    AssetClass,
    AssetDepreciationTerms,
    AssetValues,
    DepreciationPosting,
)
from app.models.organizational import CompanyCode
from app.services.fiscal import PostingError
from app.services.posting import DocumentRequest, LineRequest, post_document

_CENT = Decimal("0.01")


def create_asset(
    session: Session, mandt: str, bukrs: str, anln1: str, anlkl: str, txt50: str,
    useful_life_years: int, *, anln2: str = "0000", kostl: str | None = None,
    scrap_value: Decimal = Decimal("0"), afabe: str = "01",
) -> Asset:
    """Create an asset master record with one depreciation area."""
    if session.get(AssetClass, (mandt, anlkl)) is None:
        raise PostingError(f"Asset class {anlkl} is not defined")
    asset = Asset(
        mandt=mandt, bukrs=bukrs, anln1=anln1, anln2=anln2, anlkl=anlkl, txt50=txt50,
        erdat=date.today().strftime("%Y%m%d"), ernam="API", xactive=True,
    )
    session.merge(asset)
    session.merge(
        AssetDepreciationTerms(
            mandt=mandt, bukrs=bukrs, anln1=anln1, anln2=anln2, afabe=afabe,
            afasl="LINR", ndjar=useful_life_years, ndper=0, schrw=scrap_value,
        )
    )
    if kostl:
        session.merge(
            AssetAllocation(
                mandt=mandt, bukrs=bukrs, anln1=anln1, anln2=anln2,
                adatu=date(1900, 1, 1), bdatu=date(9999, 12, 31), kostl=kostl,
            )
        )
    session.commit()
    return session.get(Asset, (mandt, bukrs, anln1, anln2))


def post_acquisition(
    session: Session, mandt: str, bukrs: str, anln1: str, amount: Decimal,
    budat: date, *, anln2: str = "0000", offset_account: str, offset_is_vendor: bool = True,
    waers: str | None = None, bktxt: str | None = None,
) -> dict:
    """Post an external asset acquisition (F-90 / ABZON style).

    Debit the asset (PK 70, transaction type 100); credit a vendor (PK 31) or a
    G/L / bank clearing account (PK 50).
    """
    cc = session.get(CompanyCode, (mandt, bukrs))
    if cc is None:
        raise PostingError(f"Company code {bukrs} does not exist")
    waers = waers or cc.waers
    offset = (
        LineRequest(bschl="31", account=offset_account, wrbtr=amount)
        if offset_is_vendor
        else LineRequest(bschl="50", account=offset_account, wrbtr=amount)
    )
    req = DocumentRequest(
        mandt=mandt, bukrs=bukrs, blart="AA", bldat=budat, budat=budat, waers=waers,
        bktxt=bktxt or f"Acquisition asset {anln1}",
        lines=[
            LineRequest(bschl="70", account=anln1, anln2=anln2, anbwa="100",
                        wrbtr=amount, sgtxt="Asset acquisition", bzdat=budat),
            offset,
        ],
    )
    header = post_document(session, req)

    # Capitalize the asset on first acquisition.
    asset = session.get(Asset, (mandt, bukrs, anln1, anln2))
    if asset and asset.aktiv is None:
        asset.aktiv = budat
        asset.zugdt = budat
        session.commit()
    return {"belnr": header.belnr, "gjahr": header.gjahr, "anln1": anln1, "amount": str(amount)}


def run_depreciation(
    session: Session, mandt: str, bukrs: str, gjahr: int, period: int,
    *, afabe: str = "01", budat: date | None = None,
) -> dict:
    """Straight-line depreciation posting run (RAPOST2000 style) for one period."""
    cc = session.get(CompanyCode, (mandt, bukrs))
    if cc is None:
        raise PostingError(f"Company code {bukrs} does not exist")
    budat = budat or _period_end(gjahr, period)
    run_no = f"{period:03d}{afabe}"

    det_cache: dict[str, AssetAccountDetermination] = {}
    results = []
    total = Decimal("0")

    terms = session.scalars(
        select(AssetDepreciationTerms).where(
            AssetDepreciationTerms.mandt == mandt,
            AssetDepreciationTerms.bukrs == bukrs,
            AssetDepreciationTerms.afabe == afabe,
            AssetDepreciationTerms.ndjar > 0,
        )
    ).all()

    for term in terms:
        asset = session.get(Asset, (mandt, bukrs, term.anln1, term.anln2))
        if asset is None or not asset.xactive:
            continue
        val = session.get(AssetValues, (mandt, bukrs, term.anln1, term.anln2, gjahr, afabe))
        if val is None:
            continue
        apc = (val.kansw or Decimal("0")) + (val.answl or Decimal("0")) - (val.abgan or Decimal("0"))
        depreciable = apc - (term.schrw or Decimal("0"))
        if depreciable <= 0:
            continue
        months = term.ndjar * 12 + term.ndper
        monthly = (depreciable / Decimal(months)).quantize(_CENT, ROUND_HALF_UP)
        already = (val.knafa or Decimal("0")) + (val.nafag or Decimal("0"))
        remaining = depreciable - already
        dep = min(monthly, remaining)
        if dep <= 0:
            continue

        # Resolve depreciation expense + accumulated depreciation accounts.
        anka = session.get(AssetClass, (mandt, asset.anlkl))
        det = det_cache.get(anka.ktogr) or session.get(
            AssetAccountDetermination, (mandt, cc.ktopl, anka.ktogr, afabe)
        )
        if det is None:
            raise PostingError(f"No account determination for {anka.ktogr}/area {afabe}")
        det_cache[anka.ktogr] = det

        alloc = session.get(AssetAllocation, (mandt, bukrs, term.anln1, term.anln2, date(1900, 1, 1)))
        kostl = alloc.kostl if alloc else None

        req = DocumentRequest(
            mandt=mandt, bukrs=bukrs, blart="AF", bldat=budat, budat=budat, waers=cc.waers,
            bktxt=f"Depreciation {term.anln1} period {period}", kokrs=cc.kokfi,
            lines=[
                LineRequest(bschl="40", account=det.ktaufw_dep, wrbtr=dep,
                            kostl=kostl, sgtxt=f"Depreciation {term.anln1}"),
                LineRequest(bschl="50", account=det.ktabg_dep, wrbtr=dep,
                            sgtxt=f"Accum. depreciation {term.anln1}"),
            ],
        )
        header = post_document(session, req)
        val.nafag = (val.nafag or Decimal("0")) + dep
        session.merge(
            DepreciationPosting(
                mandt=mandt, bukrs=bukrs, gjahr=gjahr, peraf=period, anln1=term.anln1,
                anln2=term.anln2, afbnr=run_no, afabe=afabe, nafaz=dep, belnr=header.belnr,
            )
        )
        session.commit()
        total += dep
        results.append({"anln1": term.anln1, "depreciation": str(dep), "belnr": header.belnr})

    return {"run": run_no, "period": period, "gjahr": gjahr, "posted": results, "total": str(total)}


def _period_end(gjahr: int, period: int) -> date:
    """Last day of a calendar-year posting period (simplified)."""
    import calendar

    month = min(max(period, 1), 12)
    return date(gjahr, month, calendar.monthrange(gjahr, month)[1])
