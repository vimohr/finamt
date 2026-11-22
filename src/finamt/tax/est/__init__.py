"""Build reviewable drafts for employee income tax."""

from pathlib import Path

from .extraction import review_wage_originals
from .models import EmployeeCase
from .provenance import CalculationTrace
from .rules_2025 import draft_2025

__all__ = ["EmployeeCase", "draft_annual_return"]

_TAX_YEARS = {2025: draft_2025}


def draft_annual_return(
    case: EmployeeCase,
    source_dir: Path | None = None,
    *,
    document_bytes: dict[str, bytes] | None = None,
) -> dict:
    """Verify the cited originals and apply the rules for the assessment year."""
    build_draft = _TAX_YEARS.get(case.tax_year)
    if build_draft is None:
        supported = ", ".join(str(year) for year in sorted(_TAX_YEARS))
        raise ValueError(
            f"Unsupported assessment year {case.tax_year}. Supported years: {supported}."
        )
    trace = CalculationTrace(
        case.documents,
        source_dir,
        document_bytes=document_bytes,
        keep_originals=frozenset(wage.document for wage in case.wage_certificates),
    )
    if missing := {wage.document for wage in case.wage_certificates}.difference(trace.originals):
        raise ValueError(f"Unknown source document {min(missing)}")
    return build_draft(case, trace, review_wage_originals(case, trace.originals))
