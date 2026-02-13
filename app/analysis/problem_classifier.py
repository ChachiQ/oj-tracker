"""
AI-powered problem classifier.

Uses LLM to analyze problem descriptions and automatically classify them
by type, knowledge points, difficulty dimensions, and solution approach.
Results are persisted on the Problem model for future use.
"""

import json
import logging
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import Problem
from .llm import get_provider

logger = logging.getLogger(__name__)


class ProblemClassifier:
    """Classifies competitive programming problems using AI.

    Analyzes problem descriptions to determine:
    - Problem type (e.g. DP, graph, greedy)
    - Knowledge points with stage levels
    - Multi-dimensional difficulty assessment
    - Similar problem types and prerequisites

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

        prompt_content = f"""请分析以下信息学竞赛题目，返回JSON格式的分析结果。

题目：{problem.title}
平台：{problem.platform}
难度：{problem.difficulty_raw or '未知'}

题目描述：
{problem.description or '(无描述)'}

输入说明：{problem.input_desc or '(无)'}
输出说明：{problem.output_desc or '(无)'}
样例：{problem.examples or '(无)'}
提示/数据范围：{problem.hint or '(无)'}

请返回JSON：
{{
  "problem_type": "题型描述(如：背包DP、BFS最短路、二分答案+贪心)",
  "knowledge_points": [
    {{"name": "知识点名称", "stage": 阶段数字1-6, "importance": "核心/辅助"}}
  ],
  "difficulty_assessment": {{
    "thinking": 1-10,
    "coding": 1-10,
    "math": 1-10,
    "overall": 1-10
  }},
  "similar_problem_types": ["相似题型"],
  "prerequisite_knowledge": ["前置知识"],
  "brief_solution_idea": "简要解题思路"
}}"""

        try:
            provider = get_provider(provider_name, api_key=api_key)
            response = provider.chat(
                [{"role": "user", "content": prompt_content}],
                model=model,
                max_tokens=2000,
            )

            # Parse response and persist results
            try:
                parsed = json.loads(response.content)
                problem.ai_tags = json.dumps(
                    parsed.get("knowledge_points", []), ensure_ascii=False
                )
                problem.ai_problem_type = parsed.get("problem_type", "")
            except json.JSONDecodeError:
                problem.ai_tags = response.content
                problem.ai_problem_type = ""

            problem.ai_analyzed = True
            db.session.commit()
            logger.info(
                f"Classified problem {problem.platform}:{problem.problem_id} "
                f"as {problem.ai_problem_type}"
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
