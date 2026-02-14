"""
AI analysis orchestrator.

Coordinates LLM providers with prompt templates to perform AI-powered
analysis of student submissions and problem-solving journeys.
Includes budget management to prevent runaway API costs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import (
    Submission,
    Problem,
    AnalysisResult,
    Student,
    PlatformAccount,
)
from .llm import get_provider
from .prompts.single_submission import build_single_submission_prompt
from .prompts.problem_journey import build_problem_journey_prompt

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Orchestrates AI analysis of submissions and problem journeys.

    Manages LLM provider selection, budget checking, and result persistence.

    Args:
        app: Flask application instance. If None, uses current_app.
    """

    def __init__(self, app=None):
        self.app = app or current_app._get_current_object()

    def _get_llm(self, tier: str = "basic", user_id: int = None):
        """Get an LLM provider and model based on the configured tier.

        When *user_id* is given the method first looks for per-user overrides
        stored in ``UserSetting`` (ai_provider, api_key_*).  Falls back to
        ``app.config`` / environment variables when no user config exists.

        Args:
            tier: 'basic' for cheaper/faster models, 'advanced' for more capable ones.
            user_id: Optional user id to load per-user AI configuration.

        Returns:
            Tuple of (provider_instance, model_name).
        """
        from .llm.config import MODEL_CONFIG

        # Determine provider name and API key
        user_key_map = {
            "claude": "api_key_claude",
            "openai": "api_key_openai",
            "zhipu": "api_key_zhipu",
        }
        env_key_map = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
        }

        if user_id:
            from app.models import UserSetting
            provider_name = (
                UserSetting.get(user_id, 'ai_provider')
                or self.app.config.get("AI_PROVIDER", "zhipu")
            )
            api_key = UserSetting.get(
                user_id, user_key_map.get(provider_name, ''),
            ) or ''
        else:
            provider_name = self.app.config.get("AI_PROVIDER", "claude")
            api_key = ''

        # Fall back to environment variable / app config
        if not api_key:
            api_key = self.app.config.get(
                env_key_map.get(provider_name, ""), "",
            )

        provider = get_provider(provider_name, api_key=api_key)

        # Pick the right model for the requested tier
        models = MODEL_CONFIG.get(provider_name, {}).get("models", {})
        target_tier = "basic" if tier == "basic" else "advanced"
        model = None
        for m_name, m_info in models.items():
            if m_info.get("tier") == target_tier:
                model = m_name
                break

        # Final fallback to explicit config keys
        if not model:
            model_key = "AI_MODEL_BASIC" if tier == "basic" else "AI_MODEL_ADVANCED"
            model = self.app.config.get(model_key)

        return provider, model

    def _check_budget(self) -> bool:
        """Check if AI spending is within the monthly budget.

        Returns:
            True if budget has not been exceeded, False otherwise.
        """
        from sqlalchemy import func

        month_start = datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        total_cost = (
            db.session.query(func.sum(AnalysisResult.cost_usd))
            .filter(AnalysisResult.analyzed_at >= month_start)
            .scalar()
            or 0
        )
        budget = self.app.config.get("AI_MONTHLY_BUDGET", 5.0)
        return total_cost < budget

    def analyze_submission(self, submission_id: int) -> AnalysisResult | None:
        """Level 1: Analyze a single submission with AI.

        Checks for existing analysis, budget limits, and required data before
        making an API call. Results are persisted to the database.

        Args:
            submission_id: Database ID of the submission to analyze.

        Returns:
            AnalysisResult instance, or None if analysis cannot be performed.
        """
        # Check for existing analysis
        existing = AnalysisResult.query.filter_by(
            submission_id=submission_id, analysis_type="single_submission"
        ).first()
        if existing:
            return existing

        # Check budget
        if not self._check_budget():
            logger.warning("AI monthly budget exceeded, skipping analysis")
            return None

        # Load submission data
        submission = Submission.query.get(submission_id)
        if not submission or not submission.source_code:
            return None

        problem = submission.problem
        student = (
            submission.platform_account.student
            if submission.platform_account
            else None
        )

        # Build prompt
        messages = build_single_submission_prompt(
            problem_title=problem.title if problem else "Unknown",
            problem_description=problem.description if problem else None,
            source_code=submission.source_code,
            status=submission.status,
            score=submission.score,
            student_age=student.age if student else None,
            student_grade=student.grade if student else None,
        )

        try:
            # Resolve the owning user for per-user AI config
            user_id = None
            if student and hasattr(student, 'parent_id'):
                user_id = student.parent_id

            provider, model = self._get_llm("basic", user_id=user_id)
            response = provider.chat(messages, model=model)

            result = AnalysisResult(
                submission_id=submission_id,
                analysis_type="single_submission",
                result_json=response.content,
                ai_model=response.model,
                token_cost=response.input_tokens + response.output_tokens,
                cost_usd=response.cost,
                analyzed_at=datetime.utcnow(),
            )

            # Try to parse JSON and extract structured fields
            try:
                parsed = json.loads(response.content)
                result.summary = parsed.get("error_description", "")
                result.error_patterns = json.dumps(
                    [parsed.get("error_type", "")], ensure_ascii=False
                )
                result.suggestions = parsed.get("suggestion", "")
            except json.JSONDecodeError:
                result.summary = response.content[:500]

            db.session.add(result)
            db.session.commit()
            return result

        except Exception as e:
            logger.error(f"AI analysis failed for submission {submission_id}: {e}")
            return None

    def analyze_problem_journey(
        self, problem_db_id: int, student_id: int
    ) -> AnalysisResult | None:
        """Level 2: Analyze the full journey from WA to AC for a problem.

        Gathers all submissions for a problem by the student, builds a timeline,
        and sends it to the LLM for comprehensive analysis.

        Args:
            problem_db_id: Database ID of the problem.
            student_id: Database ID of the student.

        Returns:
            AnalysisResult instance, or None if analysis cannot be performed.
        """
        # Find all submissions for this problem by this student
        account_ids = [
            a.id
            for a in PlatformAccount.query.filter_by(student_id=student_id).all()
        ]
        if not account_ids:
            return None

        submissions = (
            Submission.query.filter(
                Submission.platform_account_id.in_(account_ids),
                Submission.problem_id_ref == problem_db_id,
            )
            .order_by(Submission.submitted_at)
            .all()
        )

        # Need at least one submission with an AC
        if not submissions or not any(s.status == "AC" for s in submissions):
            return None

        # Check if already analyzed (keyed on the last submission)
        existing = AnalysisResult.query.filter_by(
            submission_id=submissions[-1].id, analysis_type="problem_journey"
        ).first()
        if existing:
            return existing

        if not self._check_budget():
            logger.warning("AI monthly budget exceeded, skipping journey analysis")
            return None

        problem = Problem.query.get(problem_db_id)
        student = Student.query.get(student_id)

        # Build submission timeline
        timeline = []
        for i, sub in enumerate(submissions):
            timeline.append(
                {
                    "attempt_number": i + 1,
                    "status": sub.status,
                    "score": sub.score,
                    "source_code": sub.source_code,
                    "submitted_at": (
                        sub.submitted_at.strftime("%Y-%m-%d %H:%M")
                        if sub.submitted_at
                        else ""
                    ),
                }
            )

        messages = build_problem_journey_prompt(
            problem_title=problem.title if problem else "Unknown",
            problem_description=problem.description if problem else None,
            submissions_timeline=timeline,
            student_age=student.age if student else None,
            student_grade=student.grade if student else None,
        )

        try:
            user_id = student.parent_id if student else None
            provider, model = self._get_llm("basic", user_id=user_id)
            response = provider.chat(messages, model=model, max_tokens=4096)

            result = AnalysisResult(
                submission_id=submissions[-1].id,
                analysis_type="problem_journey",
                result_json=response.content,
                ai_model=response.model,
                token_cost=response.input_tokens + response.output_tokens,
                cost_usd=response.cost,
                analyzed_at=datetime.utcnow(),
            )

            # Try to parse JSON and extract structured fields
            try:
                parsed = json.loads(response.content)
                result.summary = parsed.get("journey_summary", "")
                result.suggestions = json.dumps(
                    parsed.get("suggestions", []), ensure_ascii=False
                )
            except json.JSONDecodeError:
                result.summary = response.content[:500]

            db.session.add(result)
            db.session.commit()
            return result

        except Exception as e:
            logger.error(
                f"Journey analysis failed for problem {problem_db_id}: {e}"
            )
            return None

    def get_monthly_cost(self) -> float:
        """Get total AI API cost for the current month.

        Returns:
            Total cost in USD for the current calendar month.
        """
        from sqlalchemy import func

        month_start = datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return (
            db.session.query(func.sum(AnalysisResult.cost_usd))
            .filter(AnalysisResult.analyzed_at >= month_start)
            .scalar()
            or 0.0
        )
