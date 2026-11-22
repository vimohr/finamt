"""Build reviewable drafts for employee income tax."""

from pathlib import Path

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
    return build_draft(
        case, CalculationTrace(case.documents, source_dir, document_bytes=document_bytes)
    )
