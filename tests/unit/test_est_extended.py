from __future__ import annotations

import json
from decimal import Decimal, localcontext
from hashlib import sha256

import pytest
from pydantic import ValidationError

from finamt.tax.est import EmployeeCase, draft_annual_return
from finamt.tax.est.assessment_2025 import _tariff_2025


def source(locator):
    return {"document": "evidence", "locator": locator}


def payment(locator, amount, **details):
    return {"paid_on": "2025-06-02", "amount": amount, "source": source(locator), **details}


def asset(locator, amount, **details):
    return {"acquired_on": "2025-06-02", "amount": amount, "source": source(locator), **details}


@pytest.fixture
def full_case():
    originals = {
        "evidence": b"Synthetic receipt register and declaration",
        "wage": b"Synthetic wage statement 2025",
    }
    data = {
        "schema_version": 1,
        "tax_year": 2025,
        "reviewed_standard_case": True,
        "documents": {
            key: {"path": f"{key}.txt", "sha256": sha256(original).hexdigest()}
            for key, original in originals.items()
        },
        "wage_certificates": [
            {
                "document": "wage",
                "transfer_ticket": "SYNTHETIC-2025",
                "period_end": "2025-12-31",
                "tax_class": 1,
                "amounts": {
                    "3": "50000.00",
                    "4": "8350.10",
                    "5": "0.00",
                    "6": "0.00",
                    "22a": "4650.00",
                    "23a": "4650.00",
                    "25": "4500.00",
                    "26": "1000.00",
                    "27": "650.00",
                },
            }
        ],
        "intake": {
            "version": "2025.1",
            "answers": {
                "residence": "yes",
                "single_assessment": "yes",
                "children": "no",
                "foreign": "no",
                "other_income": "no",
                "replacement_benefits": "no",
                "special_wages": "no",
                "insurance_change": "no",
                "commute_exceptions": "no",
                "additional_deductions": "no",
            },
            "wage_certificate_count": 1,
        },
        "filing": {
            "taxpayer": {
                "first_name": "Test",
                "last_name": "Muster",
                "date_of_birth": "1985-04-03",
                "street": "Musterstraße",
                "house_number": "1",
                "postcode": "12345",
                "city": "Musterstadt",
                "source": source("Profil"),
            },
            "case_facts": source("Fallbestätigung"),
            "all_income_and_payments_reviewed": True,
            "insurance": "statutory_with_sick_pay",
        },
    }
    return data, originals


def draft(full_case):
    data, originals = full_case
    case = EmployeeCase.model_validate_json(json.dumps(data))
    return draft_annual_return(case, document_bytes=originals)


def test_wage_profile_vorsorge_and_federal_tax_balance(full_case):
    result = draft(full_case)
    values = result["assessment"]["values"]
    assert values["insurance_deduction"]["value"] == "9970.00"
    assert values["special_expense_deduction"]["value"] == "36.00"
    assert values["taxable_income"]["value"] == "38764.00"
    assert values["assessed_income_tax"]["value"] == "6928.00"
    assert values["tax_balance"]["value"] == "-1423.00"
    main = {field["key"]: field["line"] for field in result["forms"]["ESt 1 A"]}
    assert main["taxpayer.date_of_birth"] == 8
    assert main["taxpayer.house_number"] == 14
    assert result["trace"]["pension_employee"]["inputs"] == ["wage.wage.23a"]
    assert result["trace"]["income_tax_withholding_credit"]["value"] == "8351.00"
    with localcontext() as context:
        context.prec = 3
        assert draft(full_case) == result


@pytest.mark.parametrize(
    ("tax_base", "tax"),
    [
        ("12096.99", 0),
        ("17443", 1015),
        ("17444", 1015),
        ("68480", 17849),
        ("68481", 17850),
        ("277825", 105774),
        ("277826", 105775),
    ],
)
def test_assessment_tariff_reference_thresholds(tax_base, tax):
    assert _tariff_2025(Decimal(tax_base))[0] == Decimal(tax)


