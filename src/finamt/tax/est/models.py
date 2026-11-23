"""Reviewed inputs for an employee's annual tax return."""

from __future__ import annotations

import re
from collections import Counter
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

from .intake_2025 import Intake2025

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
Percent = Annotated[
    Decimal, BeforeValidator(_decimal_string), Field(ge=0, le=100, decimal_places=2)
]
WagePosition = Literal[
    "3",
    "4",
    "5",
    "6",
    "17",
    "18",
    "20",
    "22a",
    "22b",
    "23a",
    "23b",
    "24a",
    "24b",
    "24c",
    "25",
    "26",
    "27",
]


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
    unsupported_positions: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def require_gross_wages(self) -> WageCertificate:
        if "3" not in self.amounts:
            raise ValueError("Provide Bruttoarbeitslohn (Lohnsteuerbescheinigung Nr. 3)")
        return self

    def locate(self, locator: str) -> SourceLocation:
        return SourceLocation(document=self.document, page=self.page, locator=locator)


class SourcedAmount(_Input):
    amount: Money
    source: SourceLocation


TransportCost = SourcedAmount


class Payment(SourcedAmount):
    paid_on: CalendarDate


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


class Expense(Payment):
    category: Literal[
        "work_supplies",
        "professional_association",
        "training",
        "initial_training",
        "application",
        "account_fees",
        "other_work",
    ]
    description: Text
    payment_source: SourceLocation | None = None
    reimbursement: Payment | None = None

    @model_validator(mode="after")
    def check_reimbursement(self) -> Expense:
        if self.reimbursement and self.reimbursement.amount > self.amount:
            raise ValueError("Expense reimbursement exceeds the paid amount")
        return self


class WorkAsset(SourcedAmount):
    """The invoice amount and the documented professional share of a durable asset."""

    description: Text
    acquired_on: CalendarDate
    vat: SourcedAmount
    professional_percent: Percent
    usage_source: SourceLocation
    asset_kind: Literal["digital", "other"]
    independently_usable: StrictBool
    useful_life_years: Annotated[StrictInt, Field(ge=1, le=50)] | None = None
    useful_life_source: SourceLocation | None = None
    reimbursement: Payment | None = None

    @model_validator(mode="after")
    def check_asset(self) -> WorkAsset:
        if self.vat.amount > self.amount:
            raise ValueError("Asset VAT exceeds the gross purchase price")
        if (self.useful_life_years is None) != (self.useful_life_source is None):
            raise ValueError("Give the useful life and its source together")
        return self


class Meal(_Input):
    kind: Literal["breakfast", "lunch", "dinner"]
    own_payment: SourcedAmount | None = None
    source: SourceLocation


class TravelDay(_Input):
    day: CalendarDate
    kind: Literal["day_trip", "arrival", "full_day", "departure"]
    source: SourceLocation
    absent_minutes: Annotated[StrictInt, Field(ge=1, lt=1440)] | None = None
    regularly_at_same_workplace_since: CalendarDate | None = None
    assignment_source: SourceLocation | None = None
    employer_meals: tuple[Meal, ...] = ()

    @model_validator(mode="after")
    def check_day(self) -> TravelDay:
        if (self.kind == "day_trip") != (self.absent_minutes is not None):
            raise ValueError("Give absence minutes for day trips only")
        if (self.regularly_at_same_workplace_since is None) != (self.assignment_source is None):
            raise ValueError("Give the start of a regular assignment and its source together")
        if (
            self.regularly_at_same_workplace_since
            and self.regularly_at_same_workplace_since > self.day
        ):
            raise ValueError("Regular assignment must start on or before the travel day")
        if len({meal.kind for meal in self.employer_meals}) != len(self.employer_meals):
            raise ValueError("Record each employer-provided meal once per day")
        return self


class TravelCost(Payment):
    category: Literal["transport", "lodging", "incidentals", "reimbursement", "meal_reimbursement"]


class TravelMileage(_Input):
    day: CalendarDate
    driven_km: Distance
    vehicle: Literal["private_car", "other_private_motor_vehicle"]
    source: SourceLocation


class InsurancePayment(Payment):
    category: Literal[
        "statutory_pension",
        "professional_pension",
        "basic_private_pension",
        "statutory_health",
        "statutory_health_no_sick_pay",
        "statutory_care",
        "private_basic_health",
        "private_care",
        "unemployment",
        "disability",
        "liability_accident_term_life",
        "statutory_health_refund",
        "statutory_health_no_sick_pay_refund",
        "statutory_care_refund",
        "private_basic_health_refund",
        "private_care_refund",
    ]


class Donation(Payment):
    category: Literal["charitable_domestic", "charitable_eu_eea", "political_party", "voters_group"]
    recipient: Text


class ChurchTaxPayment(Payment):
    category: Literal["paid", "prepayment", "refunded"]


class HouseholdCost(Payment):
    category: Literal["minijob", "service", "craft"]
    description: Text
    invoice_total: SourcedAmount
    payment_source: SourceLocation
    payment_method: Literal["account", "cash", "minijob_proof"]
    household_in_eu_eea: StrictBool
    publicly_funded: StrictBool = False
    reimbursement: Payment | None = None

    @model_validator(mode="after")
    def check_amounts(self) -> HouseholdCost:
        if self.amount > self.invoice_total.amount:
            raise ValueError("Eligible costs exceed the invoice total")
        if self.reimbursement and self.reimbursement.amount > self.amount:
            raise ValueError("Household reimbursement exceeds eligible costs")
        return self


