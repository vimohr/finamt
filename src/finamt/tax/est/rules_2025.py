"""2025 employee tax rules and numeric references for the Anlage N preview."""

from __future__ import annotations

from decimal import Context, Decimal, localcontext

from .assessment_2025 import estimate, main_form, total_income_2025
from .deductions_2025 import household, insurance, special_expenses
from .expenses_2025 import expense_totals, travel_totals
from .intake_2025 import check_intake
from .models import EmployeeCase, WageCertificate
from .provenance import CalculationTrace

_DISTANCE_BASIS = (
    "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "II-Einkommen-2-24b/4-Ueberschuss-der-Einnahmen-ueber-die-Wk-8-9a/Paragraf-9/inhalt.html"
)
_EMPLOYEE_ALLOWANCE_BASIS = (
    "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/"
    "II-Einkommen-2-24b/4-Ueberschuss-der-Einnahmen-ueber-die-Wk-8-9a/Paragraf-9a/inhalt.html"
)
_HOME_OFFICE_BASIS = (
    "https://ao.bundesfinanzministerium.de/lsth/2025/B-Anhaenge/Anhang-19/I/anhang-19-I.html"
)
_PAYROLL_FORM = (
    "https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/"
    "Steuerarten/Lohnsteuer/2025-02-20-geaen-ausdruck-elektron-LSt-besch-2025.html"
)
_ANLAGE_N_HELP = "https://www.elster.de/elsterweb/helpGlobal?themaGlobal=help_est_ufa_10_2025"
_ANLAGE_N_FORM = "https://www.formulare-bfinv.de/ffw/action/invoke.do?id=034027_25"

_FIRST_DISTANCE_BAND_KM = 20
_FIRST_DISTANCE_RATE = Decimal("0.30")
_NEXT_DISTANCE_RATE = Decimal("0.38")
_DISTANCE_CAP = Decimal("4500.00")
_HOME_OFFICE_RATE = Decimal("6.00")
_HOME_OFFICE_CAP = Decimal("1260.00")
_EMPLOYEE_ALLOWANCE = Decimal("1230.00")
_ZERO = Decimal("0.00")

# Lohnsteuerbescheinigung Nr. -> Anlage N field, line and class-specific Kennzahl.
_PAYROLL_FIELDS = {
    "3": ("gross_wages", 5, "110", "111"),
    "4": ("wage_tax", 6, "140", "141"),
    "5": ("solidarity_surcharge", 7, "150", "151"),
    "6": ("church_tax", 8, "142", "143"),
}
_REIMBURSEMENT_FIELDS = {
    "17": ("tax_free_commute_reimbursements", "290"),
    "18": ("flat_rate_taxed_commute_reimbursements", "295"),
}


def _form_field(trace: CalculationTrace, key: str, line: int, code: str | None = None) -> dict:
    return trace.form_field(key, line, code)


