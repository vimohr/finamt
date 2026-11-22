from __future__ import annotations

import json

import fitz
import pytest
from fastapi.testclient import TestClient

from finamt.tax.est.extraction import propose_wage_certificate
from finamt.ui.api import app


@pytest.fixture
def synthetic_pdf():
    lines = [
        "Ausdruck der elektronischen Lohnsteuerbescheinigung für 2025",
        "1. Bescheinigungszeitraum 01.01.2025 bis 31.12.2025",
        "Steuerklasse/Faktor: 1",
        "Transferticket: SYNTHETIC-2025-001",
        "3. Bruttoarbeitslohn einschl. Sachbezüge 46.250,30 EUR",
        "4. Einbehaltene Lohnsteuer von 3.     7842     10",
        "5. Einbehaltener Solidaritätszuschlag von 3. 0,00",
        "6. Einbehaltene Kirchensteuer des Arbeitnehmers von 3.",
        "22a. Arbeitgeberanteil gesetzliche Rentenversicherung 4.200,21",
        "23. Arbeitnehmeranteil a) zur gesetzlichen Rentenversicherung 4.200,21",
        "24. Steuerfreie Arbeitgeberzuschüsse b) zur privaten Krankenversicherung",
        "25. Arbeitnehmerbeiträge zur gesetzlichen Krankenversicherung 3.800,50",
        "27. Arbeitnehmerbeiträge zur Arbeitslosenversicherung 490,80",
    ]
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((36, 45), "\n".join(lines), fontsize=10)
        return pdf.tobytes()


def _web_case(result):
    item = result["proposals"][0]["certificate"]
    doc = result["document_id"]
    return {
        "schema_version": 1,
        "tax_year": 2025,
        "reviewed_standard_case": True,
        "documents": {doc: result["document"]},
        "wage_certificates": [item],
    }


def _preview(client, case, pdf):
    doc = case["wage_certificates"][0]["document"]
    return client.post(
        "/einkommensteuer/api/preview",
        data={"case_json": json.dumps(case)},
        files=[("originals", (doc, pdf, "application/pdf"))],
    )


def test_workspace_upload_review_and_source_check(synthetic_pdf):
    with TestClient(app) as client:
        home = client.get("/einkommensteuer")
        assert home.status_code == 200
        assert "Steuerassistent" in home.text
        assert "no-store" == home.headers["cache-control"]
        assert client.get("/einkommensteuer/workspace.js").status_code == 200
        assert client.get("/einkommensteuer/workspace.css").status_code == 200
        imported = client.post(
            "/einkommensteuer/api/payroll",
            files={"file": ("lohn.pdf", synthetic_pdf, "application/pdf")},
        )
        assert imported.status_code == 200
        result = imported.json()
        assert result["proposals"][0]["missing"] == []
        case = _web_case(result)
        wage = case["wage_certificates"][0]
        assert wage["amounts"]["3"] == "46250.30"
        assert wage["amounts"]["4"] == "7842.10"
        assert wage["amounts"]["22a"] == "4200.21"
        assert wage["amounts"]["23a"] == "4200.21"
        assert wage["amounts"]["25"] == "3800.50"
        assert "6" not in wage["amounts"]
        assert (
            client.post(
                "/einkommensteuer/api/preview", data={"case_json": json.dumps(case)}
            ).status_code
            == 422
        )

        reviewed = _preview(client, case, synthetic_pdf)
        assert reviewed.status_code == 200
        draft = reviewed.json()
        assert draft["summary"]["gross_wages"]["value"] == "46250.30"
        assert draft["review"]["status"] == "reviewable_draft"
        assert draft["review"]["agent"] == "rules_only"
        assert draft["trace"][f"wage.{wage['document']}.3"]["sources"] == [
            {"document": wage["document"], "locator": "Nr. 3", "page": 1}
        ]

        wage["amounts"]["3"] = "45999.10"
        mismatch = _preview(client, case, synthetic_pdf).json()
        assert mismatch["review"]["status"] == "clarification_needed"
        assert any(
            finding["code"] == "payroll_amount_differs" and finding["severity"] == "blocker"
            for finding in mismatch["review"]["findings"]
        )
        invalid = _preview(client, case, synthetic_pdf + b"substituted")
        assert invalid.status_code == 422
        assert "SHA-256 mismatch" in invalid.json()["detail"]


def test_extraction_does_not_accept_unrelated_or_incomplete_content():
    with fitz.open() as source:
        page = source.new_page()
        page.insert_text((45, 45), "Not a wage certificate\nAmount EUR 500.00")
        data = source.tobytes()
    result = propose_wage_certificate(data, "name.pdf", 2025)
    assert result["proposals"] == []
    assert result["notes"]


def test_official_layout_tax_class_printed_above_label():
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((300, 40), "Lohnsteuerbescheinigung 2025")
        page.insert_text((300, 90), "1. Bescheinigungszeitraum 01.01.2025 bis 31.12.2025")
        page.insert_text((300, 150), "3. Bruttoarbeitslohn 45.000,00")
        page.insert_text((52, 118), "Transferticket: TEST-CLASS-01")
        page.insert_text((52, 159), "3", fontsize=9)
        page.insert_text((52, 176), "Steuerklasse/Faktor", fontsize=9)
        data = pdf.tobytes()
    proposals = propose_wage_certificate(data, "form.pdf", 2025)["proposals"]
    assert proposals[0]["certificate"]["tax_class"] == 3
    assert not proposals[0]["missing"]


