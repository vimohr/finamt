"""Employment-related expense rules for the 2025 assessment."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from .models import EmployeeCase, Expense, Payment, SourcedAmount, WorkAsset
from .provenance import CalculationTrace

if TYPE_CHECKING:
    from collections.abc import Iterable

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
HUNDRED = Decimal(100)
HELP_2025 = "https://www.elster.de/elsterweb/helpGlobal?themaGlobal=help_est_ufa_10_2025"
DEPRECIATION = "https://www.gesetze-im-internet.de/estg/__7.html"
DIGITAL_DEPRECIATION = (
    "https://grsth.bundesfinanzministerium.de/esth/2022/C-Anhaenge/Anhang-01/V/anhang-1-V.html"
)


def cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def record_payment(
    trace: CalculationTrace, key: str, payment: SourcedAmount, *, details: dict | None = None
) -> Decimal:
    facts = dict(details or {})
    if isinstance(payment, Payment):
        facts["paid_on"] = payment.paid_on.isoformat()
    sources = (payment.source,)
    if (
        isinstance(payment, Expense)
        and payment.payment_source
        and payment.payment_source != payment.source
    ):
        sources += (payment.payment_source,)
    trace.fact(key, payment.amount, "EUR", sources, details=facts or None)
    return payment.amount


def sum_payments(trace: CalculationTrace, key: str, payments: Iterable[SourcedAmount]) -> Decimal:
    parts = []
    amount = ZERO
    for i, payment in enumerate(sorted(payments, key=source_order), start=1):
        part = f"{key}.{i}"
        amount += record_payment(trace, part, payment)
        parts.append(part)
    trace.derive(key, amount, "EUR", "payments.sum", parts)
    return amount


def source_order(payment) -> tuple[str, int, str]:
    source = payment.source
    return source.document, source.page or 0, source.locator


def _allocated_asset_cost(
    trace: CalculationTrace, asset: WorkAsset, key: str, year: int
) -> Decimal:
    record_payment(
        trace,
        f"{key}.invoice",
        asset,
        details={"description": asset.description, "acquired_on": asset.acquired_on.isoformat()},
    )
    record_payment(trace, f"{key}.vat", asset.vat)
    trace.fact(
        f"{key}.share",
        asset.professional_percent,
        "%",
        (asset.usage_source,),
        details={
            "asset_kind": asset.asset_kind,
            "independently_usable": asset.independently_usable,
        },
    )
    inputs = [f"{key}.invoice", f"{key}.vat", f"{key}.share", "rule.asset.gwg_threshold"]
    base = cents(asset.amount * asset.professional_percent / HUNDRED)
    if asset.asset_kind == "digital":
        inputs.append("rule.asset.digital_life")
        amount = base if asset.acquired_on.year == year else ZERO
        rule = "asset.digital_full_year"
    elif asset.independently_usable and asset.amount - asset.vat.amount <= 800:
        amount = base if asset.acquired_on.year == year else ZERO
        rule = "asset.low_value_full_year"
    else:
        years, source = asset.useful_life_years, asset.useful_life_source
        if years is None or source is None:
            raise ValueError("Provide the useful life for a work asset subject to depreciation")
        trace.fact(f"{key}.life", years, "years", (source,))
        inputs.extend((f"{key}.life", "rule.asset.months_per_year"))
        life_months = years * 12
        months_before = (year - asset.acquired_on.year) * 12 - asset.acquired_on.month + 1
        before = min(life_months, max(0, months_before))
        after = min(life_months, max(0, months_before + 12))
        amount = cents(base * after / life_months) - cents(base * before / life_months)
        rule = "asset.straight_line_by_month"
    if asset.reimbursement:
        reimbursed = record_payment(trace, f"{key}.reimbursement", asset.reimbursement)
        if reimbursed > amount:
            raise ValueError("Asset reimbursement exceeds deductible depreciation for this year")
        inputs.append(f"{key}.reimbursement")
        amount -= reimbursed
    trace.derive(key, amount, "EUR", rule, inputs)
    return amount


def expense_totals(
    trace: CalculationTrace, case: EmployeeCase
) -> tuple[dict[str, Decimal], list[dict]]:
    categories = {
        "work_supplies": "work_equipment",
        "professional_association": "professional_association",
        "training": "training",
        "initial_training": "initial_training",
        "application": "other_work",
        "account_fees": "other_work",
        "other_work": "other_work",
    }
    totals = dict.fromkeys(categories.values(), ZERO)
    keys = {group: [] for group in totals}
    for i, payment in enumerate(sorted(case.expenses, key=source_order), start=1):
        key = f"expense.{i}"
        amount = record_payment(
            trace,
            f"{key}.payment",
            payment,
            details={"description": payment.description, "category": payment.category},
        )
        inputs = [f"{key}.payment"]
        if payment.reimbursement:
            amount -= record_payment(trace, f"{key}.reimbursement", payment.reimbursement)
            inputs.append(f"{key}.reimbursement")
        trace.derive(key, amount, "EUR", "expense.subtract_reimbursement", inputs)
        group = categories[payment.category]
        totals[group] += amount
        keys[group].append(key)

    if case.work_assets:
        trace.rule("rule.asset.gwg_threshold", Decimal("800"), "EUR", HELP_2025)
        trace.rule("rule.asset.digital_life", 1, "years", DIGITAL_DEPRECIATION)
        trace.rule("rule.asset.months_per_year", 12, "months", DEPRECIATION)
    for i, asset in enumerate(sorted(case.work_assets, key=source_order), start=1):
        key = f"asset.{i}"
        totals["work_equipment"] += _allocated_asset_cost(trace, asset, key, case.tax_year)
        keys["work_equipment"].append(key)

    for group, amount in totals.items():
        trace.derive(group, amount, "EUR", "expense.sum_category", keys[group])
    fields = [
        trace.form_field(key, line, code)
        for key, line, code in [
            ("professional_association", 53, "310"),
            ("work_equipment", 56, "320"),
            ("training", 60, "330"),
            ("other_work", 64, "380"),
        ]
        if keys[key]
    ]
    return totals, fields


def _month_limit(start: date) -> date:
    offset = start.month + 2
    year, month = start.year + offset // 12, offset % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def travel_totals(trace: CalculationTrace, case: EmployeeCase) -> tuple[Decimal, list[dict]]:
    if not (case.travel_days or case.travel_costs or case.travel_mileage):
        trace.derive("travel_deduction", ZERO, "EUR", "travel.no_claim", [])
        return ZERO, []

    fields = []
    reimbursements = {
        key: sum_payments(
            trace, f"travel_{key}", (item for item in case.travel_costs if item.category == key)
        )
        for key in ("reimbursement", "meal_reimbursement")
    }
    costs = {
        key: sum_payments(
            trace,
            f"travel_{key}_paid",
            (item for item in case.travel_costs if item.category == key),
        )
        for key in ("transport", "lodging", "incidentals")
    }
    mileage = ZERO
    mileage_keys = []
    rates = {"private_car": Decimal("0.30"), "other_private_motor_vehicle": Decimal("0.20")}
    for vehicle, amount in rates.items():
        trace.rule(f"rule.travel.{vehicle}", amount, "EUR/km", HELP_2025)
    for i, entry in enumerate(sorted(case.travel_mileage, key=source_order), start=1):
        key = f"travel_mileage.{i}"
        trace.fact(
            f"{key}.distance",
            entry.driven_km,
            "km",
            (entry.source,),
            details={"day": entry.day.isoformat(), "vehicle": entry.vehicle},
        )
        amount = cents(entry.driven_km * rates[entry.vehicle])
        trace.derive(
            key,
            amount,
            "EUR",
            "travel.driven_distance_rate",
            [f"{key}.distance", f"rule.travel.{entry.vehicle}"],
        )
        mileage += amount
        mileage_keys.append(key)
    transport = costs["transport"] + mileage
    trace.derive(
        "travel_transport",
        transport,
        "EUR",
        "travel.total_transport",
        ["travel_transport_paid", *mileage_keys],
    )
    total_travel_costs = transport + costs["lodging"] + costs["incidentals"]
    trace.derive(
        "travel_expenses_before_reimbursements",
        total_travel_costs,
        "EUR",
        "travel.sum_expenses",
        ["travel_transport", "travel_lodging_paid", "travel_incidentals_paid"],
    )
    for key, line, code in (
        ("travel_transport", 66, None),
        ("travel_lodging_paid", 67, None),
        ("travel_incidentals_paid", 68, None),
        ("travel_expenses_before_reimbursements", 69, "410"),
        ("travel_reimbursement", 71, "420"),
    ):
        if trace.entries[key]["value"] != "0.00":
            fields.append(trace.form_field(key, line, code))

    meal_amount, meal_fields = _travel_meals(trace, case)
    wage_meal_subsidies = sum(
        (item.amounts.get("20", ZERO) for item in case.wage_certificates), ZERO
    )
    trace.derive(
        "travel_payroll_meal_reimbursement",
        wage_meal_subsidies,
        "EUR",
        "payroll.sum_position_20",
        [
            f"wage.{item.document}.20"
            for item in sorted(case.wage_certificates, key=lambda item: item.document)
            if "20" in item.amounts
        ],
    )
    meal_reimbursements = wage_meal_subsidies + reimbursements["meal_reimbursement"]
    trace.derive(
        "travel_all_meal_reimbursements",
        meal_reimbursements,
        "EUR",
        "travel.sum_meal_reimbursements",
        ["travel_meal_reimbursement", "travel_payroll_meal_reimbursement"],
    )
    if meal_reimbursements:
        meal_fields.append(trace.form_field("travel_all_meal_reimbursements", 77, "490"))
    total = max(ZERO, total_travel_costs - reimbursements["reimbursement"])
    total += max(ZERO, meal_amount - meal_reimbursements)
    trace.derive(
        "travel_deduction",
        total,
        "EUR",
        "travel.subtract_reimbursements",
        [
            "travel_expenses_before_reimbursements",
            "travel_reimbursement",
            "travel_net_meals",
            "travel_all_meal_reimbursements",
        ],
    )
    return total, fields + meal_fields


def _travel_meals(trace: CalculationTrace, case: EmployeeCase) -> tuple[Decimal, list[dict]]:
    rates = {
        "day_trip": Decimal(14),
        "arrival": Decimal(14),
        "full_day": Decimal(28),
        "departure": Decimal(14),
    }
    reductions = {
        "breakfast": Decimal("5.60"),
        "lunch": Decimal("11.20"),
        "dinner": Decimal("11.20"),
    }
    trace.rule("rule.travel.short_absence_rate", Decimal(14), "EUR", HELP_2025)
    trace.rule("rule.travel.full_day_rate", Decimal(28), "EUR", HELP_2025)
    trace.rule("rule.travel.absence_minutes", 480, "minutes", HELP_2025)
    trace.rule("rule.travel.assignment_months", 3, "months", HELP_2025)
    for meal, value in reductions.items():
        trace.rule(f"rule.travel.{meal}_reduction", value, "EUR", HELP_2025)

    groups = {"short": [], "arrival_departure": [], "full": []}
    gross_total = ZERO
    deductions = ZERO
    gross_keys = []
    reduction_keys = []
    for entry in sorted(case.travel_days, key=lambda item: item.day):
        key = f"travel_day.{entry.day.isoformat()}"
        trace.fact(f"{key}.date", entry.day, "date", (entry.source,), details={"kind": entry.kind})
        inputs = [f"{key}.date"]
        if entry.absent_minutes is not None:
            trace.fact(f"{key}.absence", entry.absent_minutes, "minutes", (entry.source,))
            inputs.extend((f"{key}.absence", "rule.travel.absence_minutes"))
        start, source = entry.regularly_at_same_workplace_since, entry.assignment_source
        if start is not None and source is not None:
            trace.fact(f"{key}.assignment_start", start, "date", (source,))
            inputs.extend((f"{key}.assignment_start", "rule.travel.assignment_months"))
        gross = rates[entry.kind]
        if (entry.absent_minutes is not None and entry.absent_minutes <= 480) or (
            start and entry.day >= _month_limit(start)
        ):
            gross = ZERO
        trace.derive(
            f"{key}.allowance",
            gross,
            "EUR",
            "travel.meal_allowance_by_day",
            [
                *inputs,
                "rule.travel.full_day_rate"
                if entry.kind == "full_day"
                else "rule.travel.short_absence_rate",
            ],
        )
        gross_keys.append(f"{key}.allowance")
        gross_total += gross
        if gross:
            group = {"day_trip": "short", "full_day": "full"}.get(entry.kind, "arrival_departure")
            groups[group].append(f"{key}.allowance")
        day_reduction = ZERO
        meal_keys = [f"{key}.allowance"]
        for meal in sorted(entry.employer_meals, key=lambda meal: meal.kind):
            meal_key = f"{key}.{meal.kind}"
            trace.fact(meal_key, meal.kind, "meal", (meal.source,))
            meal_keys.extend((meal_key, f"rule.travel.{meal.kind}_reduction"))
            own = ZERO
            if meal.own_payment:
                own = record_payment(trace, f"{meal_key}.copayment", meal.own_payment)
                meal_keys.append(f"{meal_key}.copayment")
            day_reduction += max(ZERO, reductions[meal.kind] - own)
        applied = min(gross, day_reduction)
        deductions += applied
        trace.derive(
            f"{key}.reduction",
            applied,
            "EUR",
            "travel.cap_meal_reduction_at_daily_allowance",
            meal_keys,
        )
        reduction_keys.append(f"{key}.reduction")

    fields = []
    for group, line, code in (
        ("short", 72, "470"),
        ("arrival_departure", 73, "471"),
        ("full", 74, "472"),
    ):
        if groups[group]:
            key = f"travel_meal_days_{group}"
            trace.derive(key, len(groups[group]), "days", "travel.count_meal_days", groups[group])
            fields.append(trace.form_field(key, line, code))
    trace.derive(
        "travel_meals_before_reduction",
        gross_total,
        "EUR",
        "travel.sum_meal_allowances",
        gross_keys,
    )
    trace.derive(
        "travel_employer_meal_reductions",
        deductions,
        "EUR",
        "travel.sum_meal_reductions",
        reduction_keys,
    )
    if deductions:
        fields.append(trace.form_field("travel_employer_meal_reductions", 75, "473"))
    total = gross_total - deductions
    trace.derive(
        "travel_net_meals",
        total,
        "EUR",
        "travel.subtract_meal_reductions",
        ["travel_meals_before_reduction", "travel_employer_meal_reductions"],
    )
    return total, fields
