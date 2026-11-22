"""Vorsorgeaufwand, Sonderausgaben and tax reductions for 2025."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .expenses_2025 import (
    HELP_2025,
    HUNDRED,
    ZERO,
    cents,
    record_payment,
    source_order,
    sum_payments,
)
from .models import EmployeeCase
from .provenance import CalculationTrace

_PENSION_BASIS = "https://ao.bundesfinanzministerium.de/esth/2025/tabellarische-Uebersicht/Vorsorgeaufwendunge.html"
_SPECIAL_BASIS = (
    "https://esth.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "II-Einkommen-2-24b/5-Sonderausgaben-10-10g/Paragraf-10/paragraf-10.html"
)
_DONATION_BASIS = (
    "https://esth.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "II-Einkommen-2-24b/5-Sonderausgaben-10-10g/Paragraf-10b/paragraf-10b.html"
)
_POLITICAL_BASIS = (
    "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "V-Steuerermaessigungen-34c-35c/2b-Steuerermaessigung-bei-Zuwendungen-an-politische-"
    "Parteien-und-an-unabhaengige-Waehlervereinigungen/Paragraf-34g/paragraf-34g.html"
)
_HOUSEHOLD_BASIS = "https://www.gesetze-im-internet.de/estg/__35a.html"


def payroll_total(
    trace: CalculationTrace, case: EmployeeCase, key: str, positions: tuple[str, ...]
) -> Decimal:
    sources = []
    amount = ZERO
    for certificate in sorted(case.wage_certificates, key=lambda item: item.document):
        for position in positions:
            if position in certificate.amounts:
                amount += certificate.amounts[position]
                sources.append(f"wage.{certificate.document}.{position}")
    trace.derive(key, amount, "EUR", "payroll.sum_positions", sources)
    return amount


def _total_of(trace: CalculationTrace, key: str, parts: dict[str, Decimal]) -> Decimal:
    amount = sum(parts.values(), ZERO)
    trace.derive(key, amount, "EUR", "amount.sum_components", list(parts))
    return amount


def insurance(trace: CalculationTrace, case: EmployeeCase) -> tuple[dict[str, Decimal], list[dict]]:
    values = {}
    fields = []
    payroll_fields = [
        ("pension_employee", ("23a", "23b"), 4, "300"),
        ("pension_employer", ("22a", "22b"), 9, "304"),
        ("health_payroll", ("25",), 11, "320"),
        ("care_payroll", ("26",), 13, "323"),
        ("employer_statutory_health", ("24a",), 34, "360"),
        ("employer_private", ("24b",), 35, "361"),
        ("employer_statutory_care", ("24c",), 36, "362"),
        ("unemployment_payroll", ("27",), 43, "370"),
    ]
    for key, positions, line, code in payroll_fields:
        values[key] = payroll_total(trace, case, key, positions)
        if trace.entries[key]["inputs"]:
            fields.append(trace.form_field(key, line, code))

    by_category = defaultdict(list)
    for payment in case.insurance_payments:
        by_category[payment.category].append(payment)
    extra_fields = [
        ("professional_pension", 5, "301"),
        ("statutory_pension", 6, "302"),
        ("basic_private_pension", 8, "303"),
        ("statutory_care", 18, "329"),
        ("private_basic_health", 23, "350"),
        ("private_care", 24, "351"),
        ("unemployment", 44, "500"),
        ("disability", 45, "501"),
        ("liability_accident_term_life", 46, "502"),
    ]
    categories = [
        *[key for key, _, _ in extra_fields],
        "statutory_health",
        "statutory_health_no_sick_pay",
        "statutory_health_refund",
        "statutory_health_no_sick_pay_refund",
        "statutory_care_refund",
        "private_basic_health_refund",
        "private_care_refund",
    ]
    for key in categories:
        values[key] = sum_payments(trace, key, by_category[key])
    for key, line, code in extra_fields:
        if by_category[key]:
            fields.append(trace.form_field(key, line, code))

    for key, items, line, code in (
        ("statutory_health_other", ("statutory_health", "statutory_health_no_sick_pay"), 16, "326"),
        (
            "statutory_refunds",
            (
                "statutory_health_refund",
                "statutory_health_no_sick_pay_refund",
                "statutory_care_refund",
            ),
            19,
            "330",
        ),
        ("private_refunds", ("private_basic_health_refund", "private_care_refund"), 25, "352"),
    ):
        values[key] = _total_of(trace, key, {item: values[item] for item in items})
        if any(by_category[item] for item in items):
            fields.append(trace.form_field(key, line, code))
    for key, line, code in (
        ("statutory_health", 17, "328"),
        ("statutory_health_refund", 20, "331"),
    ):
        if by_category[key]:
            fields.append(trace.form_field(key, line, code))
    if (
        case.filing
        and case.filing.insurance == "statutory_without_sick_pay"
        and values["health_payroll"]
    ):
        trace.derive(
            "payroll_health_no_sick_pay",
            values["health_payroll"],
            "EUR",
            "insurance.payroll_without_sick_pay",
            ["health_payroll", "filing.insurance"],
        )
        fields.append(trace.form_field("payroll_health_no_sick_pay", 12, "322"))
    return values, fields


def insurance_deduction(
    trace: CalculationTrace, case: EmployeeCase, amounts: dict[str, Decimal]
) -> tuple[Decimal, Decimal]:
    assert case.filing is not None
    trace.rule("rule.insurance.pension_ceiling", Decimal("29344"), "EUR", _PENSION_BASIS)
    trace.rule("rule.insurance.employee_other_ceiling", Decimal("1900"), "EUR", _PENSION_BASIS)
    trace.rule("rule.insurance.sick_pay_reduction", Decimal("0.04"), "fraction", _SPECIAL_BASIS)
    retirement = (
        "pension_employee",
        "pension_employer",
        "statutory_pension",
        "professional_pension",
        "basic_private_pension",
    )
    pension = max(
        ZERO,
        min(Decimal(29344), sum((amounts[k] for k in retirement), ZERO))
        - amounts["pension_employer"],
    )
    trace.derive(
        "deductible_pension",
        pension,
        "EUR",
        "insurance.pension_cap_less_employer",
        [*retirement, "rule.insurance.pension_ceiling"],
    )

    sick_pay_cost = amounts["statutory_health"] - amounts["statutory_health_refund"]
    if case.filing.insurance == "statutory_with_sick_pay":
        sick_pay_cost += amounts["health_payroll"]
    health_inputs = [
        "health_payroll",
        "statutory_health_other",
        "care_payroll",
        "statutory_care",
        "private_basic_health",
        "private_care",
    ]
    refunds = [
        "statutory_refunds",
        "private_refunds",
        "employer_statutory_health",
        "employer_statutory_care",
        "employer_private",
    ]
    basic = cents(
        sum((amounts[k] for k in health_inputs), ZERO)
        - sum((amounts[k] for k in refunds), ZERO)
        - sick_pay_cost * Decimal("0.04")
    )
    trace.derive(
        "net_basic_insurance",
        basic,
        "EUR",
        "insurance.net_of_refunds_subsidies_and_sick_pay_reduction",
        [
            *health_inputs,
            *refunds,
            "statutory_health",
            "statutory_health_refund",
            "filing.insurance",
            "rule.insurance.sick_pay_reduction",
        ],
    )
    overhang = max(ZERO, -basic)
    trace.derive(
        "insurance_refund_overhang",
        overhang,
        "EUR",
        "insurance.excess_refunds",
        ["net_basic_insurance"],
    )
    other_keys = [
        "unemployment_payroll",
        "unemployment",
        "disability",
        "liability_accident_term_life",
    ]
    other = sum((amounts[item] for item in other_keys), ZERO)
    health = max(ZERO, basic)
    other_deductible = min(other, max(ZERO, Decimal(1900) - health))
    trace.derive(
        "deductible_other_insurance",
        other_deductible,
        "EUR",
        "insurance.remaining_allowance",
        ["net_basic_insurance", *other_keys, "rule.insurance.employee_other_ceiling"],
    )
    deduction = pension + health + other_deductible
    trace.derive(
        "insurance_deduction",
        deduction,
        "EUR",
        "insurance.total_deduction",
        ["deductible_pension", "net_basic_insurance", "deductible_other_insurance"],
    )
    return deduction, overhang


def special_expenses(
    trace: CalculationTrace, case: EmployeeCase, income: Decimal, initial_training: Decimal
) -> tuple[dict[str, Decimal], dict[str, list[dict]]]:
    withholding = payroll_total(trace, case, "church_tax_withheld", ("6",))
    paid = sum_payments(
        trace,
        "church_tax_other_paid",
        (p for p in case.church_tax_payments if p.category == "paid"),
    )
    prepayments = sum_payments(
        trace,
        "church_tax_prepayments",
        (p for p in case.church_tax_payments if p.category == "prepayment"),
    )
    refunded = sum_payments(
        trace,
        "church_tax_refunded",
        (p for p in case.church_tax_payments if p.category == "refunded"),
    )
    paid_total = _total_of(
        trace,
        "church_tax_paid_total",
        {
            "church_tax_withheld": withholding,
            "church_tax_other_paid": paid,
            "church_tax_prepayments": prepayments,
        },
    )
    church_net = paid_total - refunded
    trace.derive(
        "net_church_tax_paid",
        church_net,
        "EUR",
        "special.church_tax_net",
        ["church_tax_paid_total", "church_tax_refunded"],
    )
    fields = [
        trace.form_field(key, 4)
        for key in ("church_tax_paid_total", "church_tax_refunded")
        if trace.entries[key]["value"] != "0.00"
    ]
    if initial_training:
        fields.append(trace.form_field("initial_training", 13))

    amounts = {}
    for key, line in [
        ("charitable_domestic", 5),
        ("charitable_eu_eea", 6),
        ("political_party", 7),
        ("voters_group", 8),
    ]:
        payments = [item for item in case.donations if item.category == key]
        amounts[key] = sum_payments(trace, key, payments)
        if payments:
            fields.append(trace.form_field(key, line))
    carry = ZERO
    carry_inputs = []
    other_form = []
    if case.donation_carryforward:
        carry = record_payment(trace, "prior_donation_carryforward", case.donation_carryforward)
        carry_inputs.append("prior_donation_carryforward")
        trace.derive(
            "prior_donation_carryforward_exists",
            int(carry > 0),
            "boolean",
            "donation.has_prior_carryforward",
            carry_inputs,
        )
        if carry:
            other_form.append(trace.form_field("prior_donation_carryforward_exists", 16))
    limit = Decimal("0.20")
    trace.rule("rule.donation.income_share", limit, "fraction", _DONATION_BASIS)
    eligible = _total_of(
        trace,
        "eligible_charitable_donations",
        {
            "charitable_domestic": amounts["charitable_domestic"],
            "charitable_eu_eea": amounts["charitable_eu_eea"],
            **dict.fromkeys(carry_inputs, carry),
        },
    )
    deduction = min(eligible, cents(max(ZERO, income) * limit))
    trace.derive(
        "charitable_donation_deduction",
        deduction,
        "EUR",
        "donation.annual_income_limit",
        ["eligible_charitable_donations", "employment_income", "rule.donation.income_share"],
    )
    trace.derive(
        "remaining_charitable_donations",
        eligible - deduction,
        "EUR",
        "donation.remaining_for_carryforward",
        ["eligible_charitable_donations", "charitable_donation_deduction"],
    )

    political_rate, political_cap = Decimal("0.50"), Decimal(825)
    trace.rule("rule.donation.political_rate", political_rate, "fraction", _POLITICAL_BASIS)
    trace.rule("rule.donation.political_credit_cap", political_cap, "EUR", _POLITICAL_BASIS)
    credit = sum(
        (
            min(political_cap, cents(amounts[key] * political_rate))
            for key in ("political_party", "voters_group")
        ),
        ZERO,
    )
    trace.derive(
        "political_donation_credit",
        credit,
        "EUR",
        "donation.political_reduction_per_group",
        [
            "political_party",
            "voters_group",
            "rule.donation.political_rate",
            "rule.donation.political_credit_cap",
        ],
    )
    trace.rule(
        "rule.donation.party_additional_deduction_cap", Decimal(1650), "EUR", _DONATION_BASIS
    )
    party_deduction = min(Decimal(1650), max(ZERO, amounts["political_party"] - Decimal(1650)))
    trace.derive(
        "political_party_special_deduction",
        party_deduction,
        "EUR",
        "donation.party_amount_above_credit_threshold",
        [
            "political_party",
            "rule.donation.party_additional_deduction_cap",
            "rule.donation.political_credit_cap",
            "rule.donation.political_rate",
        ],
    )

    trace.rule("rule.special.initial_training_ceiling", Decimal(6000), "EUR", _SPECIAL_BASIS)
    education = min(Decimal(6000), initial_training)
    trace.derive(
        "initial_training_deduction",
        education,
        "EUR",
        "special.education_cap",
        ["initial_training", "rule.special.initial_training_ceiling"],
    )
    trace.rule("rule.special.allowance", Decimal(36), "EUR", HELP_2025)
    special = max(Decimal(36), max(ZERO, church_net) + deduction + party_deduction + education)
    trace.derive(
        "special_expense_deduction",
        special,
        "EUR",
        "special.compare_actual_and_allowance",
        [
            "net_church_tax_paid",
            "charitable_donation_deduction",
            "political_party_special_deduction",
            "initial_training_deduction",
            "rule.special.allowance",
        ],
    )
    overhang = max(ZERO, -church_net)
    trace.derive(
        "church_tax_refund_overhang",
        overhang,
        "EUR",
        "special.excess_church_tax_refunds",
        ["net_church_tax_paid"],
    )
    return {"special": special, "church_refund_overhang": overhang, "political_credit": credit}, {
        "Anlage Sonderausgaben": fields,
        "Anlage Sonstiges": other_form,
    }


def household(
    trace: CalculationTrace, case: EmployeeCase
) -> tuple[Decimal, list[dict], list[dict]]:
    caps = {"minijob": Decimal(510), "service": Decimal(4000), "craft": Decimal(1200)}
    trace.rule("rule.household.rate", Decimal("0.20"), "fraction", _HOUSEHOLD_BASIS)
    for kind, cap in caps.items():
        trace.rule(f"rule.household.{kind}_cap", cap, "EUR", _HOUSEHOLD_BASIS)
    share = Decimal(100)
    share_inputs = []
    if case.filing:
        share = case.filing.household_limit_percent
        trace.fact("household_limit_share", share, "%", (case.filing.case_facts,))
        share_inputs.append("household_limit_share")
    fields = []
    findings = []
    costs = defaultdict(dict)
    craft_invoices = {}
    for i, item in enumerate(sorted(case.household_costs, key=source_order), start=1):
        key = f"household.{i}"
        record_payment(
            trace,
            f"{key}.eligible_cost",
            item,
            details={"description": item.description, "category": item.category},
        )
        record_payment(trace, f"{key}.invoice_total", item.invoice_total)
        trace.fact(
            f"{key}.payment",
            item.paid_on,
            "date",
            (item.payment_source,),
            details={
                "method": item.payment_method,
                "household_in_eu_eea": item.household_in_eu_eea,
                "publicly_funded": item.publicly_funded,
            },
        )
        amount = item.amount
        invoice = item.invoice_total.amount
        inputs = [f"{key}.eligible_cost", f"{key}.invoice_total", f"{key}.payment"]
        if item.reimbursement:
            reimbursement = record_payment(trace, f"{key}.reimbursement", item.reimbursement)
            amount -= reimbursement
            invoice -= reimbursement
            inputs.append(f"{key}.reimbursement")
        eligible = (
            item.household_in_eu_eea
            and (
                item.payment_method
                == ("minijob_proof" if item.category == "minijob" else "account")
            )
            and not (item.category == "craft" and item.publicly_funded)
        )
        trace.derive(
            key,
            amount if eligible else ZERO,
            "EUR",
            "household.eligible_cost_after_reimbursement",
            inputs,
        )
        if eligible:
            costs[item.category][key] = amount
            if item.category == "craft":
                trace.derive(f"{key}.invoice_net", invoice, "EUR", "household.invoice_net", inputs)
                craft_invoices[f"{key}.invoice_net"] = invoice
        else:
            findings.append(
                {
                    "code": "household_not_eligible",
                    "trace": key,
                    "message": "§ 35a: Zahlungsnachweis, Lage des Haushalts oder Förderung schließt diesen Ansatz aus.",
                }
            )

    reductions = {}
    for kind, line in (("minijob", 4), ("service", 5), ("craft", 6)):
        cost_key = f"household_{kind}_costs"
        amount = _total_of(trace, cost_key, costs[kind])
        if costs[kind]:
            if kind == "craft":
                invoice = _total_of(trace, "household_craft_invoice_net", craft_invoices)
                if invoice:
                    fields.append(trace.form_field("household_craft_invoice_net", line))
            fields.append(trace.form_field(cost_key, line))
        reduction_key = f"household_{kind}_credit"
        reductions[reduction_key] = cents(
            min(caps[kind] * share / HUNDRED, amount * Decimal("0.20"))
        )
        trace.derive(
            reduction_key,
            reductions[reduction_key],
            "EUR",
            "household.apply_separate_cap",
            [cost_key, f"rule.household.{kind}_cap", "rule.household.rate", *share_inputs],
        )
    return _total_of(trace, "household_total_credit", reductions), fields, findings
