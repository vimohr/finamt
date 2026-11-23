"""Read labeled bank statement tables from the positions of PDF words."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import pairwise

PdfWord = tuple[float, float, float, float, str, int, int, int]
Column = tuple[str, float, float]

_HEADINGS = {
    "buchungstag": "date",
    "buchungsdatum": "date",
    "empfänger": "payee",
    "zahlungsempfänger": "payee",
    "empfänger/auftraggeber": "payee",
    "empfänger / auftraggeber": "payee",
    "verwendungszweck": "purpose",
    "betrag": "amount",
    "betrag (eur)": "amount_eur",
    "betrag in eur": "amount_eur",
    "betrag eur": "amount_eur",
    "wertstellung": "value_date",
    "valuta": "value_date",
}
_REQUIRED = {"date", "payee", "purpose"}


@dataclass(frozen=True)
class BookingRow:
    number: int
    booking_date: str
    payee: str
    purpose: str
    amount: str
    euro_column: bool
    aligned: bool


def _visual_lines(words: list[PdfWord]) -> list[list[PdfWord]]:
    lines: list[list[PdfWord]] = []
    row_center = 0.0
    for word in sorted(words, key=lambda item: ((item[1] + item[3]) / 2, item[0])):
        center = (word[1] + word[3]) / 2
        # Allow small baseline differences within one printed line.
        if not lines or center - row_center > 2.0:
            lines.append([])
            row_center = center
        lines[-1].append(word)
    for line in lines:
        line.sort(key=lambda word: word[0])
    return lines


def _columns(line: list[PdfWord]) -> list[Column] | None:
    columns = []
    start = 0
    while start < len(line):
        for end in range(min(start + 3, len(line)), start, -1):
            title = " ".join(word[4].casefold() for word in line[start:end])
            key = _HEADINGS.get(title)
            if key is not None:
                columns.append((key, line[start][0], line[end - 1][2]))
                start = end
                break
        else:
            return None
    keys = {key for key, _, _ in columns}
    if len(keys) != len(columns) or keys - {"value_date"} not in (
        _REQUIRED | {"amount"},
        _REQUIRED | {"amount_eur"},
    ):
        return None
    if any(left[2] >= right[1] for left, right in pairwise(columns)):
        return None
    return columns


def read_booking_table(words: list[PdfWord]) -> list[BookingRow] | None:
    """Use exact labeled columns and keep each visual line separate."""
    rows: list[BookingRow] | None = None
    columns: list[Column] = []
    borders: list[float] = []
    for line in _visual_lines(words):
        header = _columns(line)
        if header is not None:
            columns = header
            borders = [(left[2] + right[1]) / 2 for left, right in pairwise(columns)]
            if rows is None:
                rows = []
            continue
        if rows is None:
            continue

        cells: list[list[str]] = [[] for _ in columns]
        aligned = True
        for left, _, right, _, text, *_ in line:
            cell = bisect_right(borders, (left + right) / 2)
            cells[cell].append(text)
            aligned &= bisect_right(borders, left) == bisect_left(borders, right)
        values = {key: " ".join(parts) for (key, _, _), parts in zip(columns, cells, strict=True)}
        rows.append(
            BookingRow(
                number=len(rows) + 1,
                booking_date=values["date"],
                payee=values["payee"],
                purpose=values["purpose"],
                amount=values.get("amount_eur", values.get("amount", "")),
                euro_column="amount_eur" in values,
                aligned=aligned,
            )
        )
    return rows
