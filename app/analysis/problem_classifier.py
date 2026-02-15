"""
AI-powered problem classifier.

Uses LLM to analyze problem descriptions and automatically classify them
by type, knowledge points, difficulty dimensions, and solution approach.
Results are persisted on the Problem model (M2M tags + difficulty) for future use.
"""

import json
import logging
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import Problem, Tag
from .llm import get_provider
from .prompts.problem_classify import build_classify_prompt

logger = logging.getLogger(__name__)


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

    def classify_problem(self, problem_id: int) -> bool:
        """Classify a single problem using AI.

        Skips problems that have already been analyzed (ai_analyzed=True).

        Args:
            problem_id: Database ID of the problem to classify.

        Returns:
            True if classification was successful, False otherwise.
        """
        problem = Problem.query.get(problem_id)
        if not problem or problem.ai_analyzed:
            return False

        provider_name = self.app.config.get("AI_PROVIDER", "claude")
        api_key_map = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
        }
        api_key = self.app.config.get(api_key_map.get(provider_name, ""), "")
        model = self.app.config.get("AI_MODEL_BASIC")

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
            provider = get_provider(provider_name, api_key=api_key)
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
            db.session.commit()
            logger.info(
                f"Classified problem {problem.platform}:{problem.problem_id} "
                f"as {problem.ai_problem_type}, "
                f"tags={[t.name for t in problem.tags]}, "
                f"difficulty={problem.difficulty}"
            )
            return True

        except Exception as e:
            logger.error(f"Problem classification failed for {problem_id}: {e}")
            return False

    def classify_unanalyzed(self, limit: int = 20) -> int:
        """Classify unanalyzed problems in batch.

        Processes up to `limit` problems that have not yet been AI-analyzed.

        Args:
            limit: Maximum number of problems to classify in this batch.

        Returns:
            Number of problems successfully classified.
        """
        problems = Problem.query.filter_by(ai_analyzed=False).limit(limit).all()
        classified = 0
        for p in problems:
            if self.classify_problem(p.id):
                classified += 1
        return classified
