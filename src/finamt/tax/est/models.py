"""Reviewed inputs for an employee's annual tax return."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DocumentId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$")]
PageNumber = Annotated[StrictInt, Field(ge=1)]
CalendarDate = Annotated[date, Field(strict=True)]


def _decimal_string(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        return Decimal(value)
    raise ValueError("Expected a decimal string with a dot as the decimal separator")


Money = Annotated[
    Decimal, BeforeValidator(_decimal_string), Field(ge=0, max_digits=12, decimal_places=2)
]
Distance = Annotated[
    Decimal, BeforeValidator(_decimal_string), Field(ge=0, max_digits=8, decimal_places=3)
]
WagePosition = Literal["3", "4", "5", "6", "17", "18"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SourceDocument(_Input):
    path: Text
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class SourceLocation(_Input):
    document: DocumentId
    locator: Text
    page: PageNumber | None = None


class WageCertificate(_Input):
    """A reviewed transcription of the supported Lohnsteuerbescheinigung positions."""

    document: DocumentId
    page: PageNumber | None = None
    transfer_ticket: Text
    period_end: CalendarDate
    tax_class: Annotated[StrictInt, Field(ge=1, le=6)]
    amounts: dict[WagePosition, Money]

    @model_validator(mode="after")
    def require_gross_wages(self) -> WageCertificate:
        if "3" not in self.amounts:
            raise ValueError("Provide Bruttoarbeitslohn (Lohnsteuerbescheinigung Nr. 3)")
        return self

    def locate(self, locator: str) -> SourceLocation:
        return SourceLocation(document=self.document, page=self.page, locator=locator)


class TransportCost(_Input):
    amount: Money
    source: SourceLocation


class Commute(_Input):
    """One confirmed route, used in both directions with the same mode each day."""

    distance_km: Distance
    mode: Literal["own_or_provided_car", "public_transport", "other"]
    source: SourceLocation
    public_transport_costs: tuple[TransportCost, ...] = ()

    @model_validator(mode="after")
    def validate_public_transport_costs(self) -> Commute:
        if self.public_transport_costs and self.mode != "public_transport":
            raise ValueError("Public transport costs require public_transport mode")
        sources = {cost.source for cost in self.public_transport_costs}
        if len(sources) != len(self.public_transport_costs):
            raise ValueError("Use a distinct source location for each transport cost")
        return self


class Workday(_Input):
    day: CalendarDate
    attended_first_workplace: StrictBool
    home_work: Literal["none", "partly", "predominantly"]
    permanently_without_other_workplace: StrictBool
    sources: Annotated[tuple[SourceLocation, ...], Field(min_length=1)]


class EmployeeCase(_Input):
    """Confirmed facts for one taxpayer and one assessment year."""

    schema_version: Annotated[StrictInt, Field(ge=1, le=1)]
    tax_year: StrictInt
    reviewed_standard_case: StrictBool
    documents: dict[DocumentId, SourceDocument]
    wage_certificates: Annotated[tuple[WageCertificate, ...], Field(min_length=1)]
    commute: Commute | None = None
    workdays: tuple[Workday, ...] = ()

    @model_validator(mode="after")
    def validate_case(self) -> EmployeeCase:
        if not self.reviewed_standard_case:
            raise ValueError("Confirm the transcribed data and the supported case scope")
        if len({item.sha256 for item in self.documents.values()}) != len(self.documents):
            raise ValueError("Use one document ID per original file")
        certificates = self.wage_certificates
        if len({item.document for item in certificates}) != len(certificates):
            raise ValueError("Use one original file per wage certificate")
        if len({item.transfer_ticket.upper() for item in certificates}) != len(certificates):
            raise ValueError("Duplicate wage certificate (transfer ticket)")
        if any(item.period_end.year != self.tax_year for item in certificates):
            raise ValueError("Wage certificate period must end in the assessment year")
        if any(item.day.year != self.tax_year for item in self.workdays):
            raise ValueError("Workdays must be in the assessment year")
        if len({item.day for item in self.workdays}) != len(self.workdays):
            raise ValueError("Use one calendar entry per workday")
        if self.commute is None and any(item.attended_first_workplace for item in self.workdays):
            raise ValueError("Provide a commute route for days at the first workplace")
        return self