def test_guide_requires_exact_selected_source_and_reviewer_is_read_only(monkeypatch, synthetic_pdf):
    from finamt.agents import llm_backend

    monkeypatch.setenv("FINAMT_EST_GUIDE_MODEL", "test-guidance")
    monkeypatch.setenv("FINAMT_EST_REVIEW_MODEL", "test-reviewer")
    seen_prompts = []

    def fake_generate(prompt, model, **options):
        seen_prompts.append((model, prompt))
        if model == "test-guidance":
            return json.dumps(
                {
                    "reply": "Prüfe die Fortbildung gegen den Zahlungsnachweis.",
                    "candidate": {
                        "collection": "expenses",
                        "facts": {
                            "category": "training",
                            "description": "Fachkurs",
                            "amount": "230.00",
                            "paid_on": "2025-04-08",
                            "source": {"document": "training", "locator": "Position Gebühren"},
                        },
                    },
                }
            )
        return json.dumps(
            {
                "findings": [
                    {
                        "trace": "gross_wages",
                        "question": "Stimmen die Summen mit dem Original überein?",
                    },
                    {"trace": "fabricated", "question": "Dieser Schlüssel gehört nicht zum Fall."},
                ]
            }
        )

    monkeypatch.setattr(llm_backend, "generate", fake_generate)
    with TestClient(app) as client:
        assert client.get("/einkommensteuer/api/settings").json() == {
            "guide": True,
            "reviewer": True,
        }
        body = {
            "stage": "expenses",
            "message": "Fachkurs am 8.4. für 230 Euro",
            "document": "training",
            "use_model": True,
            "progress": {
                "wages_confirmed": 1,
                "history": [{"role": "user", "text": "Der Kurs war im April."}],
            },
        }
        intake = client.post("/einkommensteuer/api/guide", json=body).json()
        assert intake["candidate"]["facts"]["amount"] == "230.00"
        assert "Der Kurs war im April." in seen_prompts[0][1]
        body["document"] = "another"
        assert client.post("/einkommensteuer/api/guide", json=body).json()["candidate"] is None
        result = propose_wage_certificate(synthetic_pdf, "lohn.pdf", 2025)
        case = _web_case(result)
        reviewed = client.post(
            "/einkommensteuer/api/preview",
            data={"case_json": json.dumps(case), "use_model": "true"},
            files=[("originals", (result["document_id"], synthetic_pdf, "application/pdf"))],
        ).json()
    assert reviewed["review"]["agent"] == "local_model"
    assert reviewed["summary"]["gross_wages"]["value"] == "46250.30"
    assert [
        f["trace"] for f in reviewed["review"]["findings"] if f["code"] == "reviewer_question"
    ] == [
        "gross_wages",
    ]
    reviewer_prompt = seen_prompts[-1][1]
    assert seen_prompts[-1][0] == "test-reviewer"
    assert "Fachkurs" not in reviewer_prompt
    assert "Der Kurs war im April." not in reviewer_prompt
    assert "SYNTHETIC-2025-001" not in reviewer_prompt


def test_document_guide_accepts_only_a_cited_original_amount(monkeypatch):
    from finamt.agents import llm_backend

    monkeypatch.setenv("FINAMT_EST_GUIDE_MODEL", "test-guide")
    source = b"Fachkurs\nBezahlt 08.04.2025\nKursgebuehr: 1.120,00 EUR"
    candidate = {
        "reply": "Hast du die Zahlung selbst getragen?",
        "candidate": {
            "collection": "expenses",
            "quote": "Kursgebuehr: 1.120,00 EUR",
            "facts": {
                "category": "training",
                "description": "Fachkurs",
                "amount": "1120.00",
                "paid_on": "2025-04-08",
                "source": {"document": "kurs", "locator": "Eingabe des Modells"},
            },
        },
    }
    monkeypatch.setattr(llm_backend, "generate", lambda *args, **kwargs: json.dumps(candidate))
    with TestClient(app) as client:

        def propose(content=source):
            return client.post(
                "/einkommensteuer/api/document-guide",
                data={"stage": "expenses", "document": "kurs"},
                files={"file": ("rechnung.txt", content, "text/plain")},
            ).json()

        proposal = propose()["candidate"]
        assert proposal["facts"]["source"]["locator"] == "Kursgebuehr: 1.120,00 EUR"
        assert proposal["facts"]["amount"] == "1120.00"
        assert propose(source + b"\n" + source)["candidate"] is None
        candidate["candidate"]["facts"]["amount"] = "1121.00"
        assert propose()["candidate"] is None
        candidate["candidate"]["facts"]["amount"] = "1120.00"
        candidate["candidate"]["quote"] = "Frei erfundener Betrag 1.120,00 EUR"
        assert propose()["candidate"] is None
