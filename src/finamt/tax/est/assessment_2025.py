"""Annual assessment and ESt 1 A preview for the supported 2025 profile."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_DOWN, Decimal

from .deductions_2025 import insurance_deduction, payroll_total
from .expenses_2025 import CENT, HELP_2025, ZERO, cents, sum_payments
from .models import EmployeeCase, FilingProfile
from .provenance import CalculationTrace

_TARIFF_BASIS = (
    "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "IV-Tarif-31-34b/Paragraf-32a/paragraf-32a.html"
)
_WITHHOLDING_BASIS = (
    "https://esth.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "VI-Steuererhebung-36-47/1-Erhebung-der-Einkommensteuer-36-37b/Paragraf-36/inhalt.html"
)
_SOLIDARITY_2025 = "https://www.bundesfinanzministerium.de/Content/DE/Standardartikel/Themen/Steuern/das-aendert-sich-2025.html"
_SOLIDARITY_RATE_BASIS = "https://www.gesetze-im-internet.de/solzg_1995/__4.html"
_CHURCH_TAX_BASIS = "https://www.gesetze-im-internet.de/estg/__51a.html"
_CHURCH_TAX_RATES = "https://www.bundesfinanzministerium.de/Content/DE/Downloads/Broschueren_Bestellservice/steuern-von-a-z.pdf?__blob=publicationFile&v=8"
_AGE_RELIEF_BASIS = "https://www.gesetze-im-internet.de/estg/__24a.html"
_AGE_RELIEF_GUIDANCE = (
    "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "II-Einkommen-2-24b/8-Die-einzelnen-Einkunftsarten-13-24b/h-Gemeinsame-Vorschriften-24-24b/"
    "Paragraf-24a/paragraf-24a.html"
)
_AGE_RELIEF_TABLE = (
    ("40.0", 1900),
    ("38.4", 1824),
    ("36.8", 1748),
    ("35.2", 1672),
    ("33.6", 1596),
    ("32.0", 1520),
    ("30.4", 1444),
    ("28.8", 1368),
    ("27.2", 1292),
    ("25.6", 1216),
    ("24.0", 1140),
    ("22.4", 1064),
    ("20.8", 988),
    ("19.2", 912),
    ("17.6", 836),
    ("16.0", 760),
    ("15.2", 722),
    ("14.4", 684),
    ("14.0", 665),
    ("13.6", 646),
    ("13.2", 627),
)

_TARIFF = {
    "basic_allowance": Decimal(12096),
    "first_band_limit": Decimal(17443),
    "second_band_limit": Decimal(68480),
    "third_band_limit": Decimal(277825),
    "progression_divisor": Decimal(10000),
    "first_factor": Decimal("932.30"),
    "first_constant": Decimal(1400),
    "second_factor": Decimal("176.64"),
    "second_linear": Decimal(2397),
    "second_constant": Decimal("1015.13"),
    "third_rate": Decimal("0.42"),
    "third_offset": Decimal("10911.92"),
    "fourth_rate": Decimal("0.45"),
    "fourth_offset": Decimal("19246.67"),
}


def _tariff_2025(income: Decimal) -> tuple[Decimal, tuple[str, ...]]:
    """§ 32a EStG. Round the base down before applying a band, then floor the tax."""
    x = income.to_integral_value(rounding=ROUND_DOWN)
    values = _TARIFF
    basic, first, second, third = (
        values[key]
        for key in ("basic_allowance", "first_band_limit", "second_band_limit", "third_band_limit")
    )
    limits = ("basic_allowance", "first_band_limit", "second_band_limit", "third_band_limit")
    if x <= basic:
        return ZERO, limits[:1]
    if x <= first:
        y = (x - basic) / values["progression_divisor"]
        tax = (values["first_factor"] * y + values["first_constant"]) * y
        used = (*limits[:2], "progression_divisor", "first_factor", "first_constant")
    elif x <= second:
        z = (x - first) / values["progression_divisor"]
        tax = (values["second_factor"] * z + values["second_linear"]) * z + values[
            "second_constant"
        ]
        used = (
            *limits[:3],
            "progression_divisor",
            "second_factor",
            "second_linear",
            "second_constant",
        )
    elif x <= third:
        tax = x * values["third_rate"] - values["third_offset"]
        used = (*limits, "third_rate", "third_offset")
    else:
        tax = x * values["fourth_rate"] - values["fourth_offset"]
        used = (*limits, "fourth_rate", "fourth_offset")
    return tax.to_integral_value(rounding=ROUND_DOWN), used


def main_form(trace: CalculationTrace, profile: FilingProfile) -> list[dict]:
    taxpayer = profile.taxpayer
    trace.fact("filing.insurance", profile.insurance, "category", (profile.case_facts,))
    trace.fact(
        "filing.church_tax_region", profile.church_tax_region, "category", (profile.case_facts,)
    )
    fields = []
    for key, line in (
        ("tax_number", 4),
        ("tax_office", 5),
        ("tax_id", 8),
        ("date_of_birth", 8),
        ("last_name", 9),
        ("first_name", 10),
        ("occupation", 12),
        ("street", 13),
        ("house_number", 14),
        ("postcode", 15),
        ("city", 16),
        ("iban", 30),
    ):
        value = getattr(taxpayer, key)
        if value is not None:
            trace_key = f"taxpayer.{key}"
            trace.fact(
                trace_key, value, "date" if key == "date_of_birth" else "text", (taxpayer.source,)
            )
            fields.append(trace.form_field(trace_key, line))
    trace.fact("taxpayer.religion", profile.religion_code or "VD", "code", (profile.case_facts,))
    fields.append(trace.form_field("taxpayer.religion", 8))
    return sorted(fields, key=lambda field: field["line"])


def total_income_2025(
    trace: CalculationTrace, case: EmployeeCase, gross_wages: Decimal, employment_income: Decimal
) -> Decimal:
    relief = ZERO
    inputs = ["employment_income"]
    if case.filing:
        dob = case.filing.taxpayer.date_of_birth
        # The birthday's preceding day determines the completion of the age (§§ 187–188 BGB).
        first_year = dob.year + 65 - int(dob.month == 1 and dob.day == 1)
        trace.rule("rule.age_relief.age_threshold", 64, "years", _AGE_RELIEF_BASIS)
        trace.derive(
            "age_relief_first_year",
            first_year,
            "year",
            "age_relief.first_year_after_age_threshold",
            ["taxpayer.date_of_birth", "rule.age_relief.age_threshold"],
        )
        relief_inputs = ["age_relief_first_year"]
        if first_year <= 2025:
            rate, cap = _AGE_RELIEF_TABLE[max(first_year, 2005) - 2005]
            trace.rule("rule.age_relief.rate", Decimal(rate), "%", _AGE_RELIEF_BASIS)
            trace.rule("rule.age_relief.cap", Decimal(cap), "EUR", _AGE_RELIEF_BASIS)
            trace.rule("rule.age_relief.rounding_unit", Decimal(1), "EUR", _AGE_RELIEF_GUIDANCE)
            relief_inputs.extend(
                [
                    "gross_wages",
                    "rule.age_relief.rate",
                    "rule.age_relief.cap",
                    "rule.age_relief.rounding_unit",
                ]
            )
            relief = min(
                Decimal(cap),
                (gross_wages * Decimal(rate) / 100).to_integral_value(rounding=ROUND_CEILING),
            )
        trace.derive("age_relief", relief, "EUR", "age_relief.wage_share_capped", relief_inputs)
        inputs.append("age_relief")
    total = employment_income - relief
    trace.derive("total_income", total, "EUR", "assessment.sum_income_after_age_relief", inputs)
    return total


def estimate(
    trace: CalculationTrace,
    case: EmployeeCase,
    income: Decimal,
    insurance_amounts: dict[str, Decimal],
    special: dict[str, Decimal],
    household_credit: Decimal,
) -> dict:
    filing = case.filing
    assert filing is not None
    insurance, refund_overhang = insurance_deduction(trace, case, insurance_amounts)
    taxable = (
        income
        + refund_overhang
        + special["church_refund_overhang"]
        - insurance
        - special["special"]
    )
    trace.derive(
        "taxable_income",
        taxable,
        "EUR",
        "assessment.income_after_special_expenses",
        [
            "total_income",
            "insurance_refund_overhang",
            "church_tax_refund_overhang",
            "insurance_deduction",
            "special_expense_deduction",
        ],
    )

    for key, value in _TARIFF.items():
        unit = "EUR" if key.endswith(("allowance", "limit", "offset")) else "coefficient"
        trace.rule(f"rule.tariff.{key}", value, unit, _TARIFF_BASIS)
    tariff, used = _tariff_2025(taxable)
    trace.derive(
        "tariff_income_tax",
        tariff,
        "EUR",
        "assessment.tariff_2025",
        ["taxable_income", *[f"rule.tariff.{key}" for key in used]],
    )
    assessed = max(ZERO, tariff - special["political_credit"] - household_credit).to_integral_value(
        rounding=ROUND_DOWN
    )
    trace.derive(
        "assessed_income_tax",
        assessed,
        "EUR",
        "assessment.apply_tax_credits",
        ["tariff_income_tax", "political_donation_credit", "household_total_credit"],
    )

    exemption, rate, transition = Decimal(19950), Decimal("0.055"), Decimal("0.119")
    trace.rule("rule.solidarity.threshold", exemption, "EUR", _SOLIDARITY_2025)
    trace.rule("rule.solidarity.rate", rate, "fraction", _SOLIDARITY_RATE_BASIS)
    trace.rule("rule.solidarity.transition_rate", transition, "fraction", _SOLIDARITY_RATE_BASIS)
    solidarity = min(assessed * rate, max(ZERO, assessed - exemption) * transition)
    solidarity = solidarity.quantize(CENT, rounding=ROUND_DOWN)
    trace.derive(
        "assessed_solidarity",
        solidarity,
        "EUR",
        "assessment.solidarity_mitigation",
        [
            "assessed_income_tax",
            "rule.solidarity.threshold",
            "rule.solidarity.rate",
            "rule.solidarity.transition_rate",
        ],
    )
    church_rate = {
        "none": ZERO,
        "bavaria_baden_wuerttemberg": Decimal("0.08"),
        "other": Decimal("0.09"),
    }[filing.church_tax_region]
    trace.rule("rule.church.standard_rate", church_rate, "fraction", _CHURCH_TAX_RATES)
    church = cents(assessed * church_rate)
    trace.derive(
        "assessed_church_tax",
        church,
        "EUR",
        "assessment.standard_church_tax",
        ["assessed_income_tax", "filing.church_tax_region", "rule.church.standard_rate"],
    )

    withholding = payroll_total(trace, case, "income_tax_withheld", ("4",))
    solidarity_withholding = payroll_total(trace, case, "solidarity_withheld", ("5",))
    income_prepayments = sum_payments(
        trace, "income_tax_prepayments", filing.income_tax_prepayments
    )
    solidarity_prepayments = sum_payments(
        trace, "solidarity_prepayments", filing.solidarity_prepayments
    )
    trace.rule("rule.withholding.rounding_unit", Decimal(1), "EUR", _WITHHOLDING_BASIS)
    credit = withholding.to_integral_value(rounding=ROUND_CEILING)
    solidarity_credit = solidarity_withholding.to_integral_value(rounding=ROUND_CEILING)
    trace.derive(
        "income_tax_withholding_credit",
        credit,
        "EUR",
        "assessment.ceil_withholding",
        ["income_tax_withheld", "rule.withholding.rounding_unit"],
    )
    trace.derive(
        "solidarity_withholding_credit",
        solidarity_credit,
        "EUR",
        "assessment.ceil_withholding",
        ["solidarity_withheld", "rule.withholding.rounding_unit"],
    )
    income_balance = assessed - credit - income_prepayments
    solidarity_balance = solidarity - solidarity_credit - solidarity_prepayments
    church_paid = sum(
        (
            Decimal(trace.entries[key]["value"])
            for key in ("church_tax_withheld", "church_tax_prepayments")
        ),
        ZERO,
    )
    church_balance = church - church_paid
    trace.derive(
        "income_tax_balance",
        income_balance,
        "EUR",
        "assessment.tax_after_payments",
        ["assessed_income_tax", "income_tax_withholding_credit", "income_tax_prepayments"],
    )
    trace.derive(
        "solidarity_balance",
        solidarity_balance,
        "EUR",
        "assessment.solidarity_after_payments",
        ["assessed_solidarity", "solidarity_withholding_credit", "solidarity_prepayments"],
    )
    trace.derive(
        "church_tax_balance",
        church_balance,
        "EUR",
        "assessment.church_after_payments",
        ["assessed_church_tax", "church_tax_withheld", "church_tax_prepayments"],
    )
    trace.derive(
        "tax_balance",
        income_balance + solidarity_balance + church_balance,
        "EUR",
        "assessment.overall_balance_positive_is_due",
        ["income_tax_balance", "solidarity_balance", "church_tax_balance"],
    )
    return {
        "profile": "domestic_employee_single",
        "balance_sign": "positive_due_negative_refund",
        "references": {"tariff": _TARIFF_BASIS, "church_tax": _CHURCH_TAX_BASIS, "form": HELP_2025},
        "values": {
            key: trace.result(key)
            for key in (
                "age_relief",
                "total_income",
                "taxable_income",
                "insurance_deduction",
                "special_expense_deduction",
                "tariff_income_tax",
                "assessed_income_tax",
                "assessed_solidarity",
                "assessed_church_tax",
                "income_tax_balance",
                "solidarity_balance",
                "church_tax_balance",
                "tax_balance",
            )
        },
    }
