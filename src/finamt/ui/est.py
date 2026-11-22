"""Stateless, local employee tax workspace."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from finamt.tax.est import EmployeeCase, draft_annual_return
from finamt.tax.est.assistants import (
    GuideContext,
    Stage,
    guide,
    independent_review,
    model_settings,
)
from finamt.tax.est.extraction import document_excerpt, propose_wage_certificate
from finamt.tax.est.intake_2025 import Intake2025, catalogue, check_intake
from finamt.tax.est.workday_csv_2025 import parse_workdays, workday_csv_template

router = APIRouter(prefix="/einkommensteuer", tags=["Einkommensteuer"])
_ASSETS = Path(__file__).parent / "static" / "einkommensteuer"
_MAX_FILE_BYTES = 12 * 1024 * 1024
_MAX_TOTAL_BYTES = 48 * 1024 * 1024
_MAX_DOCUMENTS = 50


@router.get("", include_in_schema=False)
def workspace():
    return FileResponse(
        _ASSETS / "index.html",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; frame-src blob:; img-src 'self' blob:; base-uri 'none'; form-action 'self'",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/workspace.css", include_in_schema=False)
def workspace_styles():
    return FileResponse(_ASSETS / "workspace.css")


@router.get("/workspace.js", include_in_schema=False)
def workspace_script():
    return FileResponse(_ASSETS / "workspace.js")


async def _read_original(file: UploadFile) -> bytes:
    data = await file.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(413, "Ein einzelner Beleg darf bis zu 12 MiB groß sein.")
    return data


@router.get("/api/settings")
def settings():
    return model_settings()


@router.get("/api/intake")
def intake_questions():
    return catalogue()


@router.post("/api/intake")
def review_intake(answers: Intake2025):
    return JSONResponse(check_intake(answers), headers={"Cache-Control": "no-store"})


@router.post("/api/payroll")
async def payroll(
    file: Annotated[UploadFile, File()],
    year: Annotated[int, Form()] = 2025,
    ocr: Annotated[bool, Form()] = False,
):
    data = await _read_original(file)
    try:
        result = await run_in_threadpool(
            propose_wage_certificate, data, file.filename or "lohnsteuer.pdf", year, allow_ocr=ocr
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/arbeitskalender-2025.csv", include_in_schema=False)
def workday_template():
    return PlainTextResponse(workday_csv_template(), media_type="text/csv")


@router.post("/api/workdays")
async def workdays(
    file: Annotated[UploadFile, File()],
    document: Annotated[str, Form(pattern=r"^[A-Za-z0-9_-]+$")],
):
    if Path(file.filename or "").suffix.lower() != ".csv":
        raise HTTPException(422, "Wähle einen Arbeitskalender im CSV-Format aus.")
    data = await _read_original(file)
    try:
        days = await run_in_threadpool(parse_workdays, data, document)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse(
        {
            "workdays": [day.model_dump(mode="json", exclude_none=True) for day in days],
            "sha256": sha256(data).hexdigest(),
        },
        headers={"Cache-Control": "no-store"},
    )


class GuideRequest(BaseModel):
    stage: Stage
    message: str = Field(max_length=1600)
    document: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    use_model: bool = False
    year: int = 2025
    progress: GuideContext | None = None


@router.post("/api/guide")
def guide_response(body: GuideRequest):
    response = guide(
        body.stage,
        body.message,
        body.document,
        use_model=body.use_model,
        year=body.year,
        progress=body.progress,
    )
    return JSONResponse(response, headers={"Cache-Control": "no-store"})


@router.post("/api/document-guide")
async def guide_document(
    file: Annotated[UploadFile, File()],
    document: Annotated[str, Form(pattern=r"^[A-Za-z0-9_-]+$")],
    stage: Annotated[Stage, Form()],
    message: Annotated[str, Form(max_length=1600)] = "",
    page: Annotated[int | None, Form(ge=1)] = None,
    progress_json: Annotated[str | None, Form(max_length=10_000)] = None,
):
    try:
        progress = GuideContext.model_validate_json(progress_json) if progress_json else None
    except ValidationError as exc:
        raise HTTPException(422, "Der Gesprächskontext ist ungültig.") from exc
    data = await _read_original(file)
    try:
        excerpt = await run_in_threadpool(document_excerpt, data, file.filename or "", page)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not excerpt:
        raise HTTPException(422, "Die ausgewählte Seite hat keinen lesbaren Text.")
    response = await run_in_threadpool(
        guide,
        stage,
        message,
        document,
        use_model=True,
        excerpt=excerpt,
        page=page,
        progress=progress,
    )
    return JSONResponse(response, headers={"Cache-Control": "no-store"})


def _reviewed_preview(case: EmployeeCase, documents: dict[str, bytes], use_model: bool) -> dict:
    draft = draft_annual_return(case, document_bytes=documents)
    report = independent_review(draft, draft["findings"], use_model=use_model, documents=documents)
    draft["review"] = report
    draft["review"]["status"] = (
        "clarification_needed"
        if any(item.get("severity") == "blocker" for item in report["findings"])
        else "reviewable_draft"
    )
    return draft


@router.post("/api/preview")
async def preview(
    case_json: Annotated[str, Form()],
    originals: Annotated[list[UploadFile], File()],
    use_model: Annotated[bool, Form()] = False,
):
    if len(case_json) > 512_000 or len(originals) > _MAX_DOCUMENTS:
        raise HTTPException(413, "Der Fall enthält zu viele Angaben oder Belege.")
    try:
        case = EmployeeCase.model_validate_json(case_json)
    except ValidationError as exc:
        details = [
            {"field": ".".join(map(str, error["loc"])), "message": error["msg"]}
            for error in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
        raise HTTPException(422, details) from exc
    documents = {}
    size = 0
    for file in originals:
        key = file.filename
        if key not in case.documents or key in documents:
            raise HTTPException(422, "Die ausgewählten Belege passen nicht zur Falldatei.")
        documents[key] = data = await _read_original(file)
        size += len(data)
        if size > _MAX_TOTAL_BYTES:
            raise HTTPException(413, "Die Belege dürfen zusammen bis zu 48 MiB groß sein.")
    try:
        draft = await run_in_threadpool(_reviewed_preview, case, documents, use_model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse(draft, headers={"Cache-Control": "no-store"})
