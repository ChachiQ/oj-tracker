"""
Weakness detection engine.

Identifies knowledge gaps and weak areas for a student by comparing their
tag-level performance against stage-appropriate expectations. Weaknesses are
categorized by severity (critical, moderate, mild) and include actionable
improvement suggestions.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from app.models import Tag, Problem, Submission, PlatformAccount, Student
from .engine import AnalysisEngine

logger = logging.getLogger(__name__)

# Expected ability scores by learning stage (1-6).
# Higher stages naturally have lower expectations since the material is harder.
STAGE_EXPECTATIONS = {
    1: 70,  # Stage 1: Syntax basics
    2: 60,  # Stage 2: Basic algorithms
    3: 50,  # Stage 3: CSP-J level
    4: 40,  # Stage 4: CSP-S level
    5: 30,  # Stage 5: Provincial selection
    6: 20,  # Stage 6: NOI level
}

# Mapping of grade level to maximum accessible stage.
# Students should not be expected to master content above their grade's stage.
GRADE_STAGE_MAP = {
    "小三": 1,
    "小四": 1,
    "小五": 2,
    "小六": 2,
    "初一": 3,
    "初二": 3,
    "初三": 4,
    "高一": 4,
    "高二": 5,
    "高三": 6,
}


class WeaknessDetector:
    """Detects knowledge weaknesses for a student.

    Compares actual tag scores against stage-appropriate expectations
    to identify areas needing improvement.

    Args:
        student_id: Database ID of the student to analyze.
    """

    def __init__(self, student_id: int):
        self.student_id = student_id
        self.engine = AnalysisEngine(student_id)
        self.student = Student.query.get(student_id)

    def detect(self) -> list[dict]:
        """Detect weaknesses, return list sorted by severity.

        Returns:
            List of weakness dicts sorted by severity (critical first), each with keys:
                - tag_name, display_name, stage, category
                - severity: 'critical', 'moderate', or 'mild'
                - reason: Human-readable explanation
                - score: Current ability score (0-100)
                - expected: Expected score for this stage
                - suggestion: Improvement recommendation
                - pass_rate, attempted, solved (when applicable)
        """
        tag_scores = self.engine.get_tag_scores()
        max_stage = self._get_max_stage()
        weaknesses = []

        # Check all tags in accessible stages
        all_tags = Tag.query.filter(Tag.stage <= max_stage).all()

        for tag in all_tags:
            stats = tag_scores.get(tag.name)
            expected = STAGE_EXPECTATIONS.get(tag.stage, 50)

            if stats is None:
                # Tag not attempted at all -- mild weakness (unknown skill)
                weaknesses.append(
                    {
                        "tag_name": tag.name,
                        "display_name": tag.display_name,
                        "stage": tag.stage,
                        "category": tag.category,
                        "severity": "mild",
                        "reason": "未涉及",
                        "score": 0,
                        "expected": expected,
                        "suggestion": f"建议开始练习{tag.display_name}相关题目",
                    }
                )
            elif stats["score"] < expected * 0.6:
                # Score below 60% of expectation -- moderate or critical
                severity = (
                    "critical" if stats["score"] < expected * 0.3 else "moderate"
                )
                weaknesses.append(
                    {
                        "tag_name": tag.name,
                        "display_name": tag.display_name,
                        "stage": tag.stage,
                        "category": tag.category,
                        "severity": severity,
                        "reason": (
                            f"通过率{stats['pass_rate']}%，"
                            f"能力评分{stats['score']}低于期望{expected}"
                        ),
                        "score": stats["score"],
                        "expected": expected,
                        "pass_rate": stats["pass_rate"],
                        "attempted": stats["attempted"],
                        "solved": stats["solved"],
                        "suggestion": (
                            f"建议加强{tag.display_name}训练，"
                            f"当前通过率{stats['pass_rate']}%"
                        ),
                    }
                )

        # Sort: critical first, then moderate, then mild; within same severity, lower score first
        severity_order = {"critical": 0, "moderate": 1, "mild": 2}
        weaknesses.sort(
            key=lambda x: (severity_order.get(x["severity"], 3), -x.get("score", 0))
        )

        return weaknesses

    def _get_max_stage(self) -> int:
        """Determine the maximum stage accessible for this student's grade.

        Returns:
            Stage number (1-6). Defaults to 4 (CSP-S) if grade is unknown.
        """
        if self.student and self.student.grade:
            return GRADE_STAGE_MAP.get(self.student.grade, 4)
        return 4  # Default to CSP-S level

    def get_critical_weaknesses(self) -> list[dict]:
        """Get only critical-severity weaknesses.

        Returns:
            Filtered list of weakness dicts with severity == 'critical'.
        """
        return [w for w in self.detect() if w["severity"] == "critical"]
