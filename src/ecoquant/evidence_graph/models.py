from dataclasses import dataclass
from datetime import date
from typing import TypeAlias


@dataclass(frozen=True)
class Issuer:
    id: str
    valid_time: date
    source_time: date
    name: str = ""


@dataclass(frozen=True)
class Bond:
    id: str
    valid_time: date
    source_time: date
    issuer_id: str = ""


@dataclass(frozen=True)
class Document:
    id: str
    valid_time: date
    source_time: date | None
    issuer_id: str = ""


@dataclass(frozen=True)
class Claim:
    id: str
    subject_id: str
    metric_id: str
    value: str | int | float | bool
    checked: bool
    provenance: str
    valid_time: date
    source_time: date
    supersedes_id: str | None = None


@dataclass(frozen=True)
class Event:
    id: str
    valid_time: date
    source_time: date
    event_type: str = ""


@dataclass(frozen=True)
class Metric:
    id: str
    valid_time: date
    source_time: date
    name: str = ""


@dataclass(frozen=True)
class RiskDriver:
    id: str
    valid_time: date
    source_time: date
    name: str = ""


GraphNode: TypeAlias = Issuer | Bond | Document | Claim | Event | Metric | RiskDriver


NODE_TYPES = (Issuer, Bond, Document, Claim, Event, Metric, RiskDriver)
