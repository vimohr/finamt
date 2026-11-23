from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from finamt.agents import llm_backend
from finamt.ui.api import app

INVOICE = """Rechnung
Rechnungsnummer: FB-2025-17
Rechnungssteller: Musterakademie
Empfänger: Ada Muster
Leistung: Berufliche Fortbildung Fachseminar
Rechnungsbetrag: 390,00 EUR
Rechnungsdatum: 03.04.2025
"""
PAYMENT = """Zahlungsbeleg
Rechnungs-Nr.: FB-2025-17
Empfänger: MUSTERAKADEMIE
Überwiesener Betrag
390,00 EUR
Buchungstag
2025-04-10
"""
REFUND = """Arbeitgebererstattung
Rechnungsnummer: FB-2025-17
Anbieter: Musterakademie
Empfänger: Ada Muster
Erstattungsbetrag: 125,00 EUR
Ausgezahlt am 30.04.2025.
"""
STATEMENT = """Kontoauszug April 2025
Buchung 1
Buchungstag: 08.04.2025
Empfänger: Andere Akademie
Überwiesener Betrag: 390,00 EUR
Verwendungszweck: Rechnung FB-2025-18

Buchung 2
Buchungstag: 10.04.2025
Empfänger: Musterakademie
Überwiesener Betrag: 390,00 EUR
Verwendungszweck: Rechnung FB-2025-17
"""


def _pdf(*pages: str, scan: bool = False) -> bytes:
    with fitz.open() as pdf:
        for text in pages:
            page = pdf.new_page()
            page.insert_text((42, 60), text, fontsize=10)
        if not scan:
            return pdf.tobytes()
        with fitz.open() as image_pdf:
            image_page = image_pdf.new_page()
            image_page.insert_image(image_page.rect, pixmap=pdf[0].get_pixmap())
            return image_pdf.tobytes()


def _documents(originals):
    return {
        key: {"path": name, "sha256": sha256(data).hexdigest()}
        for key, (name, data) in originals.items()
    }


def _uploads(originals):
    return [("originals", (key, data)) for key, (_, data) in originals.items()]


def _match(client, originals, documents=None):
    return client.post(
        "/einkommensteuer/api/receipt-matches",
        data={"documents_json": json.dumps(documents or _documents(originals))},
        files=_uploads(originals),
    )


@pytest.fixture
def originals():
    return {
        "invoice": ("rechnung.pdf", _pdf("Begleitschreiben", INVOICE)),
        "payment": ("zahlung.txt", PAYMENT.encode()),
        "refund": ("erstattung.pdf", _pdf(REFUND)),
    }


def test_matched_training_reaches_the_annual_draft_with_all_originals(originals, monkeypatch):
    def unexpected_model(*args, **kwargs):
        pytest.fail("Explicitly matched receipts should not reach a model")

    monkeypatch.setenv("FINAMT_EST_GUIDE_MODEL", "test-guide")
    monkeypatch.setattr(llm_backend, "generate", unexpected_model)
    with TestClient(app) as client:
        result = _match(client, originals)
        assert result.status_code == 200
        data = result.json()
        assert data["findings"] == []
        (proposal,) = data["proposals"]
        expense = proposal["expense"]
        assert proposal["reference"] == "FB-2025-17"
        assert expense["paid_on"] == "2025-04-10"
        assert expense["amount"] == "390.00"
        assert expense["source"]["page"] == 2
        assert expense["payment_source"]["document"] == "payment"
        assert "Buchungstag 2025-04-10" in expense["payment_source"]["locator"]
        assert expense["reimbursement"]["amount"] == "125.00"
        assert expense["reimbursement"]["paid_on"] == "2025-04-30"

        examples = Path(__file__).parents[2] / "examples" / "einkommensteuer-2025"
        case = json.loads((examples / "fall.json").read_text(encoding="utf-8"))
        case["expenses"] = [expense]
        case["documents"].update(_documents(originals))
        case_uploads = {
            key: (info["path"], (examples / info["path"]).read_bytes())
            for key, info in case["documents"].items()
            if key not in originals
        }
        case_uploads.update(originals)
        preview = client.post(
            "/einkommensteuer/api/preview",
            data={"case_json": json.dumps(case)},
            files=_uploads(case_uploads),
        )
        assert preview.status_code == 200
        trace = preview.json()["trace"]
        assert trace["training"]["value"] == "265.00"
        assert trace["expense.1.payment"]["sources"] == [
            expense["source"],
            expense["payment_source"],
        ]
        assert trace["expense.1.reimbursement"]["sources"] == [expense["reimbursement"]["source"]]

        case["expenses"].append(
            {
                **expense,
                "source": {**expense["source"], "locator": "Andere Fundstelle"},
                "payment_source": None,
                "reimbursement": None,
            }
        )
        duplicate = client.post(
            "/einkommensteuer/api/preview",
            data={"case_json": json.dumps(case)},
            files=_uploads(case_uploads),
        )
        assert duplicate.status_code == 422
        assert "An invoice matched to a payment can be claimed only once" in duplicate.text


