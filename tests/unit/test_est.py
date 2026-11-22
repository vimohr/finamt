from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import localcontext
from hashlib import sha256

import fitz
import pytest
from pydantic import ValidationError

from finamt.tax.est import EmployeeCase, draft_annual_return


def _document(path, content):
    path.write_bytes(content)
    return {"path": path.name, "sha256": sha256(content).hexdigest()}


def _source(document, locator):
    return {"document": document, "locator": locator}


def _day(day, *, workplace=False, home="none", other_workplace=True):
    day = day.isoformat() if isinstance(day, date) else day
    return {
        "day": day,
        "attended_first_workplace": workplace,
        "home_work": home,
        "permanently_without_other_workplace": not other_workplace,
        "sources": [_source("calendar", day)],
    }


@pytest.fixture
def case_data(tmp_path):
    return {
        "schema_version": 1,
        "tax_year": 2025,
        "reviewed_standard_case": True,
        "documents": {
            "wage": _document(tmp_path / "wage.txt", b"Synthetic wage certificate"),
            "calendar": _document(tmp_path / "calendar.txt", b"Synthetic calendar"),
            "route": _document(tmp_path / "route.txt", b"Synthetic route"),
        },
        "wage_certificates": [
            {
                "document": "wage",
                "transfer_ticket": "SYNTHETIC-01",
                "period_end": "2025-12-31",
                "tax_class": 1,
                "amounts": {"3": "40000.02", "4": "7100.32", "5": "0.00", "6": "395.60"},
            }
        ],
    }


def _draft(data, source_dir):
    return draft_annual_return(EmployeeCase.model_validate_json(json.dumps(data)), source_dir)


def _commute(distance="23.45", mode="own_or_provided_car", **kwargs):
    return {
        "distance_km": distance,
        "mode": mode,
        "source": _source("route", "Kürzeste Straßenverbindung"),
        **kwargs,
    }


def test_payroll_mapping_subtotals_and_trace(case_data, tmp_path):
    case_data["documents"]["second"] = _document(tmp_path / "second.txt", b"Another certificate")
    case_data["documents"]["third"] = _document(tmp_path / "third.txt", b"A third certificate")
    case_data["wage_certificates"] += [
        {
            "document": "second",
            "transfer_ticket": "SYNTHETIC-02",
            "period_end": "2025-12-31",
            "tax_class": 6,
            "amounts": {"3": "3125.58", "4": "451.13", "5": "24.81", "6": "40.60"},
        },
        {
            "document": "third",
            "transfer_ticket": "SYNTHETIC-03",
            "period_end": "2025-06-30",
            "tax_class": 1,
            "amounts": {"3": "625.40", "4": "120.00"},
        },
    ]
    draft = _draft(case_data, tmp_path)

    assert draft["status"] == "draft"
    assert draft["tax_year"] == 2025
    assert draft["rules_version"] == "2025.1"
    assert draft["form_mapping_version"] == "anlage-n-2025.1"
    assert {field["kennzahl"]: (field["line"], field["value"]) for field in draft["fields"]} == {
        "110": (5, "40625.42"),
        "111": (5, "3125.58"),
        "140": (6, "7220.32"),
        "141": (6, "451.13"),
        "150": (7, "0.00"),
        "151": (7, "24.81"),
        "142": (8, "395.60"),
        "143": (8, "40.60"),
    }
    trace = draft["trace"]
    assert draft["summary"]["gross_wages"]["value"] == "43751.00"
    assert trace["gross_wages_classes_1_to_5"]["inputs"] == [
        "wage.third.3",
        "wage.third.tax_class",
        "wage.wage.3",
        "wage.wage.tax_class",
    ]
    assert trace["wage.wage.3"]["sources"] == [_source("wage", "Nr. 3")]
    assert (
        draft["documents"]["wage"]["sha256"]
        == sha256((tmp_path / "wage.txt").read_bytes()).hexdigest()
    )
    assert "SYNTHETIC-01" not in json.dumps(draft)
    case_data["wage_certificates"].reverse()
    with localcontext() as context:
        context.prec = 3
        assert _draft(case_data, tmp_path) == draft


