"""
Problem recommender.

Recommends practice problems to students based on their detected weaknesses,
current skill level, and learning stage. Prioritizes critical weaknesses,
then moderate weaknesses, then unexplored knowledge areas.
"""
from __future__ import annotations

from app.models import Problem, Tag, Submission, PlatformAccount, Student
from .weakness import WeaknessDetector, GRADE_STAGE_MAP
from collections import defaultdict


class ProblemRecommender:
    """Recommends problems based on student weaknesses and progression.

    Args:
        student_id: Database ID of the student to recommend for.
    """

    def __init__(self, student_id: int):
        self.student_id = student_id
        self.student = Student.query.get(student_id)
        self.weakness_detector = WeaknessDetector(student_id)

    def recommend(self, limit: int = 10) -> list[dict]:
        """Generate problem recommendations.

        Strategy:
            1. Priority 1 (critical weaknesses): Problems for tags with critical severity
            2. Priority 2 (moderate weaknesses): Problems for tags with moderate severity
            3. Priority 3 (unexplored topics): Problems for tags not yet attempted

        Problems already solved by the student are excluded. Difficulty is
        calibrated around the student's current level.

        Args:
            limit: Maximum number of recommendations to return.

        Returns:
            List of dicts sorted by priority, each with keys:
                - problem: Problem model instance
                - reason: Human-readable recommendation reason
                - priority: Numeric priority (1 = highest)
                - tag: Display name of the relevant tag
        """
        weaknesses = self.weakness_detector.detect()
        max_stage = self._get_max_stage()

        # Get already solved problem IDs
        account_ids = [
            a.id
            for a in PlatformAccount.query.filter_by(
                student_id=self.student_id
            ).all()
        ]
        solved_ids = set()
        if account_ids:
            for sub in Submission.query.filter(
                Submission.platform_account_id.in_(account_ids),
                Submission.status == "AC",
            ).all():
                if sub.problem_id_ref:
                    solved_ids.add(sub.problem_id_ref)

        # Determine current max difficulty the student has solved
        max_diff = 0
        for pid in solved_ids:
            p = Problem.query.get(pid)
            if p and p.difficulty:
                max_diff = max(max_diff, p.difficulty)

        recommendations = []
        seen_problem_ids = set()

        # Priority 1 & 2: Problems for critical and moderate weaknesses
        for weakness in weaknesses[:5]:
            if weakness["severity"] in ("critical", "moderate"):
                tag = Tag.query.filter_by(name=weakness["tag_name"]).first()
                if not tag:
                    continue

                problems = (
                    Problem.query.filter(
                        Problem.tags.any(Tag.id == tag.id),
                        Problem.difficulty.between(
                            max(1, max_diff - 1), max_diff + 1
                        ),
                        ~Problem.id.in_(solved_ids | seen_problem_ids),
                    )
                    .limit(3)
                    .all()
                )

                for p in problems:
                    seen_problem_ids.add(p.id)
                    recommendations.append(
                        {
                            "problem": p,
                            "reason": (
                                f"加强{tag.display_name}训练 "
                                f"({weakness['severity']}弱项)"
                            ),
                            "priority": (
                                1 if weakness["severity"] == "critical" else 2
                            ),
                            "tag": tag.display_name,
                        }
                    )

        # Priority 3: Problems for unexplored tags in current stage
        for weakness in weaknesses:
            if weakness["reason"] == "未涉及" and weakness["stage"] <= max_stage:
                tag = Tag.query.filter_by(name=weakness["tag_name"]).first()
                if not tag:
                    continue

                problems = (
                    Problem.query.filter(
                        Problem.tags.any(Tag.id == tag.id),
                        Problem.difficulty.between(1, max(3, max_diff - 1)),
                        ~Problem.id.in_(solved_ids | seen_problem_ids),
                    )
                    .limit(2)
                    .all()
                )

                for p in problems:
                    seen_problem_ids.add(p.id)
                    recommendations.append(
                        {
                            "problem": p,
                            "reason": f"探索新知识点：{tag.display_name}",
                            "priority": 3,
                            "tag": tag.display_name,
                        }
                    )

        # Sort by priority and limit
        recommendations.sort(key=lambda x: x["priority"])
        return recommendations[:limit]

    def _get_max_stage(self) -> int:
        """Determine the maximum stage for this student's grade.

        Returns:
            Stage number (1-6). Defaults to 4 (CSP-S) if grade is unknown.
        """
        if self.student and self.student.grade:
            return GRADE_STAGE_MAP.get(self.student.grade, 4)
        return 4
