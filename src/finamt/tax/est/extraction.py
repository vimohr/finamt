"""Local extraction of reviewable wage-certificate proposals."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import get_args

import fitz

from finamt.exceptions import OCRProcessingError
from finamt.ocr_processor import OCRProcessor

from .models import EmployeeCase, WagePosition

_ROW = re.compile(r"(?:^|\s{2,})(?:Nr\.\s*)?([1-3]?\d)(?:\s*([a-c]))?[.)]\s+(\S.*)$", re.I)
_MONEY = re.compile(r"(?<!\S)(-?\d+(?:\.\d{3})*),(\d{2})(?:\s*(?:EUR|€))?\s*$")
_EURO_CENT_COLUMNS = re.compile(r"\s{2,}(-?\d+(?:\.\d{3})*)\s{2,}(\d{2})\s*$")
_PERIOD = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:bis|[-–])\s*(\d{1,2}\.\d{1,2}\.\d{4})")
_TICKET = re.compile(r"Transferticket:\s*([A-Za-z0-9][A-Za-z0-9-]{3,})\b", re.I)
_CLASS = re.compile(r"Steuerklasse(?:\s*/\s*Faktor)?\s*[:\s]+([1-6])(?=\s|/|$)", re.I)
_PENSION = re.compile(
    r"([ab])\)\s*(?:zur gesetzlichen Rentenversicherung|an berufsständische)", re.I
)
_HEALTH = re.compile(
    r"([abc])\)\s*zur (?:gesetzlichen|privaten) (?:Kranken|Pflege)versicherung", re.I
)
_KNOWN_YEARS = (2025,)
_WAGE_POSITIONS = frozenset(get_args(WagePosition))
_RECEIPT_AMOUNT = re.compile(
    r"(?<![\d.,+\-])(\d{1,3}(?:[.\u00a0 ]\d{3})+|\d+)[,.](\d{2})(?![\d.,])"
)


def _amount(line: str) -> Decimal | None:
    match = _MONEY.search(line) or _EURO_CENT_COLUMNS.search(line)
    if match is None:
        return None
    return Decimal(f"{match[1].replace('.', '')}.{match[2]}")


def _date(value: str) -> date:
    day, month, year = (int(part) for part in value.split("."))
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError("The wage certificate contains an invalid printed date") from exc


def _tax_class_near_label(page: fitz.Page) -> int | None:
    for heading in page.search_for("Steuerklasse/Faktor"):
        area = fitz.Rect(heading.x0 - 24, heading.y0 - 20, heading.x1 + 74, heading.y1 + 16)
        candidates = {
            int(word[4])
            for word in page.get_text("words", clip=area)
            if re.fullmatch(r"[1-6]", word[4])
        }
        if len(candidates) == 1:
            return next(iter(candidates))
    return None


def _page_proposal(
    text: str,
    page: int,
    document_id: str,
    year: int,
    layout_tax_class: int | None,
) -> dict | None:
    if not re.search(r"Lohnsteuerbescheinigung", text, re.I) or not re.search(
        r"Bruttoarbeitslohn", text, re.I
    ):
        return None

    lines = [line.strip().replace("\xad", "") for line in text.splitlines() if line.strip()]
    period = _PERIOD.search(text)
    ticket = _TICKET.search(text)
    printed_class = _CLASS.search(text)
    tax_class = int(printed_class[1]) if printed_class else layout_tax_class
    end = _date(period[2]) if period else None
    missing = [
        name
        for name, value in (
            ("period_end", end),
            ("transfer_ticket", ticket),
            ("tax_class", tax_class),
        )
        if value is None
    ]
    notes = []
    if end and end.year != year:
        notes.append("Der Zeitraum auf dem Beleg endet in einem anderen Kalenderjahr.")

    rows: dict[str, set[Decimal]] = {}
    headings: dict[str, list[int]] = {}
    pension_parts: list[tuple[int, str, Decimal]] = []
    for index, line in enumerate(lines):
        row = _ROW.search(line)
        amount = _amount(line)
        if row:
            position = row[1] + (row[2] or "").lower()
            headings.setdefault(position, []).append(index)
            if amount is not None and position not in ("22", "23", "24"):
                rows.setdefault(position, set()).add(amount)
        if amount is None:
            continue
        if health := _HEALTH.search(line):
            rows.setdefault("24" + health[1].lower(), set()).add(amount)
        if pension := _PENSION.search(line):
            subposition = pension[1].lower()
            if row and row[1] in ("22", "23") and not row[2]:
                rows.setdefault(row[1] + subposition, set()).add(amount)
            else:
                pension_parts.append((index, subposition, amount))

    pension_headings = [
        (position, headings[position][0])
        for position in ("22", "23")
        if len(headings.get(position, ())) == 1
    ]
    for index, subposition, amount in pension_parts:
        if len(pension_headings) == 2:
            preceding = [part for part in pension_headings if part[1] <= index + 1]
            if preceding:
                position = preceding[-1][0] + subposition
                rows.setdefault(position, set()).add(amount)

    amounts = {}
    unsupported = set()
    for position, values in rows.items():
        if len(values) != 1:
            notes.append(f"Mehrere unterschiedliche Beträge bei Position {position}.")
            unsupported.add(position)
            continue
        amount = next(iter(values))
        if amount < 0:
            unsupported.add(position)
        elif position in _WAGE_POSITIONS:
            amounts[position] = format(amount, ".2f")
        elif (
            position
            in {"7", "8", "9", "10", "15", "15a", "16", "16a", "16b", "21", "29", "32", "34"}
            and amount
        ):
            unsupported.add(position)
        elif position == "28" and amount:
            notes.append(
                "Position 28 mit der Beitragsbescheinigung der privaten Krankenversicherung abgleichen."
            )
    if "3" not in amounts:
        missing.append("amounts.3")
    if any(
        re.search(
            r"\b(?:Stornierung|Korrektur)\s*[:X]\s*(?:ja|x|1|Stornierung|Korrektur)\b", line, re.I
        )
        for line in lines
    ):
        notes.append(
            "Korrektur oder Stornierung angegeben. Nur die gültige Bescheinigung übernehmen."
        )
        unsupported.add("correction_or_cancellation")
    if unsupported:
        notes.append(
            "Einige Positionen benötigen eine gesonderte Prüfung vor der Jahresberechnung."
        )
    return {
        "certificate": {
            "document": document_id,
            "page": page,
            "period_end": end.isoformat() if end else "",
            "transfer_ticket": ticket[1] if ticket else "",
            "tax_class": tax_class,
            "amounts": amounts,
            "unsupported_positions": sorted(unsupported),
        },
        "missing": missing,
        "notes": notes,
    }


def propose_wage_certificate(
    content: bytes,
    filename: str,
    tax_year: int,
    *,
    allow_ocr: bool = False,
) -> dict:
    if tax_year not in _KNOWN_YEARS:
        raise ValueError(f"Kein Bescheinigungsmuster für das Steuerjahr {tax_year} vorhanden.")
    digest = sha256(content).hexdigest()
    document_id = f"beleg_{digest[:24]}"
    notes = []
    proposals = []
    try:
        with fitz.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValueError("Bitte eine entsperrte PDF-Datei auswählen.")
            if pdf.page_count > 10:
                raise ValueError(
                    "Bitte die Seiten einer einzelnen Lohnsteuerbescheinigung auswählen."
                )
            for page in pdf:
                extracted = page.get_text(sort=True)
                if len(extracted.strip()) < 60 and allow_ocr:
                    try:
                        with fitz.open() as single_page:
                            single_page.insert_pdf(pdf, from_page=page.number, to_page=page.number)
                            extracted = OCRProcessor().extract_text_from_pdf(single_page.tobytes())
                    except OCRProcessingError:
                        notes.append(f"OCR konnte Seite {page.number + 1} nicht lesen.")
                proposal = _page_proposal(
                    extracted, page.number + 1, document_id, tax_year, _tax_class_near_label(page)
                )
                if proposal:
                    proposals.append(proposal)
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError("Die Datei ist keine lesbare PDF-Datei.") from exc
    if not proposals:
        notes.append(
            "Keine vollständige Lohnsteuerbescheinigung erkannt. Bitte das Original ansehen und die Positionen erfassen."
        )
    return {
        "document_id": document_id,
        "document": {"path": Path(filename).name, "sha256": digest},
        "proposals": proposals,
        "notes": notes,
    }


def document_excerpt(content: bytes, filename: str, page: int | None) -> str:
    """Return text for a selected source, with at most one PDF page."""
    if Path(filename).suffix.lower() == ".pdf" or content.startswith(b"%PDF-"):
        if page is None or page < 1:
            raise ValueError("Wähle eine Seite für den PDF-Beleg aus.")
        try:
            with fitz.open(stream=content, filetype="pdf") as pdf:
                if pdf.needs_pass or page > pdf.page_count:
                    raise ValueError("Die angegebene PDF-Seite ist nicht zugänglich.")
                return pdf[page - 1].get_text(sort=True).strip()[:6000]
        except (fitz.FileDataError, fitz.EmptyFileError) as exc:
            raise ValueError("Die Datei ist keine lesbare PDF-Datei.") from exc
    if page is not None:
        raise ValueError("Seitenangaben sind nur bei PDF-Belegen möglich.")
    if Path(filename).suffix.lower() not in {".txt", ".csv"}:
        raise ValueError("Verwende für Belegvorschläge eine PDF- oder Textdatei.")
    return content[:24_000].decode("utf-8", errors="replace").strip()[:6000]


def matching_amount(quote: str, amount: Decimal) -> bool:
    return any(
        Decimal(re.sub(r"[.\u00a0 ]", "", match[1]) + "." + match[2]) == amount
        for match in _RECEIPT_AMOUNT.finditer(quote)
    )


def review_wage_originals(case: EmployeeCase, documents: dict[str, bytes]) -> list[dict]:
    """Compare transcribed fields to an independent read of the original PDF."""
    findings = []
    for wage in sorted(case.wage_certificates, key=lambda item: item.document):
        key = f"wage.{wage.document}"
        source = case.documents[wage.document]
        data = documents[wage.document]
        if Path(source.path).suffix.lower() != ".pdf" and not data.startswith(b"%PDF-"):
            findings.append(
                {
                    "code": "payroll_manual_source",
                    "severity": "notice",
                    "trace": f"{key}.3",
                    "message": "Der Originalbeleg wurde als Text referenziert. Bitte die Lohnbeträge manuell abgleichen.",
                }
            )
            continue
        proposed = propose_wage_certificate(data, source.path, case.tax_year)["proposals"]
        if len(proposed) > 1:
            findings.append(
                {
                    "code": "payroll_multiple_certificates",
                    "severity": "blocker",
                    "trace": f"{key}.3",
                    "message": "Mehrere Bescheinigungen in einer PDF erkannt. Bitte die gültigen Bescheinigungen einzeln erfassen.",
                }
            )
        candidate = next(
            (
                entry["certificate"]
                for entry in proposed
                if entry["certificate"]["page"] == wage.page
            ),
            None,
        )
        if candidate is None or "3" not in candidate["amounts"]:
            findings.append(
                {
                    "code": "payroll_not_readable",
                    "severity": "notice",
                    "trace": f"{key}.3",
                    "message": "Die zweite Auslese konnte den Bruttoarbeitslohn nicht prüfen. Bitte die Originalseite ansehen.",
                }
            )
            if candidate is None:
                continue
        if candidate["unsupported_positions"]:
            findings.append(
                {
                    "code": "payroll_exception_found",
                    "severity": "blocker",
                    "trace": f"{key}.3",
                    "message": "Der Originalbeleg enthält Positionen außerhalb des unterstützten Standardfalls.",
                }
            )
        for position, amount in candidate["amounts"].items():
            recorded = wage.amounts.get(position)
            if (recorded is None and Decimal(amount) != 0) or (
                recorded is not None and Decimal(amount) != recorded
            ):
                findings.append(
                    {
                        "code": "payroll_amount_differs",
                        "severity": "blocker",
                        "trace": f"{key}.{position}" if recorded is not None else f"{key}.3",
                        "message": f"Position {position} weicht vom zweiten Auslesen ab. Bitte Betrag direkt am Original prüfen.",
                    }
                )
        for position in sorted(set(wage.amounts) - set(candidate["amounts"])):
            findings.append(
                {
                    "code": "payroll_position_not_readable",
                    "severity": "notice",
                    "trace": f"{key}.{position}",
                    "message": f"Position {position} ließ sich beim erneuten Auslesen nicht bestätigen.",
                }
            )
        for field in ("tax_class", "period_end"):
            value = candidate.get(field)
            if value and value != wage.model_dump(mode="json")[field]:
                findings.append(
                    {
                        "code": "payroll_details_differ",
                        "severity": "blocker",
                        "trace": f"{key}.{field}",
                        "message": "Steuerklasse oder Zeitraum weicht vom zweiten Auslesen ab. Bitte Original prüfen.",
                    }
                )
    return findings
