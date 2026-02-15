"""
Knowledge graph AI analyzer.

Generates comprehensive knowledge mastery assessments by combining
tag scores, stage progress, and weakness data with AI analysis.
Results are stored as AnalysisLog entries with log_type='knowledge'.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models import Student, Submission, PlatformAccount, AnalysisLog, AnalysisResult, Problem
from .engine import AnalysisEngine
from .weakness import WeaknessDetector
from .analysis_log import AnalysisLogManager
from .ai_analyzer import AIAnalyzer
from .contest_calendar import get_upcoming_contests
from .prompts.knowledge_assessment import build_knowledge_assessment_prompt

logger = logging.getLogger(__name__)


class KnowledgeAnalyzer:
    """Generates AI-powered knowledge mastery assessments for students.

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

    def analyze_with_progress(self):
        """Run AI knowledge assessment, yielding progress at each stage.

        Yields dicts with keys: step, message, detail (optional), assessment (on done).
        Steps: collect, weakness, prompt, llm, parse, save, done.
        """
        from app.services.stats_service import StatsService

        # Step 1: Collect data
        yield {"step": "collect", "message": "正在收集知识点评分数据..."}
        basic_stats = self.engine.get_basic_stats()
        tag_scores = self.engine.get_tag_scores()
        graph_data = StatsService.get_knowledge_graph_data(self.student_id)
        stage_stats = graph_data.get("stages", {})

        top_tags = sorted(
            [
                {
                    "display_name": info["display_name"],
                    "stage": info["stage"],
                    "score": info["score"],
                    "pass_rate": info["pass_rate"],
                    "solved": info["solved"],
                    "attempted": info["attempted"],
                }
                for name, info in tag_scores.items()
            ],
            key=lambda x: -x["score"],
        )

        # Step 2: Analyze weaknesses
        yield {"step": "weakness", "message": "正在分析薄弱知识点..."}
        weaknesses = WeaknessDetector(self.student_id).detect()

        # Step 2.5: Collect submission review insights
        submission_insights = self._collect_submission_insights()

        # Step 3: Build prompt
        tag_count = len(top_tags)
        weak_count = len(weaknesses)
        yield {
            "step": "prompt",
            "message": "正在构建提示词...",
            "detail": f"{tag_count} 个知识点, {weak_count} 个薄弱项",
        }

        prev_log = self.log_manager.get_latest_log("knowledge")
        previous_findings = None
        previous_assessment = None
        recent_stats = None
        if prev_log:
            if prev_log.key_findings:
                try:
                    previous_findings = json.loads(prev_log.key_findings)
                except (json.JSONDecodeError, TypeError):
                    pass
            if prev_log.content:
                try:
                    previous_assessment = json.loads(prev_log.content)
                except (json.JSONDecodeError, TypeError):
                    pass
            # Only compute recent stats if last report was at least 1 day ago
            hours_since = (datetime.utcnow() - prev_log.created_at).total_seconds() / 3600
            if hours_since >= 24:
                recent_stats = self._get_stats_since(prev_log.created_at)

        upcoming_contests = get_upcoming_contests()

        messages = build_knowledge_assessment_prompt(
            student_name=self.student.name if self.student else "学生",
            student_age=self.student.age if self.student else None,
            student_grade=self.student.grade if self.student else None,
            stage_stats=stage_stats,
            top_tags=top_tags,
            weak_tags=weaknesses,
            basic_stats=basic_stats,
            previous_findings=previous_findings,
            previous_assessment=previous_assessment,
            recent_stats=recent_stats,
            upcoming_contests=upcoming_contests if upcoming_contests else None,
            submission_insights=submission_insights if submission_insights else None,
        )

        # Step 4: Call LLM
        try:
            ai = AIAnalyzer(app=self.app)
            user_id = self.student.parent_id if self.student else None
            provider, model = ai._get_llm("advanced", user_id=user_id)
        except Exception as e:
            logger.error(f"Knowledge AI analysis failed (LLM init): {e}")
            yield {"step": "error", "message": f"AI 模型初始化失败: {e}"}
            return

        yield {
            "step": "llm",
            "message": f"正在调用 AI 模型分析...",
            "detail": model,
        }

        try:
            response = provider.chat(messages, model=model, max_tokens=4096)
        except Exception as e:
            logger.error(f"Knowledge AI analysis failed (LLM call): {e}")
            yield {"step": "error", "message": f"AI 调用失败: {e}"}
            return

        # Step 5: Parse response
        yield {"step": "parse", "message": "正在解析返回结果..."}
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        try:
            assessment = json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse knowledge assessment JSON: {content[:200]}")
            yield {"step": "error", "message": "AI 返回结果解析失败"}
            return

        # Step 6: Save
        yield {"step": "save", "message": "正在保存分析报告..."}

        period_end = datetime.utcnow()
        period_start = self._get_earliest_submission_date() or period_end

        key_findings = []
        if assessment.get("strengths"):
            key_findings.extend(
                f"优势: {s}" for s in assessment["strengths"][:3]
            )
        if assessment.get("weaknesses"):
            key_findings.extend(
                f"不足: {w}" for w in assessment["weaknesses"][:3]
            )

        improvement_notes = ""
        if assessment.get("training_plan"):
            lines = []
            for item in assessment["training_plan"]:
                lines.append(
                    f"{item.get('priority', '-')}. "
                    f"{item.get('tag_display', item.get('tag', ''))}: "
                    f"{item.get('suggestion', '')}"
                )
            improvement_notes = "\n".join(lines)

        self.log_manager.create_log(
            log_type="knowledge",
            period_start=period_start,
            period_end=period_end,
            content=json.dumps(assessment, ensure_ascii=False),
            key_findings=key_findings,
            improvement_notes=improvement_notes,
        )

        # Step 7: Done
        yield {
            "step": "done",
            "message": "分析完成",
            "assessment": assessment,
        }

    def analyze(self) -> dict | None:
        """Run AI knowledge assessment and persist the result.

        Returns:
            Parsed assessment dict, or None if analysis fails.
        """
        result = None
        for progress in self.analyze_with_progress():
            if progress["step"] == "done":
                result = progress.get("assessment")
            elif progress["step"] == "error":
                return None
        return result

    def get_latest(self) -> dict | None:
        """Get the most recent knowledge assessment.

        Returns:
            Dict with 'assessment' and 'analyzed_at', or None if no record exists.
        """
        log = self.log_manager.get_latest_log("knowledge")
        if not log:
            return None

        try:
            assessment = json.loads(log.content)
        except (json.JSONDecodeError, TypeError):
            return None

        return {
            "assessment": assessment,
            "analyzed_at": log.created_at.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
        }

    def get_all(self) -> list[dict]:
        """Get all knowledge assessment records, newest first.

        Returns:
            List of dicts with 'id', 'assessment', 'analyzed_at'.
        """
        logs = (
            AnalysisLog.query.filter_by(
                student_id=self.student_id, log_type="knowledge"
            )
            .order_by(AnalysisLog.created_at.desc())
            .all()
        )
        results = []
        for log in logs:
            try:
                assessment = json.loads(log.content)
            except (json.JSONDecodeError, TypeError):
                continue
            results.append({
                "id": log.id,
                "assessment": assessment,
                "analyzed_at": log.created_at.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
            })
        return results

    @staticmethod
    def delete(log_id: int) -> bool:
        """Delete a knowledge assessment log by ID.

        Returns:
            True if deleted, False if not found.
        """
        log = AnalysisLog.query.get(log_id)
        if not log or log.log_type != "knowledge":
            return False
        db.session.delete(log)
        db.session.commit()
        return True

    def _collect_submission_insights(self) -> list[dict]:
        """Collect code review insights grouped by tag for the student.

        Returns:
            List of dicts with tag_display, stage, strengths, issues, mastery_level.
            At most 15 tags.
        """
        account_ids = [
            a.id
            for a in PlatformAccount.query.filter_by(
                student_id=self.student_id
            ).all()
        ]
        if not account_ids:
            return []

        # Get submission reviews for this student
        reviews = (
            AnalysisResult.query
            .join(Submission, AnalysisResult.submission_id == Submission.id)
            .filter(
                AnalysisResult.analysis_type == "submission_review",
                Submission.platform_account_id.in_(account_ids),
            )
            .order_by(AnalysisResult.analyzed_at.desc())
            .limit(50)
            .all()
        )

        if not reviews:
            return []

        # Group insights by tag
        tag_insights = {}
        for review in reviews:
            try:
                parsed = json.loads(review.result_json)
            except (json.JSONDecodeError, TypeError):
                continue

            submission = Submission.query.get(review.submission_id)
            if not submission or not submission.problem_id_ref:
                continue

            problem = Problem.query.get(submission.problem_id_ref)
            if not problem:
                continue

            for tag in problem.tags:
                key = tag.name
                if key not in tag_insights:
                    tag_insights[key] = {
                        "tag_display": tag.display_name,
                        "stage": tag.stage,
                        "strengths": [],
                        "issues": [],
                        "mastery_levels": [],
                    }

                for s in parsed.get("strengths", []):
                    if s not in tag_insights[key]["strengths"]:
                        tag_insights[key]["strengths"].append(s)
                for issue in parsed.get("issues", []):
                    desc = issue.get("description", str(issue)) if isinstance(issue, dict) else str(issue)
                    if desc not in tag_insights[key]["issues"]:
                        tag_insights[key]["issues"].append(desc)
                ml = parsed.get("mastery_level")
                if ml:
                    tag_insights[key]["mastery_levels"].append(ml)

        # Aggregate and return top 15
        results = []
        for key, info in tag_insights.items():
            # Pick most common mastery level
            mastery = None
            if info["mastery_levels"]:
                from collections import Counter
                mastery = Counter(info["mastery_levels"]).most_common(1)[0][0]

            results.append({
                "tag_display": info["tag_display"],
                "stage": info["stage"],
                "strengths": info["strengths"][:3],
                "issues": info["issues"][:3],
                "mastery_level": mastery,
            })

        results.sort(key=lambda x: x["stage"])
        return results[:15]

    def _get_stats_since(self, since_dt: datetime) -> dict:
        """Compute submission stats since a given datetime.

        Returns:
            Dict with submissions, ac_count, unique_solved, active_days, pass_rate.
        """
        from sqlalchemy import func

        account_ids = [
            a.id
            for a in PlatformAccount.query.filter_by(
                student_id=self.student_id
            ).all()
        ]
        if not account_ids:
            return {
                "submissions": 0,
                "ac_count": 0,
                "unique_solved": 0,
                "active_days": 0,
                "pass_rate": 0,
            }

        base_q = Submission.query.filter(
            Submission.platform_account_id.in_(account_ids),
            Submission.submitted_at > since_dt,
        )

        total = base_q.count()
        ac_count = base_q.filter(Submission.status == "AC").count()

        unique_solved = (
            base_q.filter(Submission.status == "AC")
            .with_entities(Submission.problem_id_ref)
            .distinct()
            .count()
        )

        active_days_result = (
            base_q
            .with_entities(func.date(Submission.submitted_at))
            .distinct()
            .count()
        )

        pass_rate = round(ac_count / total * 100, 1) if total > 0 else 0

        return {
            "submissions": total,
            "ac_count": ac_count,
            "unique_solved": unique_solved,
            "active_days": active_days_result,
            "pass_rate": pass_rate,
        }

    def _get_earliest_submission_date(self) -> datetime | None:
        """Find the earliest submission date for this student."""
        account_ids = [
            a.id
            for a in PlatformAccount.query.filter_by(
                student_id=self.student_id
            ).all()
        ]
        if not account_ids:
            return None

        earliest = (
            Submission.query
            .filter(Submission.platform_account_id.in_(account_ids))
            .order_by(Submission.submitted_at.asc())
            .first()
        )
        return earliest.submitted_at if earliest else None
