"""Match explicitly referenced training receipts for the 2025 employee case."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal

import fitz
from pydantic import ValidationError

from .extraction import receipt_amounts
from .models import Expense, SourceDocument, SourceLocation
from .receipt_evidence import amount_payment_source, payment_sources

Kind = Literal["invoice", "payment", "refund"]
_AMOUNT_FIELDS: dict[Kind, tuple[str, ...]] = {
    "invoice": ("rechnungsbetrag", "rechnungssumme", "bruttobetrag", "gesamtbetrag"),
    "payment": ("überwiesener betrag", "gezahlter betrag", "abgebuchter betrag"),
    "refund": ("erstattungsbetrag", "erstatteter betrag", "ausgezahlter betrag"),
}
_REFERENCE_FIELDS = ("rechnungsnummer", "rechnungsnr.", "rechnungs-nr.")
_ISSUER_FIELDS = ("rechnungssteller", "anbieter")
_PAYEE_FIELDS = ("empfänger", "zahlungsempfänger")
_SUBJECT_FIELDS = ("leistung", "beschreibung")
_DATE_FIELDS = ("zahlungsdatum", "buchungstag", "auszahlungsdatum")
_FIELDS = {
    *_REFERENCE_FIELDS,
    *_ISSUER_FIELDS,
    *_PAYEE_FIELDS,
    *_SUBJECT_FIELDS,
    *_DATE_FIELDS,
    "verwendungszweck",
    *(name for fields in _AMOUNT_FIELDS.values() for name in fields),
}
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,63}")
_PURPOSE_REFERENCE = re.compile(
    rf"Rechnung(?:snummer|s-?Nr\.?)?(?:\s*:\s*|\s+)({_REFERENCE.pattern})", re.IGNORECASE
)
_EURO = re.compile(
    r"(?:(?:EUR|€)\s*(?:\d{1,3}(?:[. ]\d{3})+|\d+)[,.]\d{2}|"
    r"(?:\d{1,3}(?:[. ]\d{3})+|\d+)[,.]\d{2}\s*(?:EUR|Euro|€))",
    re.IGNORECASE,
)
_TRAINING = re.compile(r"^(?:berufliche Fortbildung|Fachseminar)\b", re.IGNORECASE)
_PENDING = re.compile(
    r"\b(?:terminüberweisung|unbezahlt|zahlung ausstehend|nicht (?:ausgeführt|überwiesen)|"
    r"(?:geplant|voraussichtlich)(?:e[nrsm]?)?)\b",
    re.IGNORECASE,
)
_BANK_STATEMENT = re.compile(r"^[ \t]*Kontoauszug\b", re.IGNORECASE | re.MULTILINE)
_BOOKING = re.compile(
    r"^[ \t]*Buchung[ \t]+(?:Nr\.?[ \t]*)?[0-9]+[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Receipt:
    references: tuple[str, ...]
    issuer: str | None
    kind: Kind | None
    description: str | None
    amount: Decimal | None
    paid_on: date | None
    source: SourceLocation


def _read_pages(data: bytes, filename: str) -> list[tuple[int | None, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or data.startswith(b"%PDF-"):
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise ValueError("Wähle eine entsperrte PDF-Datei.")
                return [(page.number + 1, page.get_text(sort=True)) for page in pdf]
        except (fitz.FileDataError, fitz.EmptyFileError) as exc:
            raise ValueError("Die PDF-Datei ist nicht lesbar.") from exc
    if suffix == ".txt":
        return [(None, data.decode("utf-8-sig", errors="replace"))]
    return []


def _fields(text: str) -> dict[str, list[tuple[str, str]]]:
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    values: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for i, line in enumerate(lines):
        label, _, value = line.partition(":")
        key = label.strip().casefold()
        if key in _FIELDS:
            if value.strip():
                values[key].append((value.strip(), line))
            elif i + 1 < len(lines) and lines[i + 1].partition(":")[0].casefold() not in _FIELDS:
                values[key].append((lines[i + 1], f"{line} {lines[i + 1]}"))
    return values


def _one_field(fields: dict[str, list[tuple[str, str]]], names: tuple[str, ...]) -> tuple[str, str]:
    options = {value: quote for name in names for value, quote in fields.get(name, ())}
    return next(iter(options.items())) if len(options) == 1 else ("", "")


def _statement_bookings(text: str) -> Iterator[tuple[str | None, str]]:
    headings = list(_BOOKING.finditer(text))
    if not headings:
        yield None, text
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        yield heading[0].strip(), text[heading.end() : end]


def _receipt(
    document: str, page: int | None, text: str, booking: str | None = None
) -> Receipt | None:
    fields = _fields(text)
    amounts = [
        (kind, value, quote)
        for kind, names in _AMOUNT_FIELDS.items()
        for name in names
        for value, quote in fields.get(name, ())
    ]
    subject, subject_quote = _one_field(fields, _SUBJECT_FIELDS)
    description = subject if _TRAINING.search(subject) else None
    if not amounts and not description:
        return None

    kind, euro, amount_quote = amounts[0] if len(amounts) == 1 else (None, "", "")
    reference_options = {
        value: quote for name in _REFERENCE_FIELDS for value, quote in fields.get(name, ())
    }
    if kind in ("payment", "refund"):
        for value, quote in fields.get("verwendungszweck", ()):
            if printed := _PURPOSE_REFERENCE.fullmatch(value):
                reference_options.setdefault(printed[1], quote)
    references = tuple(ref for ref in reference_options if _REFERENCE.fullmatch(ref))
    issuer, issuer_quote = _one_field(
        fields, _PAYEE_FIELDS if kind == "payment" else _ISSUER_FIELDS
    )
    if len(reference_options) > 1:
        kind = None
    amount = next(receipt_amounts(euro), None) if _EURO.fullmatch(euro) else None
    paid_on, payment_quote = None, ""
    if kind in ("payment", "refund") and amount is not None and not _PENDING.search(text):
        date_quotes = [quote for name in _DATE_FIELDS for _, quote in fields.get(name, ())]
        payments = payment_sources("\n".join((text, *date_quotes)))
        if len(payments) == 1:
            candidate = next(iter(payments))
            proof = amount_payment_source(payments, candidate, amount, amount_quote)
            if proof:
                paid_on, payment_quote = candidate, proof

    quotes = (
        booking,
        *reference_options.values(),
        issuer_quote,
        subject_quote,
        amount_quote,
        payment_quote,
    )
    source = SourceLocation(
        document=document,
        page=page,
        locator=" · ".join(dict.fromkeys(filter(None, quotes))) or "Belegseite",
    )
    return Receipt(
        references,
        issuer.casefold() or None,
        kind,
        description,
        amount if amount and amount > 0 else None,
        paid_on,
        source,
    )


def _match_group(receipts: list[Receipt]) -> Expense:
    invoices = [item for item in receipts if item.kind == "invoice"]
    payments = [item for item in receipts if item.kind == "payment"]
    refunds = [item for item in receipts if item.kind == "refund"]
    if len(invoices) != 1 or any(item.kind is None for item in receipts):
        raise ValueError("Welche Rechnung und welche Beträge gehören zu dieser Rechnungsnummer?")
    invoice = invoices[0]
    if len(payments) != 1:
        raise ValueError("Welcher ausgeführte Zahlungsbeleg gehört zu dieser Rechnung?")
    if len(refunds) > 1:
        raise ValueError("Welche Erstattungen gehören zu dieser Rechnung?")
    issuers = {item.issuer for item in receipts}
    if None in issuers or len(issuers) != 1:
        raise ValueError("Welcher Anbieter steht auf Rechnung, Zahlungsbeleg und Erstattung?")
    payment = payments[0]
    if not invoice.amount or invoice.amount != payment.amount:
        raise ValueError("Welcher Zahlungsbeleg weist den Rechnungsbetrag aus?")
    if any(item.paid_on is None or item.paid_on.year != 2025 for item in (*payments, *refunds)):
        raise ValueError(
            "Welcher Beleg zeigt das tatsächliche Zahlungs- oder Erstattungsdatum in 2025?"
        )
    refund = refunds[0] if refunds else None
    if refund and (not refund.amount or refund.amount > payment.amount):
        raise ValueError("Welcher Betrag wurde für diese Rechnung tatsächlich erstattet?")
    try:
        return Expense.model_validate(
            {
                "category": "training",
                "description": invoice.description,
                "amount": payment.amount,
                "paid_on": payment.paid_on,
                "source": invoice.source,
                "payment_source": payment.source,
                "reimbursement": (
                    {"amount": refund.amount, "paid_on": refund.paid_on, "source": refund.source}
                    if refund
                    else None
                ),
            }
        )
    except ValidationError as exc:
        raise ValueError("Welche Beträge in Euro stehen in den Originalbelegen?") from exc


def match_receipts(documents: dict[str, SourceDocument], originals: dict[str, bytes]) -> dict:
    """Review the supplied originals once and return proposals plus specific questions."""
    if documents.keys() != originals.keys() or len(
        {doc.sha256 for doc in documents.values()}
    ) != len(documents):
        raise ValueError("Wähle jedes Original einmal aus.")
    groups: dict[str, list[Receipt]] = defaultdict(list)
    refunds = []
    findings = []
    proposals = []
    for document, info in sorted(documents.items()):
        data = originals[document]
        if sha256(data).hexdigest() != info.sha256:
            raise ValueError(
                f"Die Prüfsumme von {info.path} stimmt nicht mit dem Original überein."
            )
        try:
            pages = _read_pages(data, info.path)
        except ValueError as exc:
            findings.append({"message": str(exc), "documents": [document]})
            continue
        if pages and all(not text.strip() for _, text in pages):
            findings.append(
                {
                    "message": "Kannst du für diesen Scan einen Beleg mit lesbarem Text auswählen?",
                    "documents": [document],
                }
            )
        is_statement = any(_BANK_STATEMENT.search(text) for _, text in pages)
        records = (
            _receipt(document, page, block, booking)
            for page, text in pages
            for booking, block in (_statement_bookings(text) if is_statement else ((None, text),))
        )
        for item in records:
            if item is None:
                continue
            if item.kind == "refund" and item.issuer:
                refunds.append(item)
            if item.references:
                for reference in item.references:
                    groups[reference].append(item)
            elif item.description:
                findings.append(
                    {
                        "message": "Wo steht die Rechnungsnummer dieses Belegs?",
                        "documents": [document],
                    }
                )
    training_groups = {
        key: items
        for key, items in groups.items()
        if any(item.description and item.kind in ("invoice", None) for item in items)
    }
    unlinked_refunds = [
        item for item in refunds if training_groups.keys().isdisjoint(item.references)
    ]
    for reference, receipts in sorted(training_groups.items()):
        invoice_issuers = {item.issuer for item in receipts if item.kind == "invoice"}
        possible_refunds = [item for item in unlinked_refunds if item.issuer in invoice_issuers]
        try:
            if possible_refunds:
                raise ValueError(
                    "Zu welcher Rechnung gehört der Erstattungsbeleg dieses Anbieters?"
                )
            expense = _match_group(receipts)
        except ValueError as exc:
            findings.append(
                {
                    "reference": reference,
                    "message": str(exc),
                    "documents": sorted(
                        {item.source.document for item in (*receipts, *possible_refunds)}
                    ),
                }
            )
        else:
            proposals.append(
                {
                    "reference": reference,
                    "expense": expense.model_dump(mode="json", exclude_none=True),
                }
            )
    return {"proposals": proposals, "findings": findings}