def _record_payroll(
    trace: CalculationTrace, certificates: tuple[WageCertificate, ...]
) -> tuple[list[dict], Decimal, Decimal]:
    for certificate in certificates:
        prefix = f"wage.{certificate.document}"
        trace.fact(
            f"{prefix}.period_end",
            certificate.period_end,
            "date",
            (certificate.locate("Nr. 1 · Bescheinigungszeitraum (bis)"),),
        )
        trace.fact(
            f"{prefix}.tax_class",
            certificate.tax_class,
            "tax_class",
            (certificate.locate("Steuerklasse/Faktor"),),
        )
        for position, amount in sorted(certificate.amounts.items()):
            trace.fact(
                f"{prefix}.{position}", amount, "EUR", (certificate.locate(f"Nr. {position}"),)
            )

    fields = []
    gross = _ZERO
    gross_keys = []
    for class_six, group_name in [(False, "classes_1_to_5"), (True, "class_6")]:
        group = [item for item in certificates if (item.tax_class == 6) == class_six]
        for position, (key, line, code_1_to_5, code_6) in _PAYROLL_FIELDS.items():
            entries = [item for item in group if position in item.amounts]
            if not entries:
                continue
            amount = sum((item.amounts[position] for item in entries), _ZERO)
            result_key = f"{key}_{group_name}"
            inputs = [
                f"wage.{item.document}.{field}"
                for item in entries
                for field in (position, "tax_class")
            ]
            trace.derive(result_key, amount, "EUR", f"payroll.sum_{group_name}", inputs)
            fields.append(
                _form_field(trace, result_key, line, code_6 if class_six else code_1_to_5)
            )
            if position == "3":
                gross += amount
                gross_keys.append(result_key)
    trace.derive("gross_wages", gross, "EUR", "payroll.total_gross", gross_keys)

    reimbursements = _ZERO
    reimbursement_keys = []
    for position, (key, code) in _REIMBURSEMENT_FIELDS.items():
        entries = [item for item in certificates if position in item.amounts]
        if entries:
            amount = sum((item.amounts[position] for item in entries), _ZERO)
            trace.derive(
                key,
                amount,
                "EUR",
                "payroll.sum_commute_reimbursements",
                [f"wage.{item.document}.{position}" for item in entries],
            )
            fields.append(_form_field(trace, key, 51, code))
            reimbursements += amount
            reimbursement_keys.append(key)
    trace.derive(
        "commute_reimbursements",
        reimbursements,
        "EUR",
        "commute.total_reimbursements",
        reimbursement_keys,
    )
    return fields, gross, reimbursements


def _record_workdays(
    trace: CalculationTrace, case: EmployeeCase
) -> tuple[list[str], list[str], list[str]]:
    commute_days = []
    regular_home_days = []
    special_home_days = []
    for workday in sorted(case.workdays, key=lambda item: item.day):
        key = f"workday.{workday.day.isoformat()}"
        trace.fact(
            key,
            workday.day,
            "date",
            workday.sources,
            details={
                "attended_first_workplace": workday.attended_first_workplace,
                "home_work": workday.home_work,
                "permanently_without_other_workplace": workday.permanently_without_other_workplace,
            },
        )
        if workday.attended_first_workplace:
            commute_days.append(key)
        if workday.home_work == "none":
            continue
        if workday.permanently_without_other_workplace:
            special_home_days.append(key)
        elif workday.home_work == "predominantly" and not workday.attended_first_workplace:
            regular_home_days.append(key)
    return commute_days, regular_home_days, special_home_days