@pytest.mark.parametrize(
    ("distance", "expected"),
    [("0.999", "0.00"), ("20.999", "6.00"), ("21.00", "6.38")],
)
def test_commute_uses_full_km_and_the_2025_rate_bands(case_data, tmp_path, distance, expected):
    case_data["commute"] = _commute(distance)
    case_data["workdays"] = [_day("2025-01-02", workplace=True)]
    draft = _draft(case_data, tmp_path)
    assert draft["summary"]["commute_deduction"]["value"] == expected
    commute_fields = {
        field["line"]: field for field in draft["fields"] if field["key"].startswith("commute")
    }
    assert commute_fields[29]["value"] == 1
    assert commute_fields[30]["kennzahl"] == "111"
    assert commute_fields[31]["kennzahl"] == "112"
    assert commute_fields[30]["value"] == commute_fields[31]["value"]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("own_or_provided_car", "6734.00"), ("other", "4500.00"), ("public_transport", "4500.00")],
)
def test_commute_cap_depends_on_the_vehicle(case_data, tmp_path, mode, expected):
    case_data["commute"] = _commute("100", mode)
    case_data["workdays"] = [
        _day(date(2025, 1, 1) + timedelta(days=offset), workplace=True) for offset in range(185)
    ]
    assert _draft(case_data, tmp_path)["summary"]["commute_deduction"]["value"] == expected


@pytest.mark.parametrize(
    ("ticket_cost", "tax_free_reimbursement", "expected"),
    [
        ("4780.10", "600.05", "4079.95"),
        ("2000.00", "600.05", "3799.85"),
        ("100.00", "4900.00", "0.00"),
    ],
)
def test_public_transport_comparison_and_employer_reimbursements(
    case_data, tmp_path, ticket_cost, tax_free_reimbursement, expected
):
    case_data["commute"] = _commute(
        "100",
        "public_transport",
        public_transport_costs=[
            {"amount": ticket_cost, "source": _source("route", "Fahrkartensumme im Kalenderjahr")}
        ],
    )
    case_data["workdays"] = [
        _day(date(2025, 1, 1) + timedelta(days=offset), workplace=True) for offset in range(185)
    ]
    case_data["wage_certificates"][0]["amounts"].update(
        {"17": tax_free_reimbursement, "18": "100.10"}
    )
    draft = _draft(case_data, tmp_path)
    assert draft["summary"]["commute_deduction"]["value"] == expected
    assert draft["trace"]["commute_reimbursements"]["inputs"] == [
        "tax_free_commute_reimbursements",
        "flat_rate_taxed_commute_reimbursements",
    ]
    assert {
        field["kennzahl"]: field["value"] for field in draft["fields"] if field["line"] == 51
    } == {
        "290": tax_free_reimbursement,
        "295": "100.10",
    }


def test_home_office_counts_each_day_in_one_group(case_data, tmp_path):
    case_data["commute"] = _commute()
    case_data["workdays"] = [
        _day("2025-01-01", home="predominantly"),
        _day("2025-01-02", home="predominantly", workplace=True),
        _day("2025-01-03", home="partly", workplace=True, other_workplace=False),
        _day("2025-01-04", home="predominantly", other_workplace=False),
        _day("2025-01-05", home="partly"),
        _day("2025-01-06", other_workplace=False),
    ]
    draft = _draft(case_data, tmp_path)
    assert draft["summary"]["commute_deduction"]["value"] == "14.28"
    assert draft["summary"]["home_office_deduction"]["value"] == "18.00"
    assert draft["summary"]["supported_expenses"]["value"] == "32.28"
    assert draft["summary"]["employment_deduction"]["value"] == "1230.00"
    assert draft["summary"]["employment_income"]["value"] == "38770.02"
    home_fields = [field for field in draft["fields"] if field["line"] >= 58]
    assert [(field["line"], field["kennzahl"], field["value"]) for field in home_fields] == [
        (58, "335", 1),
        (59, "336", 2),
    ]
    trace = draft["trace"]
    assert trace["home_office_regular_days"]["inputs"] == ["workday.2025-01-01"]
    assert trace["home_office_no_other_workplace_days"]["inputs"] == [
        "workday.2025-01-03",
        "workday.2025-01-04",
    ]
    assert trace["workday.2025-01-03"]["sources"] == [_source("calendar", "2025-01-03")]
    assert trace["rule.home_office.rate"]["legal_basis"].startswith("https://")


