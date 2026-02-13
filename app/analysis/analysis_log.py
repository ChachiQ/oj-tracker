"""
Analysis log manager.

Manages the creation and retrieval of periodic analysis logs, which store
structured summaries of AI analysis results for use in report generation
and cross-period comparisons.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from app.extensions import db
from app.models import AnalysisLog, Student

logger = logging.getLogger(__name__)


class AnalysisLogManager:
    """Manages analysis logs for a student.

    Analysis logs store periodic summaries (weekly/monthly) of AI analysis
    results, key findings, error patterns, and improvement notes. They serve
    as the bridge between individual submission analyses and periodic reports.

    Args:
        student_id: Database ID of the student.
    """

    def __init__(self, student_id: int):
        self.student_id = student_id

    def get_latest_log(self, log_type: str = "weekly") -> AnalysisLog | None:
        """Get the most recent analysis log of a given type.

        Args:
            log_type: 'weekly' or 'monthly'.

        Returns:
            The most recent AnalysisLog instance, or None if none exist.
        """
        return (
            AnalysisLog.query.filter_by(
                student_id=self.student_id, log_type=log_type
            )
            .order_by(AnalysisLog.period_end.desc())
            .first()
        )

    def create_log(
        self,
        log_type: str,
        period_start: datetime,
        period_end: datetime,
        content: str,
        key_findings: list = None,
        error_pattern_stats: dict = None,
        improvement_notes: str = None,
    ) -> AnalysisLog:
        """Create and persist a new analysis log entry.

        Args:
            log_type: 'weekly' or 'monthly'.
            period_start: Start of the analysis period.
            period_end: End of the analysis period.
            content: Full text content of the analysis summary.
            key_findings: List of key finding strings.
            error_pattern_stats: Dict of error pattern name to count.
            improvement_notes: Free-form improvement notes.

        Returns:
            The newly created AnalysisLog instance.
        """
        log = AnalysisLog(
            student_id=self.student_id,
            log_type=log_type,
            period_start=period_start,
            period_end=period_end,
            content=content,
            key_findings=json.dumps(key_findings or [], ensure_ascii=False),
            error_pattern_stats=json.dumps(
                error_pattern_stats or {}, ensure_ascii=False
            ),
            improvement_notes=improvement_notes,
        )
        db.session.add(log)
        db.session.commit()
        return log

    def get_logs_for_period(
        self, start: datetime, end: datetime
    ) -> list[AnalysisLog]:
        """Get all analysis logs within a date range.

        Args:
            start: Start of the date range (inclusive).
            end: End of the date range (inclusive).

        Returns:
            List of AnalysisLog instances ordered by period_start.
        """
        return (
            AnalysisLog.query.filter(
                AnalysisLog.student_id == self.student_id,
                AnalysisLog.period_start >= start,
                AnalysisLog.period_end <= end,
            )
            .order_by(AnalysisLog.period_start)
            .all()
        )