def test_work_expenses_education_and_depreciation(full_case):
    data, _ = full_case
    data["expenses"] = [
        payment(
            "Fortbildung",
            "900.00",
            description="Fachkurs",
            category="training",
            reimbursement=payment("Fortbildung AG", "100.00"),
        ),
        payment("Erstausbildung", "9000", description="Erststudium", category="initial_training"),
        payment("Bewerbung", "16.00", description="Bewerbungsporto", category="application"),
    ]
    data["work_assets"] = [
        asset(
            "Computer",
            "1190",
            description="Laptop",
            vat={"amount": "190", "source": source("Computer VAT")},
            professional_percent="60",
            usage_source=source("Laptopnutzung"),
            asset_kind="digital",
            independently_usable=True,
        ),
        asset(
            "Stuhl",
            "720",
            description="Bürostuhl",
            vat={"amount": "0", "source": source("Stuhl ohne USt")},
            professional_percent="100",
            usage_source=source("Stuhlnutzung"),
            asset_kind="other",
            independently_usable=True,
        ),
        asset(
            "Tisch",
            "1200",
            description="Schreibtisch",
            vat={"amount": "0", "source": source("Tisch ohne USt")},
            professional_percent="100",
            usage_source=source("Tischnutzung"),
            asset_kind="other",
            independently_usable=True,
            useful_life_years=4,
            useful_life_source=source("Nutzungsdauer"),
            acquired_on="2025-10-01",
        ),
    ]
    result = draft(full_case)
    summary = result["summary"]
    assert summary["work_equipment"]["value"] == "1509.00"
    assert summary["training"]["value"] == "800.00"
    assert summary["employment_deduction"]["value"] == "2325.00"
    assert result["trace"]["initial_training_deduction"]["value"] == "6000.00"
    assert result["forms"]["Anlage Sonderausgaben"][0]["line"] == 13
    assert result["trace"]["asset.1.share"]["sources"] == [source("Laptopnutzung")]


def test_domestic_travel_with_time_meals_mileage_and_employer_reimbursements(full_case):
    data, _ = full_case
    data["wage_certificates"][0]["amounts"]["20"] = "4.00"
    data["travel_days"] = [
        {
            "day": "2025-05-11",
            "kind": "day_trip",
            "absent_minutes": 480,
            "source": source("8 hours"),
        },
        {
            "day": "2025-05-12",
            "kind": "day_trip",
            "absent_minutes": 481,
            "source": source("8 hours 1 minute"),
            "employer_meals": [
                {
                    "kind": "lunch",
                    "source": source("lunch"),
                    "own_payment": {"amount": "3.20", "source": source("lunch copayment")},
                }
            ],
        },
        {"day": "2025-05-13", "kind": "arrival", "source": source("arrival")},
        {
            "day": "2025-05-14",
            "kind": "full_day",
            "source": source("full"),
            "employer_meals": [{"kind": "breakfast", "source": source("breakfast")}],
        },
        {
            "day": "2025-05-15",
            "kind": "departure",
            "source": source("departure"),
            "regularly_at_same_workplace_since": "2025-02-01",
            "assignment_source": source("work assignment"),
        },
    ]
    data["travel_costs"] = [
        payment("room", "110.25", category="lodging"),
        payment("parking", "5", category="incidentals"),
        payment("travel reimbursed", "50.25", category="reimbursement"),
    ]
    data["travel_mileage"] = [
        {
            "day": "2025-05-12",
            "driven_km": "100.00",
            "vehicle": "private_car",
            "source": source("mileage"),
        },
    ]
    result = draft(full_case)
    trace = result["trace"]
    assert trace["travel_meals_before_reduction"]["value"] == "56.00"
    assert trace["travel_employer_meal_reductions"]["value"] == "13.60"
    assert trace["travel_deduction"]["value"] == "133.40"
    assert next(field for field in result["fields"] if field["line"] == 77)["value"] == "4.00"
    assert trace["travel_day.2025-05-15.assignment_start"]["sources"] == [source("work assignment")]