def test_home_office_cap_spans_both_groups_and_actual_costs_can_exceed_allowance(
    case_data, tmp_path
):
    case_data["workdays"] = [
        _day(
            date(2025, 1, 1) + timedelta(days=offset),
            home="predominantly",
            other_workplace=offset < 120,
        )
        for offset in range(225)
    ]
    draft = _draft(case_data, tmp_path)
    assert draft["summary"]["employment_deduction"]["value"] == "1260.00"
    assert draft["trace"]["home_office_regular_days"]["value"] == 120
    assert draft["trace"]["home_office_no_other_workplace_days"]["value"] == 105


def test_employee_allowance_is_limited_to_gross_wages(case_data, tmp_path):
    case_data["wage_certificates"][0]["amounts"] = {"3": "160.48"}
    draft = _draft(case_data, tmp_path)
    assert draft["summary"]["employment_deduction"]["value"] == "160.48"
    assert draft["summary"]["employment_income"]["value"] == "0.00"


@pytest.mark.parametrize("amount", [0.1, True, "1,00", "1.001", "-1.00", "NaN"])
def test_rejects_inexact_or_unsupported_amounts(case_data, tmp_path, amount):
    case_data["wage_certificates"][0]["amounts"]["3"] = amount
    with pytest.raises(ValidationError):
        _draft(case_data, tmp_path)


def test_rejects_unreviewed_or_cross_year_facts(case_data, tmp_path):
    case_data["reviewed_standard_case"] = False
    with pytest.raises(ValidationError, match="Confirm the transcribed data"):
        _draft(case_data, tmp_path)
    case_data["reviewed_standard_case"] = True
    case_data["workdays"] = [_day("2026-01-01", home="predominantly")]
    with pytest.raises(ValidationError, match="Workdays must be in the assessment year"):
        _draft(case_data, tmp_path)
    case_data["tax_year"] = 2026
    with pytest.raises(ValidationError, match="Wage certificate period"):
        _draft(case_data, tmp_path)
    case_data["wage_certificates"][0]["period_end"] = "2026-12-31"
    with pytest.raises(ValueError, match="Unsupported assessment year 2026"):
        _draft(case_data, tmp_path)


def test_rejects_duplicate_wage_certificate_and_workday(case_data, tmp_path):
    certificate = case_data["wage_certificates"][0]
    case_data["documents"]["copy"] = _document(
        tmp_path / "copy.txt", b"A re-export of the statement"
    )
    case_data["wage_certificates"].append({**certificate, "document": "copy"})
    with pytest.raises(ValidationError, match="Duplicate wage certificate"):
        _draft(case_data, tmp_path)
    case_data["wage_certificates"].pop()
    day = _day("2025-01-05", home="predominantly")
    case_data["workdays"] = [day, day]
    with pytest.raises(ValidationError, match="one calendar entry per workday"):
        _draft(case_data, tmp_path)


def test_missing_route_and_missing_source_are_rejected(case_data, tmp_path):
    case_data["workdays"] = [_day("2025-01-02", workplace=True)]
    with pytest.raises(ValidationError, match="Provide a commute route"):
        _draft(case_data, tmp_path)
    case_data["commute"] = _commute()
    case_data["workdays"][0]["sources"][0]["document"] = "missing"
    with pytest.raises(ValueError, match="Unknown source document missing"):
        _draft(case_data, tmp_path)


def test_document_substitution_is_rejected(case_data, tmp_path):
    (tmp_path / "wage.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch for source document wage"):
        _draft(case_data, tmp_path)
    (tmp_path / "wage.txt").unlink()
    with pytest.raises(ValueError, match="Source document wage is missing"):
        _draft(case_data, tmp_path)


def test_pdf_reference_is_checked_and_preserved(case_data, tmp_path):
    certificate = case_data["wage_certificates"][0]
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Synthetic wage certificate")
        case_data["documents"]["wage"] = _document(tmp_path / "wage.pdf", pdf.tobytes())
    with pytest.raises(ValueError, match="Provide a valid PDF page"):
        _draft(case_data, tmp_path)
    certificate["page"] = 2
    with pytest.raises(ValueError, match="Provide a valid PDF page"):
        _draft(case_data, tmp_path)
    certificate["page"] = 1
    result = _draft(case_data, tmp_path)
    assert result["trace"]["wage.wage.3"]["sources"] == [
        {"document": "wage", "locator": "Nr. 3", "page": 1}
    ]
