"""Transcribe a confirmed calendar into sourced workday facts for 2025."""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Literal

from .models import SourceLocation, Workday

_HEADER = ["Datum", "Erste Tätigkeitsstätte", "Homeoffice", "Dauerhaft kein anderer Arbeitsplatz"]
_YES_NO = {"ja": True, "nein": False}
_HOME_OFFICE: dict[str, Literal["none", "partly", "predominantly"]] = {
    "nein": "none",
    "teilweise": "partly",
    "überwiegend": "predominantly",
}


def workday_csv_template() -> str:
    return "\ufeff" + ";".join(_HEADER) + "\r\n"


def parse_workdays(content: bytes, document: str) -> list[Workday]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Speichere den Arbeitskalender als CSV mit UTF-8-Kodierung.") from exc

    rows = csv.reader(StringIO(text, newline=""), delimiter=";", strict=True)
    workdays = []
    seen: set[date] = set()
    try:
        if [cell.strip() for cell in next(rows, [])] != _HEADER:
            raise ValueError("Die Spalten des Arbeitskalenders müssen der Vorlage entsprechen.")
        previous_line = rows.line_num
        for row in rows:
            line = previous_line + 1
            previous_line = rows.line_num
            if not row:
                continue
            if len(row) != len(_HEADER) or line != rows.line_num:
                raise ValueError(f"Zeile {line} braucht vier Spalten in einer Zeile.")
            day_text, attended, home, exception = (field.strip().casefold() for field in row)
            try:
                day = date.fromisoformat(day_text)
            except ValueError as exc:
                raise ValueError(
                    f"Zeile {line} braucht ein gültiges Datum im Format JJJJ-MM-TT."
                ) from exc
            if day_text != day.isoformat() or day.year != 2025:
                raise ValueError(f"Zeile {line} braucht ein Datum aus 2025 im Format JJJJ-MM-TT.")
            if day in seen:
                raise ValueError(f"Der {day:%d.%m.%Y} kommt in Zeile {line} erneut vor.")
            if attended not in _YES_NO or exception not in _YES_NO or home not in _HOME_OFFICE:
                raise ValueError(
                    f"Zeile {line} braucht ja oder nein für Tätigkeitsstätte und Arbeitsplatz. "
                    "Für Homeoffice sind nein, teilweise und überwiegend gültig."
                )
            workdays.append(
                Workday(
                    day=day,
                    attended_first_workplace=_YES_NO[attended],
                    home_work=_HOME_OFFICE[home],
                    permanently_without_other_workplace=_YES_NO[exception],
                    sources=(SourceLocation(document=document, locator=f"Zeile {line}"),),
                )
            )
            seen.add(day)
    except csv.Error as exc:
        raise ValueError(f"Die CSV ist in Zeile {rows.line_num} ungültig.") from exc
    if not workdays:
        raise ValueError("Der Arbeitskalender enthält keine Arbeitstage.")
    return workdays
