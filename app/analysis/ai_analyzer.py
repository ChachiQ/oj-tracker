"""
AI analysis orchestrator.

Coordinates LLM providers with prompt templates to perform AI-powered
analysis of student submissions and problem-solving journeys.
Includes budget management to prevent runaway API costs.
"""
from __future__ import annotations

import json
import logging
import re
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
from .prompts.problem_solution import build_problem_solution_prompt
from .prompts.problem_full_solution import build_problem_full_solution_prompt
from .prompts.problem_comprehensive import build_problem_comprehensive_prompt
from .prompts.submission_review import build_submission_review_prompt

logger = logging.getLogger(__name__)


def _clean_llm_json(text: str) -> str:
    """Extract JSON from LLM response that may be wrapped in markdown code blocks."""
    if not text:
        return text
    stripped = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    if stripped.startswith('```'):
        first_nl = stripped.find('\n')
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
        if stripped.endswith('```'):
            stripped = stripped[:-3].rstrip()
    # Fallback: if not starting with {, extract first { to last }
    stripped = stripped.strip()
    if stripped and stripped[0] != '{':
        start = stripped.find('{')
        end = stripped.rfind('}')
        if start != -1 and end > start:
            stripped = stripped[start:end + 1]
    return stripped


def _fix_json_escape_sequences(text: str) -> str:
    """Fix invalid JSON escape sequences like \\max, \\min from LaTeX.

    Scans character-by-character and doubles any backslash that is followed
    by a character not valid in JSON escapes (not one of: " \\ / b f n r t u).
    Only call this as a fallback after json.loads fails on the original text.
    """
    if not text:
        return text
    _VALID_ESCAPES = set('"\\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch in _VALID_ESCAPES:
                result.append(ch)
            else:
                # Invalid escape like \max → \\max
                result.append('\\\\')
            i += 1
            result.append(text[i])
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _fix_trailing_commas(text: str) -> str:
    """Remove trailing commas before } and ] in JSON."""
    return re.sub(r',\s*([\]}])', r'\1', text)


def _repair_truncated_json(text: str) -> str:
    """Attempt to close a truncated JSON string by tracking bracket/quote nesting.

    If the JSON is already complete, returns it unchanged.
    """
    if not text:
        return text
    text = text.rstrip()

    # Quick check: if it parses, return as-is
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, TypeError):
        pass

    in_string = False
    escape_next = False
    stack = []  # tracks { and [

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()

    if not stack and not in_string:
        # Balanced already — truncation isn't about brackets
        return text

    repaired = text.rstrip()

    # If we're inside a string, close it
    if in_string:
        repaired += '"'

    # Strip trailing comma or incomplete value tokens
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in (',', ':'):
        repaired = repaired[:-1].rstrip()

    # Close unclosed brackets in reverse order
    for opener in reversed(stack):
        repaired += '}' if opener == '{' else ']'

    return repaired


def _parse_llm_json(text: str) -> dict | None:
    """Multi-level tolerant JSON parser for LLM responses.

    Tries increasingly aggressive repair strategies:
    1. _clean_llm_json → json.loads (existing logic)
    2. _fix_json_escape_sequences → json.loads
    3. _repair_truncated_json → json.loads
    4. escape fix + truncation repair combined
    """
    if not text:
        return None

    # Level 1: clean + parse
    cleaned = _clean_llm_json(text)
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Level 2: fix escape sequences
    try:
        fixed = _fix_json_escape_sequences(cleaned)
        result = json.loads(fixed)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Level 2.5: fix trailing commas (common LLM mistake: {"key": "value",})
    try:
        no_trailing = _fix_trailing_commas(cleaned)
        result = json.loads(no_trailing)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Level 3: repair truncation
    try:
        repaired = _repair_truncated_json(cleaned)
        result = json.loads(repaired)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Level 4: escape fix + truncation repair combined
    try:
        combined = _repair_truncated_json(fixed)
        result = json.loads(combined)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError, UnboundLocalError):
        pass

    return None


