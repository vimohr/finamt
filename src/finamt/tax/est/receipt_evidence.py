"""Explicit payment evidence for reviewable document proposals."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .extraction import receipt_amounts

PaymentSources = dict[date, list[str]]

_DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b")
_PAID = re.compile(
    r"\b(?:bezahlt|gezahlt|beglichen|abgebucht|eingezogen|gutgeschrieben|[uü]berwiesen|"
    r"erstattet|ausgezahlt|auszahlungsdatum|zahlungsdatum|buchungstag|geldeingang|"
    r"zahlungseingang|bar erhalten|eingang der spende|"
    r"(?:zahlung|spende|beitrag|betrag|zuwendung)\b.{0,100}\b(?:erhalten|eingegangen|verbucht)|"
    r"(?:lastschrift|[uü]berweisung)\b.{0,100}\bausgef[uü]hrt)\b",
    re.IGNORECASE,
)
_NOT_PAID = re.compile(
    r"\b(?:nicht|kein(?:e[nrsm]?)?|unbezahlt|unbeglichen|offen|fällig(?:keit)?|zahlbar|"
    r"rechnungsdatum|(?:voraussichtlich|geplant|erwartet)(?:e[nrsm]?)?|"
    r"soll(?:en|te[n]?)?|wird|werden|zu überweisen)\b",
    re.IGNORECASE,
)
_NO_PURPOSE = re.compile(
    r"\bVerwendungszweck\s*:?\s*(?:nicht (?:angegeben|ersichtlich)|fehlt|unbekannt)\b",
    re.IGNORECASE,
)
_NO_AMOUNT = re.compile(
    r"\b(?:Betrag|Gebühr)\b[^.!?\n]{0,90}\bnicht (?:lesbar|erkennbar|angegeben)\b",
    re.IGNORECASE,
)
_INSURANCE_TYPES = re.compile(
    r"\b(?:\w+versicherung|basisabsicherung|versorgungswerk|rürup|riester)\b", re.IGNORECASE
)
_REFUND = re.compile(
    r"\b(?:Beitragserstattung|Rückerstattung|Erstattung|erstattet)\b", re.IGNORECASE
)
_INSURANCE_RECEIPTS = {
    "haftpflichtversicherung": (
        re.compile(r"\bprivate[nr]?\s+Haftpflichtversicherung\b", re.IGNORECASE),
        "liability_accident_term_life",
    ),
    "berufsunfähigkeitsversicherung": (
        re.compile(r"\bprivate[nr]?\s+Berufsunfähigkeitsversicherung\b", re.IGNORECASE),
        "disability",
    ),
    "pflegeversicherung": (
        re.compile(r"\bgesetzliche[nr]?\s+Pflegeversicherung\b", re.IGNORECASE),
        "statutory_care_refund",
    ),
}
_INSURANCE_AMOUNT = re.compile(
    r"\b(?:Versicherungsbeitrag|Einzelbeitrag|Jahresbeitrag|Beitragserstattung)\b", re.IGNORECASE
)
_EURO = re.compile(r"(?:\b(?:EUR|Euro)\b|€)", re.IGNORECASE)


def printed_date(token: str) -> date | None:
    if not _DATE.fullmatch(token):
        return None
    try:
        if "." in token:
            day, month, year = map(int, token.split("."))
            return date(year, month, day)
        return date.fromisoformat(token)
    except ValueError:
        return None


def payment_sources(excerpt: str) -> PaymentSources:
    """Find dates named in an affirmative statement of payment or reimbursement."""
    evidence: PaymentSources = {}
    for line in excerpt.splitlines():
        for statement in re.split(r"(?<=[.!?])\s+", " ".join(line.split())):
            dates = _DATE.findall(statement)
            if len(dates) != 1 or not _PAID.search(statement) or _NOT_PAID.search(statement):
                continue
            if paid_on := printed_date(dates[0]):
                evidence.setdefault(paid_on, []).append(statement)
    return evidence


def amount_payment_source(
    payments: PaymentSources, paid_on: date, amount: Decimal, quote: str
) -> str | None:
    statements = payments.get(paid_on)
    if not statements:
        return None
    amounts = {statement: set(receipt_amounts(statement)) for statement in statements}
    expected = {amount}
    if len(payments) > 1:
        cited = [line for lines in payments.values() for line in lines if line in quote]
        if len(cited) == 1 and amounts.get(cited[0]) == expected:
            return cited[0]
        return None
    paired = next((line for line, values in amounts.items() if values == expected), None)
    if paired or any(amounts.values()):
        return paired
    return statements[0]


def receipt_question(excerpt: str, payments: PaymentSources, year: int) -> str | None:
    if _NO_PURPOSE.search(excerpt):
        return "Hast du einen Beleg, aus dem der Zweck der Überweisung hervorgeht?"
    if _NO_AMOUNT.search(excerpt) or next(receipt_amounts(excerpt), None) is None:
        return "An welcher Stelle steht der tatsächlich gezahlte oder erstattete Betrag?"
    if not any(day.year == year for day in payments):
        return f"Hast du einen Beleg mit dem tatsächlichen Datum der Zahlung oder Erstattung in {year}?"
    return None


def clear_insurance_receipt(
    excerpt: str, payments: PaymentSources
) -> tuple[str, Decimal, str] | None:
    """Recognize an explicitly labeled, single insurance payment from its original."""
    insurance_types = {match.casefold() for match in _INSURANCE_TYPES.findall(excerpt)}
    if len(insurance_types) != 1 or len(payments) != 1 or len(next(iter(payments.values()))) != 1:
        return None
    rule = _INSURANCE_RECEIPTS.get(next(iter(insurance_types)))
    if rule is None:
        return None
    label, category = rule
    lines = [" ".join(line.split()) for line in excerpt.splitlines()]
    heading = next(
        (line for line in lines if label.search(line) and not _NOT_PAID.search(line)), None
    )
    refund = category == "statutory_care_refund"
    if heading is None or refund != bool(_REFUND.search(excerpt)):
        return None
    amounts = list(receipt_amounts(excerpt))
    if len(amounts) != 1:
        return None
    for line in lines:
        if (
            _INSURANCE_AMOUNT.search(line)
            and _EURO.search(line)
            and amounts[0] in receipt_amounts(line)
            and not _NOT_PAID.search(line)
            and refund == bool(_REFUND.search(line))
        ):
            return category, amounts[0], " · ".join(dict.fromkeys([heading, line]))
    return None
