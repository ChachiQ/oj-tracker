"""
AI-powered problem classifier.

Uses LLM to analyze problem descriptions and automatically classify them
by type, knowledge points, difficulty dimensions, and solution approach.
Results are persisted on the Problem model (M2M tags + difficulty) for future use.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import current_app
from sqlalchemy import or_

from app.extensions import db
from app.models import Problem, Tag, UserSetting, AnalysisResult
from .llm import get_provider
from .llm.config import MODEL_CONFIG
from .prompts.problem_classify import build_classify_prompt

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class ProblemClassifier:
    """Classifies competitive programming problems using AI.

    Analyzes problem descriptions to determine:
    - Problem type (e.g. DP, graph, greedy)
    - Knowledge points mapped to Tag M2M relationship
    - Multi-dimensional difficulty assessment
    - Brief solution idea

    Args:
        app: Flask application instance. If None, uses current_app.
    """

    def __init__(self, app=None):
        self.app = app or current_app._get_current_object()

    def _get_llm(self, user_id: int = None):
        """Get an LLM provider and model, checking UserSetting first.

        When *user_id* is given the method first looks for per-user overrides
        stored in ``UserSetting`` (ai_provider, api_key_*).  Falls back to
        ``app.config`` / environment variables when no user config exists.

        Args:
            user_id: Optional user id to load per-user AI configuration.

        Returns:
            Tuple of (provider_instance, model_name).
        """
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

        # Pick the basic-tier model from MODEL_CONFIG
        models = MODEL_CONFIG.get(provider_name, {}).get("models", {})
        model = None
        for m_name, m_info in models.items():
            if m_info.get("tier") == "basic":
                model = m_name
                break

        # Final fallback to explicit config key
        if not model:
            model = self.app.config.get("AI_MODEL_BASIC")

        return provider, model

    def _check_budget(self, user_id: int = None) -> bool:
        """Check if AI spending is within the monthly budget.

        Args:
            user_id: Optional user id to read per-user budget from UserSetting.

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
        if user_id:
            user_budget = UserSetting.get(user_id, 'ai_monthly_budget')
            if user_budget:
                budget = float(user_budget)
        return total_cost < budget

    def classify_problem(self, problem_id: int, user_id: int = None) -> bool:
        """Classify a single problem using AI.

        Skips problems that have already been successfully analyzed
        (ai_analyzed=True) unless they have an error recorded (eligible
        for retry up to MAX_RETRIES).

        Args:
            problem_id: Database ID of the problem to classify.
            user_id: Optional user id to load per-user AI configuration.

        Returns:
            True if classification was successful, False otherwise.
        """
        problem = Problem.query.get(problem_id)
        if not problem:
            return False
        # Skip already-analyzed problems that have no error
        if problem.ai_analyzed and not problem.ai_analysis_error:
            return False

        if not self._check_budget(user_id):
            logger.warning("AI monthly budget exceeded, skipping classification")
            return False

        provider, model = self._get_llm(user_id)

        # Parse platform_tags for prompt context
        platform_tags = None
        if problem.platform_tags:
            try:
                platform_tags = json.loads(problem.platform_tags)
            except (json.JSONDecodeError, TypeError):
                pass

        messages = build_classify_prompt(
            title=problem.title or problem.problem_id,
            platform=problem.platform,
            difficulty_raw=problem.difficulty_raw,
            description=problem.description,
            input_desc=problem.input_desc,
            output_desc=problem.output_desc,
            examples=problem.examples,
            hint=problem.hint,
            platform_tags=platform_tags,
        )

        try:
            response = provider.chat(
                messages,
                model=model,
                max_tokens=2000,
            )

            # Parse response and persist results
            try:
                parsed = json.loads(response.content)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                content = response.content
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    try:
                        parsed = json.loads(content[start:end + 1])
                    except json.JSONDecodeError:
                        parsed = None
                else:
                    parsed = None

            if parsed:
                # Store raw AI response in ai_tags
                problem.ai_tags = json.dumps(
                    parsed.get("knowledge_points", []), ensure_ascii=False
                )
                problem.ai_problem_type = parsed.get("problem_type", "")

                # Write M2M tags
                for kp in parsed.get("knowledge_points", []):
                    tag_name = kp.get("tag_name")
                    if not tag_name:
                        continue
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if tag and tag not in problem.tags:
                        problem.tags.append(tag)

                # Write AI difficulty assessment
                overall = parsed.get("difficulty_assessment", {}).get("overall")
                if overall is not None:
                    try:
                        difficulty_val = int(overall)
                        if 1 <= difficulty_val <= 10:
                            problem.difficulty = difficulty_val
                    except (ValueError, TypeError):
                        pass
            else:
                problem.ai_tags = response.content
                problem.ai_problem_type = ""

            problem.ai_analyzed = True
            problem.ai_analysis_error = None  # Clear any previous error

            # Record cost so budget tracking can see classification spending
            cost_record = AnalysisResult(
                problem_id_ref=problem.id,
                analysis_type="problem_classify",
                result_json=response.content,
                summary=problem.ai_problem_type,
                ai_model=model or "",
                token_cost=(response.input_tokens + response.output_tokens),
                cost_usd=response.cost,
                analyzed_at=datetime.utcnow(),
            )
            db.session.add(cost_record)

            db.session.commit()
            logger.info(
                f"Classified problem {problem.platform}:{problem.problem_id} "
                f"as {problem.ai_problem_type}, "
                f"tags={[t.name for t in problem.tags]}, "
                f"difficulty={problem.difficulty}"
            )
            return True

        except Exception as e:
            error_msg = str(e)[:500]
            logger.error(f"Problem classification failed for {problem_id}: {e}")
            problem.ai_analysis_error = error_msg
            problem.ai_retry_count = (problem.ai_retry_count or 0) + 1
            db.session.commit()
            return False

    def classify_unanalyzed(
        self, limit: int = 20, user_id: int = None, max_workers: int = 4,
    ) -> int:
        """Classify unanalyzed problems in batch using concurrent threads.

        Processes up to ``limit`` problems that have not yet been AI-analyzed
        or that previously failed but are still eligible for retry.

        Args:
            limit: Maximum number of problems to classify in this batch.
            user_id: Optional user id to load per-user AI configuration.
            max_workers: Number of concurrent threads (default 4).

        Returns:
            Number of problems successfully classified.
        """
        problems = (
            Problem.query.filter(
                or_(
                    Problem.ai_analyzed.is_(False),
                    db.and_(
                        Problem.ai_analysis_error.isnot(None),
                        Problem.ai_retry_count < MAX_RETRIES,
                    ),
                )
            )
            .limit(limit)
            .all()
        )

        if not problems:
            return 0

        problem_ids = [p.id for p in problems]

        # Use serial processing when only 1 worker or in-memory SQLite
        db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
        use_serial = max_workers <= 1 or db_uri == 'sqlite:///:memory:'

        if use_serial:
            classified = 0
            for pid in problem_ids:
                if self.classify_problem(pid, user_id=user_id):
                    classified += 1
            return classified

        app = self.app

        def _classify_one(pid):
            with app.app_context():
                classifier = ProblemClassifier(app=app)
                return classifier.classify_problem(pid, user_id=user_id)

        classified = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_classify_one, pid): pid
                for pid in problem_ids
            }
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    if future.result():
                        classified += 1
                except Exception as e:
                    logger.error(f"Thread error classifying {pid}: {e}")

        return classified
