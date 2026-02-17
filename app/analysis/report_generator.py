"""
Report generator for weekly and monthly student performance reports.

Combines statistical data from the AnalysisEngine, weakness detection,
trend analysis, and AI-generated narrative content to produce comprehensive
reports suitable for parents and coaches.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from flask import current_app

from app.extensions import db
from app.models import Report, Student, AnalysisResult, AnalysisLog
from .engine import AnalysisEngine
from .weakness import WeaknessDetector
from .trend import TrendAnalyzer
from .analysis_log import AnalysisLogManager
from .llm import get_provider
from .prompts.periodic_report import build_periodic_report_prompt
from .prompts.periodic_summary import build_periodic_summary_prompt

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates weekly and monthly performance reports for students.

    Orchestrates data gathering from multiple analysis components and
    uses AI to produce human-readable report narratives.

    Args:
        student_id: Database ID of the student.
        app: Flask application instance. If None, uses current_app.
    """

    def __init__(self, student_id: int, app=None):
        self.student_id = student_id
        self.app = app or current_app._get_current_object()
        self.engine = AnalysisEngine(student_id)
        self.student = Student.query.get(student_id)
        self.log_manager = AnalysisLogManager(student_id)

    def generate_weekly_report(self, end_date: datetime = None, start_date: datetime = None) -> Report | None:
        """Generate a weekly report ending at the given date.

        Args:
            end_date: End date of the report period. Defaults to now.
            start_date: Start date of the report period. If provided with
                end_date, used directly instead of computing from end_date.

        Returns:
            Report model instance, or None if generation fails.
        """
        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(weeks=1))
        return self._generate_report("weekly", start_date, end_date)

    def generate_monthly_report(self, end_date: datetime = None, start_date: datetime = None) -> Report | None:
        """Generate a monthly report ending at the given date.

        Args:
            end_date: End date of the report period. Defaults to now.
            start_date: Start date of the report period. If provided with
                end_date, used directly instead of computing from end_date.

        Returns:
            Report model instance, or None if generation fails.
        """
        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(days=30))
        return self._generate_report("monthly", start_date, end_date)

    def generate_quarterly_report(self, end_date: datetime = None, start_date: datetime = None) -> Report | None:
        """Generate a quarterly report ending at the given date.

        Args:
            end_date: End date of the report period. Defaults to now.
            start_date: Start date of the report period. If provided with
                end_date, used directly instead of computing from end_date.

        Returns:
            Report model instance, or None if generation fails.
        """
        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(days=90))
        return self._generate_report("quarterly", start_date, end_date)

    def _generate_report(
        self, report_type: str, start_date: datetime, end_date: datetime
    ) -> Report | None:
        """Internal method to generate a report of the given type.

        Gathers all necessary data, calls the AI for narrative generation,
        and persists both the report and an analysis log entry.

        Args:
            report_type: 'weekly' or 'monthly'.
            start_date: Start of the report period.
            end_date: End of the report period.

        Returns:
            Report model instance, or None if generation fails critically.
        """
        # Gather current statistics
        weeks_map = {"weekly": 1, "monthly": 4, "quarterly": 13}
        current_stats = self.engine.get_basic_stats()
        weekly_stats = self.engine.get_weekly_stats(
            weeks_map.get(report_type, 1)
        )
        tag_scores = self.engine.get_tag_scores()
        weaknesses = WeaknessDetector(self.student_id).detect()

        # Get previous report for comparison
        prev_report = (
            Report.query.filter_by(
                student_id=self.student_id, report_type=report_type
            )
            .order_by(Report.period_end.desc())
            .first()
        )

        # Get previous analysis log for context
        prev_log = self.log_manager.get_latest_log(report_type)

        # Build formatted text summaries for the prompt
        stats_text = json.dumps(weekly_stats, ensure_ascii=False, indent=2)
        prev_stats_text = prev_report.stats_json if prev_report else None

        # Build weakness summary text
        weakness_text = "\n".join(
            [
                f"- {w['display_name']}: {w['reason']} (严重度: {w['severity']})"
                for w in weaknesses[:10]
            ]
        )

        # Build knowledge progress text
        knowledge_text = "\n".join(
            [
                f"- {name}: 评分{info['score']}, 通过率{info['pass_rate']}%"
                for name, info in sorted(
                    tag_scores.items(), key=lambda x: -x[1]["score"]
                )[:15]
            ]
        )

        # Build radar chart data
        radar_categories = [
            "搜索",
            "动态规划",
            "图论",
            "数据结构",
            "数学",
            "字符串",
            "基础算法",
        ]
        radar_curr = {}
        for tag_name, info in tag_scores.items():
            cat = info.get("display_name", tag_name)
            for rc in radar_categories:
                if rc in cat:
                    radar_curr[rc] = max(radar_curr.get(rc, 0), info["score"])

        # Call AI to generate report narrative
        try:
            from app.models import UserSetting
            from .llm.config import MODEL_CONFIG

            user_id = self.student.parent_id if self.student else None
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

            if not api_key:
                api_key = self.app.config.get(
                    env_key_map.get(provider_name, ""), "",
                )

            provider = get_provider(provider_name, api_key=api_key)

            # Pick advanced-tier model from MODEL_CONFIG
            models = MODEL_CONFIG.get(provider_name, {}).get("models", {})
            model = None
            for m_name, m_info in models.items():
                if m_info.get("tier") == "advanced":
                    model = m_name
                    break
            if not model:
                model = self.app.config.get("AI_MODEL_ADVANCED")

            period_type_map = {
                "weekly": "周报",
                "monthly": "月报",
                "quarterly": "季报",
            }
            messages = build_periodic_report_prompt(
                period_type=period_type_map.get(report_type, "周报"),
                period_start=start_date.strftime("%Y.%m.%d"),
                period_end=end_date.strftime("%Y.%m.%d"),
                stats=stats_text,
                previous_stats=prev_stats_text,
                error_analysis=weakness_text,
                knowledge_progress=knowledge_text,
                student_name=self.student.name if self.student else "学生",
                student_age=self.student.age if self.student else None,
                student_grade=self.student.grade if self.student else None,
            )

            response = provider.chat(messages, model=model, max_tokens=4096)
            ai_content = response.content

        except Exception as e:
            logger.error(f"AI report generation failed: {e}")
            ai_content = (
                f"AI报告生成失败: {str(e)}\n\n统计数据:\n{stats_text}"
            )

        # Create and persist the report
        report = Report(
            student_id=self.student_id,
            report_type=report_type,
            period_start=start_date,
            period_end=end_date,
            stats_json=json.dumps(weekly_stats, ensure_ascii=False),
            ai_content=ai_content,
            radar_data_prev=(
                prev_report.radar_data_curr if prev_report else None
            ),
            radar_data_curr=json.dumps(radar_curr, ensure_ascii=False),
        )
        db.session.add(report)

        # Also create an analysis log entry for future reference
        self.log_manager.create_log(
            log_type=report_type,
            period_start=start_date,
            period_end=end_date,
            content=ai_content[:2000],
            key_findings=[
                w["display_name"] + ": " + w["reason"] for w in weaknesses[:5]
            ],
        )

        db.session.commit()
        return report
