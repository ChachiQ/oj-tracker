"""
Core statistics engine for computing student metrics.

Provides all the statistical computations needed for dashboards, reports,
radar charts, heatmaps, and other analytical views.
"""

import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from app.extensions import db
from app.models import Student, Submission, Problem, Tag, PlatformAccount


class AnalysisEngine:
    """Core statistics engine for computing student metrics.

    Lazily loads all submissions for a given student and provides
    various statistical aggregations over them.

    Args:
        student_id: Database ID of the student to analyze.
    """

    def __init__(self, student_id: int):
        self.student_id = student_id
        self._submissions = None

    @property
    def submissions(self):
        """Lazy-loaded list of all submissions for this student, newest first."""
        if self._submissions is None:
            account_ids = [
                a.id
                for a in PlatformAccount.query.filter_by(
                    student_id=self.student_id
                ).all()
            ]
            if account_ids:
                self._submissions = (
                    Submission.query.filter(
                        Submission.platform_account_id.in_(account_ids)
                    )
                    .order_by(Submission.submitted_at.desc())
                    .all()
                )
            else:
                self._submissions = []
        return self._submissions

    def get_basic_stats(self) -> dict:
        """Get basic statistics: total problems, AC count, pass rate, etc.

        Returns:
            Dict with keys: total_submissions, ac_submissions, unique_attempted,
            unique_solved, pass_rate.
        """
        total = len(self.submissions)
        ac_submissions = [s for s in self.submissions if s.status == "AC"]
        unique_problems_attempted = len(
            set(
                (s.platform_account_id, s.problem_id_ref)
                for s in self.submissions
                if s.problem_id_ref
            )
        )
        unique_problems_solved = len(
            set(
                (s.platform_account_id, s.problem_id_ref)
                for s in ac_submissions
                if s.problem_id_ref
            )
        )

        return {
            "total_submissions": total,
            "ac_submissions": len(ac_submissions),
            "unique_attempted": unique_problems_attempted,
            "unique_solved": unique_problems_solved,
            "pass_rate": (
                round(len(ac_submissions) / total * 100, 1) if total > 0 else 0
            ),
        }

    def get_weekly_stats(self, weeks: int = 1) -> dict:
        """Stats for the last N weeks.

        Args:
            weeks: Number of weeks to look back.

        Returns:
            Dict with keys: submissions, ac_count, unique_solved, active_days, pass_rate.
        """
        since = datetime.utcnow() - timedelta(weeks=weeks)
        recent = [
            s for s in self.submissions if s.submitted_at and s.submitted_at >= since
        ]
        ac_recent = [s for s in recent if s.status == "AC"]
        unique_solved = len(
            set(s.problem_id_ref for s in ac_recent if s.problem_id_ref)
        )
        active_days = len(
            set(s.submitted_at.date() for s in recent if s.submitted_at)
        )

        return {
            "submissions": len(recent),
            "ac_count": len(ac_recent),
            "unique_solved": unique_solved,
            "active_days": active_days,
            "pass_rate": (
                round(len(ac_recent) / len(recent) * 100, 1) if recent else 0
            ),
        }

    def get_streak_days(self) -> int:
        """Calculate consecutive active days ending today (or yesterday).

        Returns:
            Number of consecutive days with at least one submission.
        """
        if not self.submissions:
            return 0

        dates = sorted(
            set(
                s.submitted_at.date()
                for s in self.submissions
                if s.submitted_at
            ),
            reverse=True,
        )
        if not dates:
            return 0

        streak = 0
        today = datetime.utcnow().date()
        expected = today

        for d in dates:
            if d == expected:
                streak += 1
                expected = d - timedelta(days=1)
            elif d < expected:
                break

        return streak

    def get_status_distribution(self) -> dict:
        """Distribution of submission statuses.

        Returns:
            Dict mapping status string to count (e.g. {'AC': 50, 'WA': 20, ...}).
        """
        counter = Counter(s.status for s in self.submissions)
        return dict(counter)

    def get_difficulty_distribution(self) -> dict:
        """Distribution of solved problems by difficulty.

        Returns:
            Dict mapping difficulty level to count, sorted by difficulty.
        """
        ac_problem_ids = set(
            s.problem_id_ref
            for s in self.submissions
            if s.status == "AC" and s.problem_id_ref
        )
        if not ac_problem_ids:
            return {}

        problems = Problem.query.filter(Problem.id.in_(ac_problem_ids)).all()
        counter = Counter(p.difficulty for p in problems)
        return dict(sorted(counter.items()))

    def get_daily_submissions(self, days: int = 365) -> list:
        """Daily submission counts for heatmap visualization.

        Args:
            days: Number of days to look back.

        Returns:
            List of dicts with 'date' (YYYY-MM-DD) and 'count' keys, sorted by date.
        """
        since = datetime.utcnow() - timedelta(days=days)
        recent = [
            s for s in self.submissions if s.submitted_at and s.submitted_at >= since
        ]
        daily = Counter(s.submitted_at.strftime("%Y-%m-%d") for s in recent)
        return [{"date": k, "count": v} for k, v in sorted(daily.items())]

    def get_tag_scores(self) -> dict:
        """Calculate ability scores per tag/knowledge point for radar chart.

        Score formula (weighted 0-100):
            - pass_count_weight * 20: How many problems solved with this tag
            - pass_rate_weight * 25: AC rate for problems with this tag
            - difficulty_weight * 30: Max difficulty solved
            - first_ac_rate * 15: Rate of first-attempt ACs
            - avg_attempts * 10: Efficiency (fewer attempts = higher score)

        Returns:
            Dict mapping tag_name to dict with keys: score, display_name, stage,
            solved, attempted, pass_rate, first_ac_rate, avg_attempts.
        """
        # Group submissions by problem
        problem_submissions = defaultdict(list)
        for s in self.submissions:
            if s.problem_id_ref:
                problem_submissions[s.problem_id_ref].append(s)

        tag_stats = defaultdict(
            lambda: {
                "solved": 0,
                "attempted": 0,
                "total_subs": 0,
                "ac_subs": 0,
                "first_ac": 0,
                "total_attempts_to_ac": 0,
                "ac_problems": 0,
                "max_difficulty": 0,
            }
        )

        for prob_id, subs in problem_submissions.items():
            problem = Problem.query.get(prob_id)
            if not problem:
                continue
            tags = problem.tags
            if not tags:
                continue

            subs_sorted = sorted(
                subs,
                key=lambda x: x.submitted_at if x.submitted_at else datetime.min,
            )
            has_ac = any(s.status == "AC" for s in subs_sorted)
            first_is_ac = subs_sorted[0].status == "AC" if subs_sorted else False
            attempts_to_ac = 0
            if has_ac:
                for i, s in enumerate(subs_sorted):
                    if s.status == "AC":
                        attempts_to_ac = i + 1
                        break

            for tag in tags:
                stats = tag_stats[tag.name]
                stats["attempted"] += 1
                stats["total_subs"] += len(subs)
                stats["ac_subs"] += sum(1 for s in subs if s.status == "AC")
                if has_ac:
                    stats["solved"] += 1
                    stats["ac_problems"] += 1
                    stats["total_attempts_to_ac"] += attempts_to_ac
                    if first_is_ac:
                        stats["first_ac"] += 1
                    stats["max_difficulty"] = max(
                        stats["max_difficulty"], problem.difficulty or 0
                    )

        result = {}
        for tag_name, stats in tag_stats.items():
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                continue

            attempted = stats["attempted"]
            solved = stats["solved"]
            pass_rate = solved / attempted if attempted > 0 else 0
            first_ac_rate = (
                stats["first_ac"] / stats["ac_problems"]
                if stats["ac_problems"] > 0
                else 0
            )
            avg_attempts = (
                stats["total_attempts_to_ac"] / stats["ac_problems"]
                if stats["ac_problems"] > 0
                else 0
            )

            # Normalize individual component scores to 0-100
            count_score = min(solved * 10, 100)  # Cap at 10 problems
            rate_score = pass_rate * 100
            diff_score = min(stats["max_difficulty"] * 10, 100)
            first_score = first_ac_rate * 100
            attempt_score = (
                max(0, 100 - (avg_attempts - 1) * 20) if avg_attempts > 0 else 0
            )

            # Weighted total
            total_score = (
                count_score * 0.20
                + rate_score * 0.25
                + diff_score * 0.30
                + first_score * 0.15
                + attempt_score * 0.10
            )

            result[tag_name] = {
                "score": round(total_score),
                "display_name": tag.display_name,
                "stage": tag.stage,
                "solved": solved,
                "attempted": attempted,
                "pass_rate": round(pass_rate * 100, 1),
                "first_ac_rate": round(first_ac_rate * 100, 1),
                "avg_attempts": round(avg_attempts, 1),
            }

        return result

    def get_heatmap_data(self, days: int = 365) -> list:
        """Alias for get_daily_submissions, for calendar heatmap views.

        Args:
            days: Number of days to look back.

        Returns:
            List of dicts with 'date' and 'count' keys.
        """
        return self.get_daily_submissions(days)

    def get_first_ac_rate(self) -> float:
        """Overall first-attempt AC rate across all attempted problems.

        Returns:
            Percentage (0-100) of problems solved on the first attempt.
        """
        problem_submissions = defaultdict(list)
        for s in self.submissions:
            if s.problem_id_ref:
                problem_submissions[s.problem_id_ref].append(s)

        first_ac = 0
        total_attempted = 0
        for prob_id, subs in problem_submissions.items():
            subs_sorted = sorted(
                subs,
                key=lambda x: x.submitted_at if x.submitted_at else datetime.min,
            )
            if subs_sorted:
                total_attempted += 1
                if subs_sorted[0].status == "AC":
                    first_ac += 1

        return round(first_ac / total_attempted * 100, 1) if total_attempted > 0 else 0