def test_donations_and_household_are_deducted_at_different_stages(full_case):
    data, _ = full_case
    data["donations"] = [
        payment(
            "Spendenbescheinigung",
            "20000",
            category="charitable_domestic",
            recipient="Fiktiver Verein",
        ),
        payment(
            "Parteispendenbescheinigung",
            "3000",
            category="political_party",
            recipient="Fiktive Partei",
        ),
    ]
    data["donation_carryforward"] = {
        "amount": "50.00",
        "source": source("festgestellter Spendenvortrag"),
    }
    data["household_costs"] = [
        payment(
            "Lohnanteil Handwerker",
            "7500",
            category="craft",
            description="Renovierung",
            invoice_total={"amount": "11000", "source": source("Rechnung Renovierung")},
            payment_source=source("Überweisung Renovierung"),
            payment_method="account",
            household_in_eu_eea=True,
        ),
        payment(
            "Barzahlung",
            "900",
            category="service",
            description="Haushaltshilfe",
            invoice_total={"amount": "900", "source": source("Quittung")},
            payment_source=source("Kasse"),
            payment_method="cash",
            household_in_eu_eea=True,
        ),
    ]
    result = draft(full_case)
    trace = result["trace"]
    assert trace["charitable_donation_deduction"]["value"] == "9754.00"
    assert trace["remaining_charitable_donations"]["value"] == "10296.00"
    assert trace["political_donation_credit"]["value"] == "825.00"
    assert trace["political_party_special_deduction"]["value"] == "1350.00"
    assert trace["household_total_credit"]["value"] == "1200.00"
    assert result["findings"][0]["code"] == "household_not_eligible"
    assert result["forms"]["Anlage Sonstiges"][0]["line"] == 16
    assert set(result["forms"]) >= {
        "Anlage N",
        "Anlage Sonderausgaben",
        "Anlage Haushaltsnahe Aufwendungen",
    }


def test_private_basic_costs_displace_other_insurance_and_employer_subsidy_is_deducted(full_case):
    data, _ = full_case
    data["filing"]["insurance"] = "private"
    amounts = data["wage_certificates"][0]["amounts"]
    del amounts["25"], amounts["26"]
    amounts["24b"] = "2800"
    data["insurance_payments"] = [
        payment("PKV Beitragsbescheinigung", "6400", category="private_basic_health"),
        payment("Pflegepflicht", "750", category="private_care"),
        payment("Erstattung PKV", "500", category="private_basic_health_refund"),
        payment("Haftpflicht", "300", category="liability_accident_term_life"),
    ]
    result = draft(full_case)
    assert result["trace"]["net_basic_insurance"]["value"] == "3850.00"
    assert result["trace"]["deductible_other_insurance"]["value"] == "0.00"
    assert result["trace"]["insurance_deduction"]["value"] == "8500.00"


def test_supplemental_church_payment_only_credits_prepayment_for_the_assessment_year(full_case):
    data, _ = full_case
    data["filing"].update(church_tax_region="bavaria_baden_wuerttemberg", religion_code="EV")
    data["wage_certificates"][0]["amounts"]["6"] = "300.00"
    data["church_tax_payments"] = [
        payment("Nachzahlung Vorjahr", "200", category="paid"),
        payment("Vorauszahlung 2025", "49", category="prepayment"),
        payment("Erstattung Vorjahr", "100", category="refunded"),
    ]
    trace = draft(full_case)["trace"]
    assert trace["net_church_tax_paid"]["value"] == "449.00"
    assert trace["church_tax_balance"]["inputs"] == [
        "assessed_church_tax",
        "church_tax_withheld",
        "church_tax_prepayments",
    ]


