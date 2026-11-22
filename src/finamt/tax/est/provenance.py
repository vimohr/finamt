"""Document integrity checks and a trace of source facts and derivations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import fitz

from .models import SourceDocument, SourceLocation


class CalculationTrace:
    def __init__(
        self,
        documents: dict[str, SourceDocument],
        source_dir: Path | None = None,
        *,
        document_bytes: dict[str, bytes] | None = None,
        keep_originals: frozenset[str] = frozenset(),
    ) -> None:
        self.documents = {key: document.model_dump() for key, document in sorted(documents.items())}
        self.entries: dict[str, dict] = {}
        self.originals: dict[str, bytes] = {}
        self._page_counts: dict[str, int | None] = {}
        for key, document in documents.items():
            if document_bytes is not None and key in document_bytes:
                data = document_bytes[key]
            elif source_dir is not None and (path := source_dir / document.path).is_file():
                data = path.read_bytes()
            else:
                raise ValueError(f"Source document {key} is missing or is not a regular file")
            if sha256(data).hexdigest() != document.sha256:
                raise ValueError(f"SHA-256 mismatch for source document {key}")
            if key in keep_originals:
                self.originals[key] = data
            self._page_counts[key] = None
            if Path(document.path).suffix.lower() == ".pdf" or data.startswith(b"%PDF-"):
                try:
                    with fitz.open(stream=data, filetype="pdf") as pdf:
                        if pdf.needs_pass:
                            raise ValueError(f"Source PDF {key} requires a password")
                        self._page_counts[key] = pdf.page_count
                except (fitz.FileDataError, fitz.EmptyFileError) as exc:
                    raise ValueError(f"Source document {key} is not a readable PDF") from exc

    def _entry(self, key: str, value: Decimal | int | date | str, unit: str) -> dict:
        if key in self.entries:
            raise ValueError(f"Duplicate calculation trace key: {key}")
        if isinstance(value, Decimal):
            value = format(value, ".2f" if unit == "EUR" else "f")
        elif isinstance(value, date):
            value = value.isoformat()
        entry = {"value": value, "unit": unit}
        self.entries[key] = entry
        return entry

    def fact(
        self,
        key: str,
        value: Decimal | int | date | str,
        unit: str,
        sources: tuple[SourceLocation, ...],
        *,
        details: dict | None = None,
    ) -> None:
        for source in sources:
            if source.document not in self._page_counts:
                raise ValueError(f"Unknown source document {source.document}")
            pages = self._page_counts[source.document]
            if pages is not None and (source.page is None or source.page > pages):
                raise ValueError(f"Provide a valid PDF page for source document {source.document}")
            if pages is None and source.page is not None:
                raise ValueError(
                    f"Use a text locator for non-PDF source document {source.document}"
                )
        entry = self._entry(key, value, unit)
        entry["sources"] = [source.model_dump(exclude_none=True) for source in sources]
        if details is not None:
            entry["details"] = details

    def rule(
        self,
        key: str,
        value: Decimal | int,
        unit: str,
        basis: str,
    ) -> None:
        self._entry(key, value, unit)["legal_basis"] = basis

    def derive(
        self,
        key: str,
        value: Decimal | int,
        unit: str,
        rule: str,
        inputs: list[str],
    ) -> None:
        for input_key in inputs:
            if input_key not in self.entries:
                raise ValueError(f"Unknown calculation trace key: {input_key}")
        self._entry(key, value, unit).update(rule=rule, inputs=inputs)

    def result(self, key: str) -> dict:
        entry = self.entries[key]
        return {"value": entry["value"], "unit": entry["unit"], "trace": key}

    def form_field(self, key: str, line: int, code: str | None = None) -> dict:
        field = {"key": key, "line": line, **self.result(key)}
        if code is not None:
            field["kennzahl"] = code
        return field