class Taxpayer(_Input):
    first_name: Text
    last_name: Text
    date_of_birth: CalendarDate
    street: Text
    house_number: Text
    postcode: Annotated[str, StringConstraints(pattern=r"^[0-9]{5}$")]
    city: Text
    tax_id: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{10}$")] | None = None
    tax_office: Text | None = None
    tax_number: Text | None = None
    iban: Annotated[str, StringConstraints(pattern=r"^DE[0-9]{20}$")] | None = None
    occupation: Text | None = None
    source: SourceLocation


class FilingProfile(_Input):
    """Facts for an estimate of a domestic, childless employee's single assessment."""

    taxpayer: Taxpayer
    case_facts: SourceLocation
    all_income_and_payments_reviewed: StrictBool
    insurance: Literal["statutory_with_sick_pay", "statutory_without_sick_pay", "private"]
    church_tax_region: Literal["none", "bavaria_baden_wuerttemberg", "other"] = "none"
    religion_code: Literal["EV", "RK"] | None = None
    household_limit_percent: Percent = Decimal(100)
    income_tax_prepayments: tuple[Payment, ...] = ()
    solidarity_prepayments: tuple[Payment, ...] = ()

    @model_validator(mode="after")
    def check_church_membership(self) -> FilingProfile:
        if (self.church_tax_region == "none") != (self.religion_code is None):
            raise ValueError("Provide the religion code and state group for church-tax members")
        return self


class EmployeeCase(_Input):
    """Confirmed facts for one taxpayer and one assessment year."""

    schema_version: Annotated[StrictInt, Field(ge=1, le=1)]
    tax_year: StrictInt
    reviewed_standard_case: StrictBool
    documents: dict[DocumentId, SourceDocument]
    wage_certificates: Annotated[tuple[WageCertificate, ...], Field(min_length=1)]
    commute: Commute | None = None
    workdays: tuple[Workday, ...] = ()
    expenses: tuple[Expense, ...] = ()
    work_assets: tuple[WorkAsset, ...] = ()
    travel_days: tuple[TravelDay, ...] = ()
    travel_costs: tuple[TravelCost, ...] = ()
    travel_mileage: tuple[TravelMileage, ...] = ()
    insurance_payments: tuple[InsurancePayment, ...] = ()
    donations: tuple[Donation, ...] = ()
    donation_carryforward: SourcedAmount | None = None
    church_tax_payments: tuple[ChurchTaxPayment, ...] = ()
    household_costs: tuple[HouseholdCost, ...] = ()
    filing: FilingProfile | None = None
    intake: Intake2025 | None = None

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
        self._validate_claims()
        if self.filing:
            self._validate_filing()
        return self

    def _validate_claims(self) -> None:
        payments = [
            *self.expenses,
            *self.travel_costs,
            *self.insurance_payments,
            *self.donations,
            *self.church_tax_payments,
            *self.household_costs,
        ]
        for claim in (*self.expenses, *self.work_assets, *self.household_costs):
            if claim.reimbursement:
                payments.append(claim.reimbursement)
        if self.filing:
            payments.extend(self.filing.income_tax_prepayments + self.filing.solidarity_prepayments)
        if any(item.paid_on.year != self.tax_year for item in payments):
            raise ValueError("Payment dates must be in the assessment year")
        if any(asset.acquired_on.year > self.tax_year for asset in self.work_assets):
            raise ValueError("Work assets must be acquired by the end of the assessment year")
        if any(
            entry.day.year != self.tax_year for entry in (*self.travel_days, *self.travel_mileage)
        ):
            raise ValueError("Travel dates must be in the assessment year")
        if len({entry.day for entry in self.travel_days}) != len(self.travel_days):
            raise ValueError("Enter one combined meal allowance record per travel day")
        full_travel_days = {entry.day for entry in self.travel_days if entry.kind == "full_day"}
        if any(
            day.day in full_travel_days
            and (day.attended_first_workplace or day.home_work != "none")
            for day in self.workdays
        ):
            raise ValueError("A 24-hour absence cannot overlap with home or first-workplace work")
        invoice_pages = Counter((item.source.document, item.source.page) for item in self.expenses)
        if any(
            item.payment_source and invoice_pages[item.source.document, item.source.page] > 1
            for item in self.expenses
        ):
            raise ValueError("An invoice matched to a payment can be claimed only once")
        claim_sources = [
            entry.source for entry in (*payments, *self.work_assets, *self.travel_mileage)
        ]
        claim_sources.extend(
            expense.payment_source
            for expense in self.expenses
            if expense.payment_source is not None and expense.payment_source != expense.source
        )
        if self.commute:
            claim_sources.extend(cost.source for cost in self.commute.public_transport_costs)
        if len(set(claim_sources)) != len(claim_sources):
            raise ValueError("A source position can be claimed only once")

    def _validate_filing(self) -> None:
        filing = self.filing
        if filing is None:
            return
        if not filing.all_income_and_payments_reviewed:
            raise ValueError(
                "Confirm all wage statements, insurance contributions and payments before estimating"
            )
        if filing.taxpayer.date_of_birth > date(self.tax_year, 12, 31):
            raise ValueError("Birth date must be before the end of the assessment year")
        positions = {
            key
            for certificate in self.wage_certificates
            for key, value in certificate.amounts.items()
            if value
        }
        if filing.insurance == "private":
            if positions.intersection({"24a", "24c", "25", "26"}):
                raise ValueError(
                    "Contributions to both private and statutory health insurance need separate assessment"
                )
            if not any(
                payment.category in {"private_basic_health", "private_care"}
                for payment in self.insurance_payments
            ):
                raise ValueError(
                    "Provide actual private basic health and care insurance contributions"
                )
        elif "24b" in positions:
            raise ValueError("Review the private health insurance subsidy on the wage certificate")