def _calculate_commute(
    trace: CalculationTrace, case: EmployeeCase, days: list[str], reimbursements: Decimal
) -> tuple[Decimal, list[dict]]:
    commute = case.commute
    if commute is None:
        trace.derive("commute_deduction", _ZERO, "EUR", "commute.no_claim", [])
        return _ZERO, []

    trace.rule("rule.commute.band_km", _FIRST_DISTANCE_BAND_KM, "km", _DISTANCE_BASIS)
    trace.rule("rule.commute.first_rate", _FIRST_DISTANCE_RATE, "EUR/km", _DISTANCE_BASIS)
    trace.rule("rule.commute.next_rate", _NEXT_DISTANCE_RATE, "EUR/km", _DISTANCE_BASIS)
    trace.rule("rule.commute.cap", _DISTANCE_CAP, "EUR", _DISTANCE_BASIS)
    trace.fact(
        "commute_route_distance",
        commute.distance_km,
        "km",
        (commute.source,),
        details={"mode": commute.mode},
    )
    full_km = int(commute.distance_km)
    trace.derive(
        "commute_distance_km", full_km, "km", "commute.full_km", ["commute_route_distance"]
    )
    trace.derive("commute_days", len(days), "days", "commute.count_workplace_visits", days)
    fields = [
        _form_field(trace, "commute_days", 29, "110"),
        _form_field(trace, "commute_distance_km", 30, "111"),
    ]
    own_car = commute.mode == "own_or_provided_car"
    mode_key = "commute_car_km" if own_car else "commute_other_km"
    trace.derive(mode_key, full_km, "km", "commute.distance_by_mode", ["commute_distance_km"])
    fields.append(
        _form_field(trace, mode_key, 31, "112") if own_car else _form_field(trace, mode_key, 33)
    )

    daily = (
        min(full_km, _FIRST_DISTANCE_BAND_KM) * _FIRST_DISTANCE_RATE
        + max(0, full_km - _FIRST_DISTANCE_BAND_KM) * _NEXT_DISTANCE_RATE
    )
    trace.derive(
        "commute_per_day",
        daily,
        "EUR",
        "commute.tiered_rate",
        [
            "commute_distance_km",
            "rule.commute.band_km",
            "rule.commute.first_rate",
            "rule.commute.next_rate",
        ],
    )
    allowance = daily * len(days)
    allowance_inputs = ["commute_per_day", "commute_days", mode_key]
    if not own_car:
        allowance = min(allowance, _DISTANCE_CAP)
        allowance_inputs.append("rule.commute.cap")
    trace.derive(
        "commute_allowance",
        allowance,
        "EUR",
        "commute.annual_allowance_by_mode",
        allowance_inputs,
    )
    result_inputs = ["commute_allowance", "commute_reimbursements"]
    transport_costs = _ZERO
    if commute.public_transport_costs:
        costs = sorted(
            commute.public_transport_costs,
            key=lambda item: (item.source.document, item.source.page or 0, item.source.locator),
        )
        cost_keys = []
        for index, cost in enumerate(costs, start=1):
            key = f"commute.ticket.{index}"
            trace.fact(key, cost.amount, "EUR", (cost.source,))
            transport_costs += cost.amount
            cost_keys.append(key)
        trace.derive(
            "commute_ticket_costs", transport_costs, "EUR", "commute.sum_tickets", cost_keys
        )
        fields.append(_form_field(trace, "commute_ticket_costs", 34, "114"))
        result_inputs.append("commute_ticket_costs")
    deduction = max(_ZERO, max(allowance, transport_costs) - reimbursements)
    trace.derive(
        "commute_deduction", deduction, "EUR", "commute.choose_and_subtract", result_inputs
    )
    return deduction, fields


def _calculate_home_office(
    trace: CalculationTrace, regular_days: list[str], special_days: list[str]
) -> tuple[Decimal, list[dict]]:
    trace.rule("rule.home_office.rate", _HOME_OFFICE_RATE, "EUR/day", _HOME_OFFICE_BASIS)
    trace.rule("rule.home_office.cap", _HOME_OFFICE_CAP, "EUR", _HOME_OFFICE_BASIS)
    fields = []
    inputs = ["rule.home_office.rate", "rule.home_office.cap"]
    for key, days, line, code in [
        ("home_office_regular_days", regular_days, 58, "335"),
        ("home_office_no_other_workplace_days", special_days, 59, "336"),
    ]:
        if days:
            trace.derive(key, len(days), "days", f"home_office.count_{line}", days)
            fields.append(_form_field(trace, key, line, code))
            inputs.append(key)
    deduction = min((len(regular_days) + len(special_days)) * _HOME_OFFICE_RATE, _HOME_OFFICE_CAP)
    trace.derive("home_office_deduction", deduction, "EUR", "home_office.capped_total", inputs)
    return deduction, fields