def test_expenses_detect_duplicate_source_and_reject_unconfirmed_scope(full_case):
    data, _ = full_case
    data["expenses"] = [payment("duplicate", "200", description="Fachkurs", category="training")]
    data["donations"] = [
        payment("duplicate", "200", category="charitable_domestic", recipient="Test")
    ]
    with pytest.raises(ValidationError, match="only once"):
        draft(full_case)
    data["donations"].clear()
    data["filing"]["all_income_and_payments_reviewed"] = False
    with pytest.raises(ValidationError, match="Confirm all"):
        draft(full_case)


def test_case_totals_point_to_confirmed_facts_or_year_rules(full_case):
    result = draft(full_case)
    trace = result["trace"]

    def resolve(key, ancestors):
        assert key not in ancestors
        entry = trace[key]
        if "sources" in entry:
            assert all(source["document"] in result["documents"] for source in entry["sources"])
        elif "legal_basis" in entry:
            assert entry["legal_basis"].startswith("https://")
        else:
            for child in entry["inputs"]:
                resolve(child, ancestors | {key})

    for entry in result["assessment"]["values"].values():
        resolve(entry["trace"], set())


@pytest.mark.parametrize(
    ("key", "answer", "expected"),
    [
        ("residence", "unsure", "intake_unresolved"),
        ("foreign", "yes", "intake_outside_scope"),
        ("single_assessment", "no", "intake_outside_scope"),
        ("replacement_benefits", "yes", "intake_outside_scope"),
    ],
)
def test_open_or_special_situation_keeps_the_draft_without_an_assessment(
    full_case, key, answer, expected
):
    data, _ = full_case
    data["intake"]["answers"][key] = answer
    result = draft(full_case)
    assert result["assessment"] is None
    assert "taxable_income" not in result["trace"]
    assert result["forms"]["Anlage N"]
    assert any(item["code"] == expected and item["question"] == key for item in result["findings"])


def test_older_filing_without_intake_and_wrong_certificate_count_are_caught(full_case):
    data, _ = full_case
    intake = data.pop("intake")
    result = draft(full_case)
    assert result["assessment"] is None
    assert "intake_missing" in {item["code"] for item in result["findings"]}
    data["intake"] = {**intake, "wage_certificate_count": 2}
    result = draft(full_case)
    assert result["assessment"] is None
    assert "intake_payroll_count_differs" in {item["code"] for item in result["findings"]}


def test_class_two_is_checked_against_childless_intake(full_case):
    data, _ = full_case
    data["wage_certificates"][0]["tax_class"] = 2
    result = draft(full_case)
    assert result["assessment"] is None
    assert "payroll_class_2" in {item["code"] for item in result["findings"]}


@pytest.mark.parametrize(
    ("birth_date", "wage", "relief"),
    [
        ("1938-07-02", "50000.00", "1900.00"),
        ("1960-01-01", "50000.00", "646.00"),
        ("1961-01-01", "50000.00", "627.00"),
        ("1961-01-01", "1000.01", "133.00"),
        ("1961-01-02", "50000.00", "0.00"),
    ],
)
def test_age_relief_uses_birthday_cohort_gross_wage_and_rounding(
    full_case, birth_date, wage, relief
):
    data, _ = full_case
    data["filing"]["taxpayer"]["date_of_birth"] = birth_date
    data["wage_certificates"][0]["amounts"]["3"] = wage
    result = draft(full_case)
    assert result["assessment"]["values"]["age_relief"]["value"] == relief
    assert "taxpayer.date_of_birth" in result["trace"]["age_relief_first_year"]["inputs"]
    assert "total_income" in result["trace"]["taxable_income"]["inputs"]


def test_cannot_claim_home_office_during_a_full_day_away(full_case):
    data, _ = full_case
    data["travel_days"] = [
        {"day": "2025-05-11", "kind": "full_day", "source": source("trip")},
    ]
    data["workdays"] = [
        {
            "day": "2025-05-11",
            "attended_first_workplace": False,
            "home_work": "predominantly",
            "permanently_without_other_workplace": False,
            "sources": [source("work log")],
        },
    ]
    with pytest.raises(ValidationError, match="24-hour absence"):
        draft(full_case)
