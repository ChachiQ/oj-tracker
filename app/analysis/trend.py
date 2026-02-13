"""
Trend analysis for student performance over time.

Computes weekly and monthly aggregated metrics including submission counts,
AC counts, unique problems, and pass rates for charting and comparison.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from collections import defaultdict

from app.models import Submission, PlatformAccount


class TrendAnalyzer:
    """Analyzes performance trends over time for a student.

    Args:
        student_id: Database ID of the student to analyze.
    """

    def __init__(self, student_id: int):
        self.student_id = student_id

    def _get_account_ids(self) -> list[int]:
        """Get all platform account IDs for this student."""
        return [
            a.id
            for a in PlatformAccount.query.filter_by(
                student_id=self.student_id
            ).all()
        ]

    def get_weekly_trend(self, weeks: int = 12) -> list[dict]:
        """Get weekly submission and AC trends for the last N weeks.

        Args:
            weeks: Number of weeks to look back.

        Returns:
            List of dicts sorted by week, each with keys:
                - week: ISO week string (e.g. '2025-W03')
                - submissions: Total submission count
                - ac_count: Number of AC submissions
                - unique_problems: Number of distinct problems attempted
                - pass_rate: AC percentage
        """
        account_ids = self._get_account_ids()
        if not account_ids:
            return []

        since = datetime.utcnow() - timedelta(weeks=weeks)
        submissions = (
            Submission.query.filter(
                Submission.platform_account_id.in_(account_ids),
                Submission.submitted_at >= since,
            )
            .all()
        )

        weekly = defaultdict(lambda: {"total": 0, "ac": 0, "problems": set()})
        for s in submissions:
            if s.submitted_at:
                week_key = s.submitted_at.strftime("%Y-W%W")
                weekly[week_key]["total"] += 1
                if s.status == "AC":
                    weekly[week_key]["ac"] += 1
                if s.problem_id_ref:
                    weekly[week_key]["problems"].add(s.problem_id_ref)

        result = []
        for week, stats in sorted(weekly.items()):
            result.append(
                {
                    "week": week,
                    "submissions": stats["total"],
                    "ac_count": stats["ac"],
                    "unique_problems": len(stats["problems"]),
                    "pass_rate": (
                        round(stats["ac"] / stats["total"] * 100, 1)
                        if stats["total"] > 0
                        else 0
                    ),
                }
            )
        return result

    def get_monthly_trend(self, months: int = 6) -> list[dict]:
        """Get monthly submission and AC trends.

        Args:
            months: Number of months to look back (approximate, using 30-day periods).

        Returns:
            List of dicts sorted by month, each with keys:
                - month: Month string (e.g. '2025-01')
                - submissions: Total submission count
                - ac_count: Number of AC submissions
                - unique_problems: Number of distinct problems attempted
                - pass_rate: AC percentage
        """
        account_ids = self._get_account_ids()
        if not account_ids:
            return []

        since = datetime.utcnow() - timedelta(days=months * 30)
        submissions = (
            Submission.query.filter(
                Submission.platform_account_id.in_(account_ids),
                Submission.submitted_at >= since,
            )
            .all()
        )

        monthly = defaultdict(lambda: {"total": 0, "ac": 0, "problems": set()})
        for s in submissions:
            if s.submitted_at:
                month_key = s.submitted_at.strftime("%Y-%m")
                monthly[month_key]["total"] += 1
                if s.status == "AC":
                    monthly[month_key]["ac"] += 1
                if s.problem_id_ref:
                    monthly[month_key]["problems"].add(s.problem_id_ref)

        result = []
        for month, stats in sorted(monthly.items()):
            result.append(
                {
                    "month": month,
                    "submissions": stats["total"],
                    "ac_count": stats["ac"],
                    "unique_problems": len(stats["problems"]),
                    "pass_rate": (
                        round(stats["ac"] / stats["total"] * 100, 1)
                        if stats["total"] > 0
                        else 0
                    ),
                }
            )
        return result