# 中文难度描述 → 数字映射（基于 _macros.html 的 labels）
_DIFFICULTY_TEXT_MAP = {
    '入门': 1, '入门+': 2,
    '普及-': 3, '普及': 4,
    '提高-': 5, '提高': 6,
    '省选-': 7, '省选': 8,
    'noi-': 9, 'noi': 10,
    # 常见 LLM 口语化表达
    '简单': 2, '容易': 2,
    '中等': 4, '一般': 4,
    '较难': 6, '困难': 8, '难': 7,
}


def _parse_difficulty(raw_value) -> int | None:
    """尝试将 LLM 返回的 difficulty 值解析为 1-10 整数。

    支持：整数、浮点数、数字字符串、中文难度描述、
    "4/10" 分数格式、"难度：3" / "difficulty: 5" 嵌入格式、
    dict 如 {"overall": 3} 递归提取。
    返回 None 表示无法解析。
    """
    if raw_value is None:
        return None

    # dict → 递归提取 "overall" 或第一个值
    if isinstance(raw_value, dict):
        if "overall" in raw_value:
            return _parse_difficulty(raw_value["overall"])
        for v in raw_value.values():
            result = _parse_difficulty(v)
            if result is not None:
                return result
        return None

    # 尝试直接数字
    try:
        val = int(float(raw_value))  # 处理 "5.0" 等情况
        if 1 <= val <= 10:
            return val
        return None
    except (ValueError, TypeError):
        pass

    if isinstance(raw_value, str):
        text = raw_value.strip()

        # "4/10" 格式 → 提取分子
        if '/' in text:
            import re
            m = re.match(r'(\d+)\s*/\s*\d+', text)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 10:
                    return val

        # "难度：3" / "difficulty: 5" → 提取嵌入数字
        import re
        m = re.search(r'(\d+)', text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 10:
                return val

        # 中文映射
        return _DIFFICULTY_TEXT_MAP.get(text.lower())

    return None


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

    def _check_budget(self, user_id: int = None) -> bool:
        """Check if AI spending is within the monthly budget.

        Args:
            user_id: Optional user id to read per-user budget from UserSetting.

        Returns:
            True if budget has not been exceeded, False otherwise.
        """
        from sqlalchemy import func
        from app.models import UserSetting

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

    @staticmethod
    def _inject_images_for_provider(messages, provider_name):
        """Extract ![](url) image URLs from message content and inject as multimodal blocks.

        For Claude and OpenAI, images are sent as native multimodal content.
        For other providers, a text note is appended indicating images are present.
        """
        _IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

        new_messages = []
        for msg in messages:
            content = msg.get('content', '')
            if not isinstance(content, str):
                new_messages.append(msg)
                continue

            urls = _IMG_RE.findall(content)
            if not urls:
                new_messages.append(msg)
                continue

            if provider_name == 'claude':
                blocks = [{"type": "text", "text": content}]
                for _alt, url in urls:
                    blocks.append({
                        "type": "image",
                        "source": {"type": "url", "url": url},
                    })
                new_messages.append({**msg, "content": blocks})

            elif provider_name == 'openai':
                blocks = [{"type": "text", "text": content}]
                for _alt, url in urls:
                    blocks.append({
                        "type": "image_url",
                        "image_url": {"url": url},
                    })
                new_messages.append({**msg, "content": blocks})

            else:
                # Non-multimodal provider: append a text hint
                hint = "\n\n注意：本题包含图片但当前 AI 无法查看，请根据文字描述分析。"
                new_messages.append({**msg, "content": content + hint})

        return new_messages

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

        # Resolve user for per-user budget
        user_id = student.parent_id if student else None

        # Check budget
        if not self._check_budget(user_id=user_id):
            logger.warning("AI monthly budget exceeded, skipping analysis")
            return None

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

        problem = Problem.query.get(problem_db_id)
        student = Student.query.get(student_id)
        user_id = student.parent_id if student else None

        if not self._check_budget(user_id=user_id):
            logger.warning("AI monthly budget exceeded, skipping journey analysis")
            return None

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

    def analyze_problem_solution(
        self, problem_id: int, force: bool = False, user_id: int = None,
    ) -> AnalysisResult | None:
        """Analyze a problem's solution approach (no code).

        Args:
            problem_id: Database ID of the problem.
            force: If True, delete existing analysis and re-analyze.
            user_id: Optional user id for per-user AI config.

        Returns:
            AnalysisResult instance, or None if analysis cannot be performed.
        """
        analysis_type = "problem_solution"

        existing = AnalysisResult.query.filter_by(
            problem_id_ref=problem_id, analysis_type=analysis_type,
        ).first()
        if existing and not force:
            if existing.result_json:
                try:
                    json.loads(existing.result_json)
                    return existing
                except (json.JSONDecodeError, TypeError):
                    pass
            # Empty or invalid result_json → delete and re-analyze
            db.session.delete(existing)
            db.session.commit()
        if existing and force:
            db.session.delete(existing)
            db.session.commit()

        if not self._check_budget(user_id=user_id):
            logger.warning("AI monthly budget exceeded, skipping problem solution analysis")
            return None

        problem = Problem.query.get(problem_id)
        if not problem or not problem.description:
            return None

        messages = build_problem_solution_prompt(
            problem_title=problem.title or problem.problem_id,
            problem_description=problem.description,
            input_desc=problem.input_desc,
            output_desc=problem.output_desc,
            examples=problem.examples,
            hint=problem.hint,
            difficulty=problem.difficulty,
            problem_type=problem.ai_problem_type,
        )

        try:
            provider, model = self._get_llm("basic", user_id=user_id)
            response = provider.chat(messages, model=model)

            cleaned = _clean_llm_json(response.content)
            result = AnalysisResult(
                problem_id_ref=problem_id,
                analysis_type=analysis_type,
                result_json=cleaned,
                ai_model=response.model,
                token_cost=response.input_tokens + response.output_tokens,
                cost_usd=response.cost,
                analyzed_at=datetime.utcnow(),
            )

            try:
                parsed = json.loads(cleaned)
                result.summary = parsed.get("approach", "")
            except json.JSONDecodeError:
                result.summary = (response.content or "")[:500]

            db.session.add(result)
            db.session.commit()
            return result

        except Exception as e:
            logger.error(f"Problem solution analysis failed for {problem_id}: {e}")
            return None

    def analyze_problem_full_solution(
        self, problem_id: int, force: bool = False, user_id: int = None,
    ) -> AnalysisResult | None:
        """Generate a complete AI solution for a problem.

        Args:
            problem_id: Database ID of the problem.
            force: If True, delete existing analysis and re-analyze.
            user_id: Optional user id for per-user AI config.

        Returns:
            AnalysisResult instance, or None if analysis cannot be performed.
        """
        analysis_type = "problem_full_solution"

        existing = AnalysisResult.query.filter_by(
            problem_id_ref=problem_id, analysis_type=analysis_type,
        ).first()
        if existing and not force:
            if existing.result_json:
                try:
                    json.loads(existing.result_json)
                    return existing
                except (json.JSONDecodeError, TypeError):
                    pass
            # Empty or invalid result_json → delete and re-analyze
            db.session.delete(existing)
            db.session.commit()
        if existing and force:
            db.session.delete(existing)
            db.session.commit()

        if not self._check_budget(user_id=user_id):
            logger.warning("AI monthly budget exceeded, skipping full solution analysis")
            return None

        problem = Problem.query.get(problem_id)
        if not problem or not problem.description:
            return None

        messages = build_problem_full_solution_prompt(
            problem_title=problem.title or problem.problem_id,
            problem_description=problem.description,
            input_desc=problem.input_desc,
            output_desc=problem.output_desc,
            examples=problem.examples,
            hint=problem.hint,
            difficulty=problem.difficulty,
            problem_type=problem.ai_problem_type,
        )

        try:
            provider, model = self._get_llm("basic", user_id=user_id)
            response = provider.chat(messages, model=model, max_tokens=8192)

            cleaned = _clean_llm_json(response.content)
            result = AnalysisResult(
                problem_id_ref=problem_id,
                analysis_type=analysis_type,
                result_json=cleaned,
                ai_model=response.model,
                token_cost=response.input_tokens + response.output_tokens,
                cost_usd=response.cost,
                analyzed_at=datetime.utcnow(),
            )

            try:
                parsed = json.loads(cleaned)
                result.summary = parsed.get("approach", "")
            except json.JSONDecodeError:
                result.summary = (response.content or "")[:500]

            db.session.add(result)
            db.session.commit()
            return result

        except Exception as e:
            logger.error(f"Full solution analysis failed for {problem_id}: {e}")
            return None

    def analyze_problem_comprehensive(
        self, problem_id: int, force: bool = False, user_id: int = None,
    ) -> dict | None:
        """Perform classification + solution + full_solution in one LLM call.

        Stores results as 3 separate AnalysisResult records for backward
        compatibility. Returns a dict keyed by 'classify', 'solution',
        'full_solution' with the AnalysisResult instances (or None per part
        on partial failure).

        Args:
            problem_id: Database ID of the problem.
            force: If True, delete existing analyses and re-analyze.
            user_id: Optional user id for per-user AI config.

        Returns:
            Dict mapping analysis part names to AnalysisResult instances,
            or None if analysis cannot be performed at all.
        """
        analysis_types = [
            "problem_classify", "problem_solution", "problem_full_solution",
        ]

        # Check which types already exist with valid JSON
        existing_types = set()
        if not force:
            for atype in analysis_types:
                existing = AnalysisResult.query.filter_by(
                    problem_id_ref=problem_id, analysis_type=atype,
                ).first()
                if existing and existing.result_json:
                    try:
                        json.loads(existing.result_json)
                        existing_types.add(atype)
                    except (json.JSONDecodeError, TypeError):
                        pass
            if len(existing_types) == 3:
                problem = Problem.query.get(problem_id)
                if problem and not problem.difficulty:
                    # difficulty 仍为 0，需要重新 classify
                    return self._classify_only(problem_id, user_id)
                # All present — return existing results
                results = {}
                for atype in analysis_types:
                    key = atype.replace("problem_", "")
                    results[key] = AnalysisResult.query.filter_by(
                        problem_id_ref=problem_id, analysis_type=atype,
                    ).first()
                return results

            # Only missing classify → run classify-only, save tokens
            if existing_types == {"problem_solution", "problem_full_solution"}:
                return self._classify_only(problem_id, user_id)

        if not self._check_budget(user_id=user_id):
            logger.warning("AI monthly budget exceeded, skipping comprehensive analysis")
            return None

        problem = Problem.query.get(problem_id)
        if not problem or not problem.description:
            return None

        # Parse platform_tags
        platform_tags = None
        if problem.platform_tags:
            try:
                platform_tags = json.loads(problem.platform_tags)
            except (json.JSONDecodeError, TypeError):
                pass

        messages = build_problem_comprehensive_prompt(
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
            provider, model = self._get_llm("basic", user_id=user_id)
            messages = self._inject_images_for_provider(messages, provider.PROVIDER_NAME)
            response = provider.chat(messages, model=model, max_tokens=16384)
        except Exception as e:
            logger.error(f"Comprehensive analysis LLM call failed for {problem_id}: {e}")
            problem.ai_retry_count = (problem.ai_retry_count or 0) + 1
            if problem.ai_retry_count >= 3:
                problem.ai_skip_backfill = True
                logger.warning(f"Problem {problem_id} flagged for skip after {problem.ai_retry_count} failures")
            problem.ai_analysis_error = str(e)[:500]
            db.session.commit()
            return None

        if response.finish_reason in ("max_tokens", "length"):
            logger.warning(f"Comprehensive response TRUNCATED for problem {problem_id}: "
                           f"finish_reason={response.finish_reason}, output_tokens={response.output_tokens}")

        parsed = _parse_llm_json(response.content)

        # Auto-retry with dual strategy when JSON parsing fails
        if parsed is None:
            is_truncated = response.finish_reason in ("max_tokens", "length")

            if is_truncated:
                # Strategy A: reasoning exhausted tokens — resend original prompt
                # with an extra instruction to skip lengthy reasoning
                logger.warning(
                    f"Comprehensive JSON parse failed for {problem_id} "
                    f"(truncation: finish_reason={response.finish_reason}), "
                    f"retrying with shortened-reasoning instruction"
                )
                # Inject a concise-output instruction into the system message
                truncation_hint = (
                    "\n\n【重要】上一次请求因输出过长被截断。"
                    "请直接输出 JSON 结果，不要进行冗长的推理过程。"
                    "确保输出完整的 JSON 对象。"
                )
                retry_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        retry_messages.append({
                            **msg,
                            "content": msg["content"] + truncation_hint,
                        })
                    else:
                        retry_messages.append(msg)
                # If no system message was found, add instruction as a user suffix
                if not any(m["role"] == "system" for m in messages):
                    retry_messages.append({
                        "role": "user",
                        "content": truncation_hint.strip(),
                    })
            else:
                # Strategy B: prose response (finish_reason=stop) — send the
                # model's reply back and ask it to reformat as JSON
                logger.warning(
                    f"Comprehensive JSON parse failed for {problem_id}, "
                    f"retrying with reformat instruction "
                    f"(content preview: {response.content[:300]!r})"
                )
                retry_messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": (
                        "你的分析内容很好，但输出格式不正确。"
                        "请将上述分析结果严格按照我之前要求的 JSON 格式重新输出。"
                        "只输出 JSON，不要包含任何其他文字或 markdown 标记。"
                    )},
                ]

            try:
                response2 = provider.chat(retry_messages, model=model, max_tokens=16384)
                parsed = _parse_llm_json(response2.content)
                if parsed:
                    response = response2
                    retry_type = "truncation" if is_truncated else "reformat"
                    logger.info(f"Comprehensive {retry_type} retry succeeded for {problem_id}")
                else:
                    logger.warning(
                        f"Comprehensive retry also failed for {problem_id} "
                        f"(content preview: {response2.content[:300]!r})"
                    )
            except Exception as e:
                logger.warning(f"Comprehensive retry LLM call failed for {problem_id}: {e}")

        if parsed is None:
            logger.error(
                f"Comprehensive analysis JSON parse failed for {problem_id} "
                f"(cleaned preview: {_clean_llm_json(response.content)[:300]!r})"
            )
            truncated = (f" [TRUNCATED: {response.finish_reason}]"
                         if response.finish_reason in ("max_tokens", "length") else "")
            problem.difficulty = 0
            problem.ai_analyzed = True
            problem.ai_analysis_error = f"comprehensive JSON parse failed{truncated}: {response.content[:200]}"
            problem.ai_retry_count = (problem.ai_retry_count or 0) + 1
            if problem.ai_retry_count >= 3:
                problem.ai_skip_backfill = True
                logger.warning(f"Problem {problem_id} flagged for skip after {problem.ai_retry_count} failures")
            db.session.commit()
            return None

        # Delete old records AFTER LLM success + JSON parse — prevents data loss
        if force:
            for atype in analysis_types:
                AnalysisResult.query.filter_by(
                    problem_id_ref=problem_id, analysis_type=atype,
                ).delete()
        else:
            for atype in analysis_types:
                if atype not in existing_types:
                    AnalysisResult.query.filter_by(
                        problem_id_ref=problem_id, analysis_type=atype,
                    ).delete()

        total_cost = response.cost or 0
        total_tokens = (response.input_tokens or 0) + (response.output_tokens or 0)
        part_cost = total_cost / 3
        part_tokens = total_tokens // 3
        now = datetime.utcnow()
        results = {}

        # --- classify ---
        classify_data = parsed.get("classify")
        if not classify_data and isinstance(parsed.get("problem_type"), str):
            classify_data = {
                "problem_type": parsed.get("problem_type", ""),
                "knowledge_points": parsed.get("knowledge_points", []),
                "difficulty_assessment": parsed.get("difficulty_assessment", {}),
            }
        if classify_data and isinstance(classify_data, dict):
            try:
                result_json = json.dumps(classify_data, ensure_ascii=False)
                ar = AnalysisResult(
                    problem_id_ref=problem_id,
                    analysis_type="problem_classify",
                    result_json=result_json,
                    summary=classify_data.get("problem_type", ""),
                    ai_model=response.model or model or "",
                    token_cost=part_tokens,
                    cost_usd=part_cost,
                    analyzed_at=now,
                )
                db.session.add(ar)

                # Update Problem model fields (same as ProblemClassifier)
                problem.ai_tags = json.dumps(
                    classify_data.get("knowledge_points", []), ensure_ascii=False
                )
                problem.ai_problem_type = classify_data.get("problem_type", "")

                for kp in classify_data.get("knowledge_points", []):
                    tag_name = kp.get("tag_name")
                    if not tag_name:
                        continue
                    from app.models import Tag
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if tag and tag not in problem.tags:
                        problem.tags.append(tag)
                    elif not tag:
                        logger.warning(f"Unknown tag '{tag_name}' returned by LLM for problem {problem_id}")

                overall = classify_data.get("difficulty_assessment", {}).get("overall")
                difficulty_val = _parse_difficulty(overall)
                if difficulty_val:
                    problem.difficulty = difficulty_val
                    problem.ai_analysis_error = None
                else:
                    logger.warning(
                        f"Unparseable difficulty for problem {problem_id}: {overall!r}"
                    )
                    problem.difficulty = 0
                    problem.ai_analysis_error = f"unparseable difficulty: {overall!r}"

                problem.ai_analyzed = True
                results["classify"] = ar
            except Exception as e:
                logger.warning(f"Comprehensive: classify part failed for {problem_id}: {e}")
                problem.difficulty = 0
                problem.ai_analyzed = True
                problem.ai_analysis_error = f"classify processing error: {e}"
        else:
            # LLM didn't return a valid classify section
            logger.warning(f"Comprehensive: classify section missing/invalid for {problem_id}")
            problem.difficulty = 0
            problem.ai_analyzed = True
            problem.ai_analysis_error = "classify section missing from comprehensive response"
            problem.ai_retry_count = (problem.ai_retry_count or 0) + 1
            if problem.ai_retry_count >= 3:
                problem.ai_skip_backfill = True
                logger.warning(f"Problem {problem_id} flagged for skip after {problem.ai_retry_count} failures")

        # --- solution ---
        if "problem_solution" in existing_types:
            results["solution"] = AnalysisResult.query.filter_by(
                problem_id_ref=problem_id, analysis_type="problem_solution",
            ).first()
        else:
            solution_data = parsed.get("solution")
            if solution_data and isinstance(solution_data, dict):
                try:
                    result_json = json.dumps(solution_data, ensure_ascii=False)
                    ar = AnalysisResult(
                        problem_id_ref=problem_id,
                        analysis_type="problem_solution",
                        result_json=result_json,
                        summary=solution_data.get("approach", ""),
                        ai_model=response.model or model or "",
                        token_cost=part_tokens,
                        cost_usd=part_cost,
                        analyzed_at=now,
                    )
                    db.session.add(ar)
                    results["solution"] = ar
                except Exception as e:
                    logger.warning(f"Comprehensive: solution part failed for {problem_id}: {e}")

        # --- full_solution ---
        if "problem_full_solution" in existing_types:
            results["full_solution"] = AnalysisResult.query.filter_by(
                problem_id_ref=problem_id, analysis_type="problem_full_solution",
            ).first()
        else:
            full_solution_data = parsed.get("full_solution")
            if full_solution_data and isinstance(full_solution_data, dict):
                try:
                    result_json = json.dumps(full_solution_data, ensure_ascii=False)
                    ar = AnalysisResult(
                        problem_id_ref=problem_id,
                        analysis_type="problem_full_solution",
                        result_json=result_json,
                        summary=full_solution_data.get("approach", ""),
                        ai_model=response.model or model or "",
                        token_cost=part_tokens,
                        cost_usd=part_cost,
                        analyzed_at=now,
                    )
                    db.session.add(ar)
                    results["full_solution"] = ar
                except Exception as e:
                    logger.warning(f"Comprehensive: full_solution part failed for {problem_id}: {e}")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Comprehensive analysis commit failed for {problem_id}: {e}")
            return None

        logger.info(
            f"Comprehensive analysis for {problem.platform}:{problem.problem_id} — "
            f"parts ok: {list(results.keys())}"
        )
        return results if results else None

    def _classify_only(self, problem_id, user_id):
        """Only run classification for a problem that already has solution/full_solution."""
        from .problem_classifier import ProblemClassifier
        classifier = ProblemClassifier(app=self.app)
        ok = classifier.classify_problem(problem_id, user_id=user_id)
        if ok:
            results = {}
            for atype in ["problem_classify", "problem_solution", "problem_full_solution"]:
                key = atype.replace("problem_", "")
                results[key] = AnalysisResult.query.filter_by(
                    problem_id_ref=problem_id, analysis_type=atype,
                ).first()
            return results
        return None

    def review_submission(
        self, submission_id: int, force: bool = False, user_id: int = None,
    ) -> AnalysisResult | None:
        """Review a student's code submission.

        Args:
            submission_id: Database ID of the submission.
            force: If True, delete existing review and re-analyze.
            user_id: Optional user id for per-user AI config.

        Returns:
            AnalysisResult instance, or None if review cannot be performed.
        """
        analysis_type = "submission_review"

        existing = AnalysisResult.query.filter_by(
            submission_id=submission_id, analysis_type=analysis_type,
        ).first()
        if existing and not force:
            if existing.result_json:
                try:
                    json.loads(existing.result_json)
                    return existing
                except (json.JSONDecodeError, TypeError):
                    pass
            # Empty or invalid result_json → delete and re-analyze
            db.session.delete(existing)
            db.session.commit()
        if existing and force:
            db.session.delete(existing)
            db.session.commit()

        if not self._check_budget(user_id=user_id):
            logger.warning("AI monthly budget exceeded, skipping submission review")
            return None

        submission = Submission.query.get(submission_id)
        if not submission or not submission.source_code:
            return None

        problem = submission.problem
        student = (
            submission.platform_account.student
            if submission.platform_account
            else None
        )

        messages = build_submission_review_prompt(
            problem_title=problem.title if problem else "Unknown",
            problem_description=problem.description if problem else None,
            source_code=submission.source_code,
            status=submission.status,
            score=submission.score,
            language=submission.language,
            student_age=student.age if student else None,
            student_grade=student.grade if student else None,
        )

        try:
            if not user_id and student and hasattr(student, 'parent_id'):
                user_id = student.parent_id

            provider, model = self._get_llm("basic", user_id=user_id)
            messages = self._inject_images_for_provider(messages, provider.PROVIDER_NAME)
            response = provider.chat(messages, model=model)

            cleaned = _clean_llm_json(response.content)
            result = AnalysisResult(
                submission_id=submission_id,
                analysis_type=analysis_type,
                result_json=cleaned,
                ai_model=response.model,
                token_cost=response.input_tokens + response.output_tokens,
                cost_usd=response.cost,
                analyzed_at=datetime.utcnow(),
            )

            try:
                parsed = json.loads(cleaned)
                result.summary = parsed.get("approach_analysis", "")
                result.suggestions = json.dumps(
                    parsed.get("suggestions", []), ensure_ascii=False,
                )
            except json.JSONDecodeError:
                result.summary = (response.content or "")[:500]

            db.session.add(result)
            db.session.commit()
            return result

        except Exception as e:
            logger.error(f"Submission review failed for {submission_id}: {e}")
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