def draft_2025(case: EmployeeCase, trace: CalculationTrace, source_findings: list[dict]) -> dict:
    # Use an explicit decimal context so a caller's global context cannot alter deductions.
    with localcontext(Context(prec=28)):
        certificates = tuple(sorted(case.wage_certificates, key=lambda item: item.document))
        payroll_fields, gross, reimbursements = _record_payroll(trace, certificates)
        commute_days, regular_home_days, special_home_days = _record_workdays(trace, case)
        commute_amount, commute_fields = _calculate_commute(
            trace, case, commute_days, reimbursements
        )
        home_amount, home_fields = _calculate_home_office(
            trace, regular_home_days, special_home_days
        )
        claims, expense_fields = expense_totals(trace, case)
        travel, travel_fields = travel_totals(trace, case)
        claim_keys = ["work_equipment", "professional_association", "training", "other_work"]
        expenses = (
            commute_amount + home_amount + travel + sum((claims[key] for key in claim_keys), _ZERO)
        )
        trace.derive(
            "supported_expenses",
            expenses,
            "EUR",
            "employment.sum_supported_expenses",
            ["commute_deduction", "home_office_deduction", *claim_keys, "travel_deduction"],
        )
        trace.rule("rule.employee_allowance", _EMPLOYEE_ALLOWANCE, "EUR", _EMPLOYEE_ALLOWANCE_BASIS)
        deduction = max(expenses, min(gross, _EMPLOYEE_ALLOWANCE))
        trace.derive(
            "employment_deduction",
            deduction,
            "EUR",
            "employment.compare_actual_to_allowance_limited_to_gross",
            ["supported_expenses", "gross_wages", "rule.employee_allowance"],
        )
        income = gross - deduction
        trace.derive(
            "employment_income",
            income,
            "EUR",
            "employment.subtract_deduction",
            ["gross_wages", "employment_deduction"],
        )
        main_fields = main_form(trace, case.filing) if case.filing else []
        total_income = total_income_2025(trace, case, gross, income)
        insurance_values, insurance_fields = insurance(trace, case)
        special, special_forms = special_expenses(
            trace, case, total_income, claims["initial_training"]
        )
        household_credit, household_fields, findings = household(trace, case)
        findings.extend(source_findings)
        intake = check_intake(case.intake, wage_count=len(certificates))
        if case.intake or case.filing:
            findings.extend(intake["findings"])
        for certificate in certificates:
            if certificate.unsupported_positions:
                findings.append(
                    {
                        "code": "unsupported_payroll",
                        "severity": "blocker",
                        "trace": f"wage.{certificate.document}.3",
                        "message": "Diese Lohnsteuerbescheinigung enthält weitere Sachverhalte. Der Originalbeleg bleibt im Fall verfügbar.",
                    }
                )
        if case.filing and any(certificate.tax_class == 2 for certificate in certificates):
            findings.append(
                {
                    "code": "payroll_class_2",
                    "severity": "blocker",
                    "question": "children",
                    "message": "Steuerklasse II im Lohnbeleg. Kläre die Voraussetzungen für den Entlastungsbetrag für Alleinerziehende.",
                }
            )
        assessment = (
            estimate(trace, case, total_income, insurance_values, special, household_credit)
            if case.filing and all(finding.get("severity") != "blocker" for finding in findings)
            else None
        )
        if not case.filing:
            findings.append(
                {
                    "code": "no_assessment_profile",
                    "message": "Für eine Jahresschätzung fehlen die bestätigten Angaben im Hauptvordruck.",
                }
            )
        anlage_n = sorted(
            payroll_fields + commute_fields + home_fields + expense_fields + travel_fields,
            key=lambda item: item["line"],
        )
        forms = {
            "ESt 1 A": main_fields,
            "Anlage N": anlage_n,
            "Anlage Vorsorgeaufwand": insurance_fields,
            **special_forms,
            "Anlage Haushaltsnahe Aufwendungen": household_fields,
        }

    return {
        "status": "draft",
        "form": "Anlage N",
        "tax_year": 2025,
        "rules_version": "2025.3",
        "form_mapping_version": "est-forms-2025.2",
        "references": {
            "wage_certificate": _PAYROLL_FORM,
            "anlage_n_help": _ANLAGE_N_HELP,
            "anlage_n_form": _ANLAGE_N_FORM,
        },
        "documents": trace.documents,
        "fields": anlage_n,
        "forms": {
            name: sorted(fields, key=lambda field: field["line"])
            for name, fields in forms.items()
            if fields
        },
        "summary": {
            key: trace.result(key)
            for key in (
                "gross_wages",
                "commute_deduction",
                "home_office_deduction",
                "work_equipment",
                "training",
                "professional_association",
                "other_work",
                "travel_deduction",
                "supported_expenses",
                "employment_deduction",
                "employment_income",
            )
        },
        "assessment": assessment,
        "intake": intake,
        "findings": findings,
        "submission_status": "preview",
        "trace": trace.entries,
    }
