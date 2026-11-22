"""Deterministic intake for the supported 2025 employee assessment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

VERSION = "2025.1"
Answer = Literal["yes", "no", "unsure"]


@dataclass(frozen=True)
class Question:
    key: str
    prompt: str
    supported_answer: Literal["yes", "no"]
    outside_scope: str


QUESTIONS = (
    Question(
        "residence",
        "Hattest du ganzjährig deinen steuerlichen Wohnsitz in Deutschland?",
        "yes",
        "Für einen unterjährigen oder ausländischen Wohnsitz braucht es eine gesonderte Prüfung.",
    ),
    Question(
        "single_assessment",
        "Gibst du die Erklärung für 2025 als Einzelveranlagung ab?",
        "yes",
        "Die Schätzung unterstützt die Einzelveranlagung. Eine Zusammenveranlagung braucht weitere Angaben und Regeln.",
    ),
    Question(
        "children",
        "Gab es 2025 ein Kind, für das Kindergeld oder ein Kinderfreibetrag in Betracht kommt?",
        "no",
        "Kinder und die damit verbundenen Freibeträge und Vergünstigungen brauchen eine gesonderte Prüfung.",
    ),
    Question(
        "foreign",
        "Gab es Arbeitslohn, eine Tätigkeit oder Dienstreisen im Ausland, etwa als Grenzgänger?",
        "no",
        "Für Arbeit oder Dienstreisen im Ausland gelten zusätzliche Regeln und Anlagen.",
    ),
    Question(
        "other_income",
        "Gab es neben regulärem Arbeitslohn weitere Einkünfte, etwa aus Rente, Vermietung, Selbstständigkeit oder anzugebenden Kapitalerträgen?",
        "no",
        "Weitere Einkunftsarten sind in der Jahresschätzung nicht enthalten.",
    ),
    Question(
        "replacement_benefits",
        "Hast du Lohnersatzleistungen wie Kurzarbeitergeld, Arbeitslosengeld, Elterngeld, Krankengeld oder Mutterschaftsgeld erhalten?",
        "no",
        "Lohnersatzleistungen können den Steuersatz ändern und müssen gesondert berücksichtigt werden.",
    ),
    Question(
        "special_wages",
        "Gab es Abfindungen, Versorgungsbezüge, Mehrjahresvergütungen oder steuerpflichtigen Lohn ohne Lohnsteuerbescheinigung?",
        "no",
        "Dieser Arbeitslohn erfordert eine gesonderte Prüfung der Bemessungsgrundlage und des Tarifs.",
    ),
    Question(
        "insurance_change",
        "Hat sich dein Krankenversicherungsstatus 2025 geändert, etwa von gesetzlich zu privat oder beim Krankengeldanspruch?",
        "no",
        "Die Jahresschätzung verwendet einen einheitlichen Versicherungsstatus für das ganze Jahr.",
    ),
    Question(
        "commute_exceptions",
        "Hattest du wechselnde Pendelstrecken oder Verkehrsmittel, einfache Fahrten ohne Rückweg am selben Tag oder eine doppelte Haushaltsführung?",
        "no",
        "Das Pendelprofil unterstützt eine Strecke mit gleichem Verkehrsmittel für Hin- und Rückfahrt.",
    ),
    Question(
        "additional_deductions",
        "Willst du ein häusliches Arbeitszimmer, Unterhalt oder außergewöhnliche Belastungen wie Krankheitskosten oder einen Behinderten-Pauschbetrag geltend machen?",
        "no",
        "Diese Abzüge brauchen Angaben, die der jetzige Entwurf noch nicht erfasst.",
    ),
)

_BY_KEY = {question.key: question for question in QUESTIONS}


class Intake2025(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    version: Literal["2025.1"]
    answers: dict[str, Answer] = Field(default_factory=dict, max_length=len(QUESTIONS))
    wage_certificate_count: Annotated[StrictInt, Field(ge=1, le=50)] | None = None


def catalogue() -> dict:
    return {
        "version": VERSION,
        "questions": [{"key": question.key, "prompt": question.prompt} for question in QUESTIONS],
    }


def _blocker(code: str, message: str, question: str | None = None) -> dict:
    finding = {"code": code, "severity": "blocker", "message": message}
    if question:
        finding["question"] = question
    return finding


def check_intake(intake: Intake2025 | None, *, wage_count: int | None = None) -> dict:
    if intake is None:
        return {
            "version": VERSION,
            "status": "needs_answers",
            "findings": [
                _blocker("intake_missing", "Beantworte zuerst die Fragen zur Steuersituation.")
            ],
        }

    findings = []
    unknown = set(intake.answers).difference(_BY_KEY)
    if unknown:
        findings.append(
            _blocker("intake_unknown_questions", "Die Falldatei enthält unbekannte Standardfragen.")
        )

    outside_scope = False
    for question in QUESTIONS:
        answer = intake.answers.get(question.key)
        if answer is None or answer == "unsure":
            findings.append(_blocker("intake_unresolved", question.prompt, question.key))
        elif answer != question.supported_answer:
            outside_scope = True
            findings.append(_blocker("intake_outside_scope", question.outside_scope, question.key))

    count = intake.wage_certificate_count
    if count is None:
        findings.append(
            _blocker(
                "intake_payroll_count_missing",
                "Wie viele gültige Lohnsteuerbescheinigungen liegen vor?",
            )
        )
    elif wage_count is not None and count != wage_count:
        findings.append(
            _blocker(
                "intake_payroll_count_differs",
                "Die Anzahl der bestätigten Lohnsteuerbescheinigungen stimmt mit der Angabe im Fragenkatalog nicht überein.",
            )
        )

    return {
        "version": VERSION,
        "status": "outside_scope"
        if outside_scope
        else "needs_answers"
        if findings
        else "supported",
        "findings": findings,
    }