@pytest.mark.parametrize(
    ("key", "content", "question"),
    [
        ("payment", None, "Zahlungsbeleg gehört"),
        ("payment", PAYMENT.replace("390,00", "380,00"), "Rechnungsbetrag"),
        ("payment", PAYMENT.replace("MUSTERAKADEMIE", "Andere Akademie"), "Anbieter"),
        ("payment", PAYMENT.replace("2025-04-10", "2024-04-10"), "in 2025"),
        ("payment", PAYMENT + "Terminüberweisung\n", "tatsächliche Zahlungs-"),
        ("payment", PAYMENT + "Rechnungsnummer: FB-2025-18", "welche Beträge"),
        ("payment", PAYMENT + "Überwiesener Betrag: 390,00 EUR", "welche Beträge"),
        ("payment", PAYMENT + "Zahlung eingegangen am 11.04.2025.", "tatsächliche Zahlungs-"),
        ("refund", REFUND.replace("125,00", "395,00"), "tatsächlich erstattet"),
        ("refund", REFUND.replace("FB-2025-17", "FB-2025-18"), "Erstattungsbeleg dieses Anbieters"),
    ],
)
def test_receipt_conflicts_are_reported_without_a_proposal(originals, key, content, question):
    if content is None:
        del originals[key]
    else:
        originals[key] = (f"{key}.txt", content.encode())
    with TestClient(app) as client:
        response = _match(client, originals)
    assert response.status_code == 200
    assert response.json()["proposals"] == []
    (finding,) = response.json()["findings"]
    assert question in finding["message"]
    assert finding["reference"] == "FB-2025-17"
    assert "invoice" in finding["documents"]


def test_invoice_reference_can_be_printed_in_bank_transfer_purpose(originals):
    bank_page = PAYMENT.replace(
        "Rechnungs-Nr.: FB-2025-17", "Verwendungszweck: Rechnung FB-2025-17"
    )
    originals["payment"] = ("zahlung.pdf", _pdf(bank_page))
    with TestClient(app) as client:
        response = _match(client, originals)
    assert response.status_code == 200
    result = response.json()
    assert result["findings"] == []
    (proposal,) = result["proposals"]
    assert (
        "Verwendungszweck: Rechnung FB-2025-17" in proposal["expense"]["payment_source"]["locator"]
    )


def test_bank_statement_selects_the_referenced_booking_even_with_equal_amounts(originals):
    title, _, bookings = STATEMENT.partition("\n")
    originals["payment"] = ("kontoauszug.pdf", _pdf(title, bookings))
    with TestClient(app) as client:
        response = _match(client, originals)
    assert response.status_code == 200
    result = response.json()
    assert result["findings"] == []
    (proposal,) = result["proposals"]
    expense = proposal["expense"]
    assert expense["paid_on"] == "2025-04-10"
    assert expense["payment_source"]["document"] == "payment"
    assert expense["payment_source"]["page"] == 2
    assert "Buchung 2" in expense["payment_source"]["locator"]
    assert "08.04.2025" not in expense["payment_source"]["locator"]


@pytest.mark.parametrize(
    ("statement", "question"),
    [
        (STATEMENT.replace("Buchungstag: 10.04.2025\n", ""), "tatsächliche Zahlungs-"),
        (STATEMENT.replace("Empfänger: Musterakademie\n", ""), "Anbieter"),
        (STATEMENT.replace("Rechnung FB-2025-18", "Rechnung FB-2025-17"), "Zahlungsbeleg gehört"),
    ],
)
def test_bank_statement_does_not_combine_fields_from_different_bookings(
    originals, statement, question
):
    originals["payment"] = ("kontoauszug.txt", statement.encode())
    with TestClient(app) as client:
        response = _match(client, originals)
    assert response.status_code == 200
    result = response.json()
    assert result["proposals"] == []
    (finding,) = result["findings"]
    assert question in finding["message"]


def test_scan_reports_missing_text_and_hash_mismatch_stops_matching(originals):
    originals["payment"] = ("scan.pdf", _pdf(PAYMENT, scan=True))
    with TestClient(app) as client:
        response = _match(client, originals)
        assert response.status_code == 200
        data = response.json()
        assert data["proposals"] == []
        assert any(
            finding["documents"] == ["payment"] and "lesbarem Text" in finding["message"]
            for finding in data["findings"]
        )
        documents = _documents(originals)
        originals["payment"] = ("scan.pdf", originals["payment"][1] + b"changed")
        bad_hash = _match(client, originals, documents)
        assert bad_hash.status_code == 422
        assert "Prüfsumme" in bad_hash.json()["detail"]
