from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SubmissionStatus(str, Enum):
    AC = 'AC'
    WA = 'WA'
    TLE = 'TLE'
    MLE = 'MLE'
    RE = 'RE'
    CE = 'CE'
    UNKNOWN = 'UNKNOWN'
    PENDING = 'PENDING'
    JUDGING = 'JUDGING'


@dataclass
class ScrapedSubmission:
    platform_record_id: str
    problem_id: str
    status: str
    score: int | None = None
    language: str | None = None
    time_ms: int | None = None
    memory_kb: int | None = None
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    source_code: str | None = None


@dataclass
class ScrapedProblem:
    problem_id: str
    title: str
    difficulty_raw: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str | None = None
    url: str = ''
    description: str | None = None
    input_desc: str | None = None
    output_desc: str | None = None
    examples: str | None = None
    hint: str | None = None
