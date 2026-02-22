"""2-phase AI backfill service with concurrent execution.

Phase 1 (comprehensive): Merges classification + solution approach + full
solution into a single LLM call per problem via ``analyze_problem_comprehensive``.

Phase 2 (review): Code review of individual submissions (unchanged logic).

Both phases use ``ThreadPoolExecutor`` for concurrent processing, with the
concurrency limit read from the LLM provider config.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import (
    ThreadPoolExecutor, as_completed,
    TimeoutError as FuturesTimeoutError,
)
from datetime import datetime
from itertools import groupby

from sqlalchemy import func as sa_func

from app.extensions import db
from app.models import (
    Problem, Submission, AnalysisResult, PlatformAccount, SyncJob,
    UserSetting,
)

logger = logging.getLogger(__name__)


class AIBackfillService:
    PHASE_TIMEOUT_SECONDS = 3600  # 1 hour per phase

    def __init__(self, app):
        self.app = app
        self._progress_lock = threading.Lock()
        self._cancel_event = threading.Event()

    def request_cancel(self):
        """Signal the background thread to stop at the next safe point."""
        self._cancel_event.set()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, job_id: int, user_id: int, platform: str = None,
            account_id: int = None, limit: int = 0):
        """Main entry: run 2-phase AI backfill, updating SyncJob progress."""
        with self.app.app_context():
            job = db.session.get(SyncJob, job_id)
            if not job:
                logger.error(f"SyncJob {job_id} not found")
                return

            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()

            stats = {
                'comprehensive_ok': 0, 'comprehensive_total': 0,
                'review_ok': 0, 'review_total': 0,
            }

            try:
                from app.analysis.ai_analyzer import AIAnalyzer
                analyzer = AIAnalyzer(app=self.app)

                self._run_phase_comprehensive(
                    job, analyzer, stats, user_id, platform, limit,
                )

                if self._cancel_event.is_set():
                    logger.info("AI backfill job %d cancelled between phases", job_id)
                    job.status = 'failed'
                    job.error_message = '用户取消'
                else:
                    self._run_phase_review(
                        job, analyzer, stats, user_id, platform, account_id, limit,
                    )

                    if self._cancel_event.is_set():
                        logger.info("AI backfill job %d cancelled after review phase", job_id)
                        job.status = 'failed'
                        job.error_message = '用户取消'
                    else:
                        job.status = 'completed'
                        logger.info("AI backfill job %d finished with status=completed, stats=%s",
                                    job_id, stats)

            except Exception as e:
                logger.error("AI backfill job %d failed: %s", job_id, e)
                job.status = 'failed'
                job.error_message = str(e)

            finally:
                job.stats = stats
                job.finished_at = datetime.utcnow()
                job.current_phase = None
                try:
                    db.session.commit()
                except Exception as exc:
                    logger.error("Failed to commit final status for job %d: %s", job_id, exc)
                    try:
                        db.session.rollback()
                        job_fresh = db.session.get(SyncJob, job_id)
                        if job_fresh:
                            job_fresh.status = 'failed'
                            job_fresh.error_message = f'最终提交失败: {exc}'
                            job_fresh.finished_at = datetime.utcnow()
                            db.session.commit()
                    except Exception:
                        logger.error("Recovery commit also failed for job %d", job_id)

    # ------------------------------------------------------------------
    # Concurrency helpers
    # ------------------------------------------------------------------

    def _get_max_workers(self, user_id: int) -> int:
        """Determine concurrency from user's AI provider config."""
        from app.analysis.llm.config import get_max_concurrency

        provider_name = self.app.config.get("AI_PROVIDER", "zhipu")
        if user_id:
            user_prov = UserSetting.get(user_id, 'ai_provider')
            if user_prov:
                provider_name = user_prov
        return get_max_concurrency(provider_name)

    def _run_phase_concurrent(self, job, items, process_fn, stat_ok_key,
                              stat_total_key, stats, user_id):
        """Generic concurrent executor for a backfill phase.

        Args:
            job: SyncJob to update progress on.
            items: Iterable of work items (problem ids, submission ids, etc.).
            process_fn: Callable(item, user_id) -> bool. Executed in worker
                threads with app context.
            stat_ok_key: Stats dict key for successful count.
            stat_total_key: Stats dict key for total count.
            stats: Mutable stats dict.
            user_id: User id forwarded to process_fn.
        """
        item_list = list(items)
        stats[stat_total_key] = len(item_list)
        job.progress_total = len(item_list)
        job.progress_current = 0
        db.session.commit()

        if not item_list:
            return

        max_workers = self._get_max_workers(user_id)
        completed = 0
        ok_count = 0
        consecutive_errors = 0

        def _run_one(item):
            with self.app.app_context():
                return process_fn(item, user_id)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_one, item): item
                for item in item_list
            }

            try:
                for future in as_completed(futures, timeout=self.PHASE_TIMEOUT_SECONDS):
                    if self._cancel_event.is_set():
                        logger.info("AI backfill cancelled during %s phase", job.current_phase)
                        for f in futures:
                            f.cancel()
                        break

                    completed += 1
                    try:
                        if future.result():
                            ok_count += 1
                            consecutive_errors = 0
                        else:
                            consecutive_errors += 1
                    except Exception as e:
                        logger.warning("AI backfill worker failed for item %s: %s",
                                       futures[future], e)
                        consecutive_errors += 1

                    with self._progress_lock:
                        job.progress_current = completed
                        db.session.commit()

                    if consecutive_errors >= 10:
                        logger.warning(
                            "AI backfill: 10+ consecutive errors in %s phase, stopping",
                            job.current_phase,
                        )
                        for f in futures:
                            f.cancel()
                        break
            except FuturesTimeoutError:
                logger.error(
                    "Phase %s timed out after %ds (%d/%d done)",
                    job.current_phase, self.PHASE_TIMEOUT_SECONDS,
                    completed, len(item_list),
                )
                for f in futures:
                    f.cancel()

        stats[stat_ok_key] = ok_count

    # ------------------------------------------------------------------
    # Phase 1: Comprehensive (classify + solution + full_solution)
    # ------------------------------------------------------------------

    def _run_phase_comprehensive(self, job, analyzer, stats, user_id,
                                 platform, limit):
        """Phase 1: Comprehensive analysis for problems missing any of
        classify / solution / full_solution."""
        job.current_phase = 'comprehensive'

        # Problems that need comprehensive analysis:
        # - not classified (ai_analyzed=False or difficulty=0)
        # - OR missing solution analysis
        # - OR missing full_solution analysis
        classified_ids = (
            db.session.query(AnalysisResult.problem_id_ref)
            .filter_by(analysis_type="problem_classify")
        )
        has_solution_ids = (
            db.session.query(AnalysisResult.problem_id_ref)
            .filter_by(analysis_type="problem_solution")
        )
        has_full_ids = (
            db.session.query(AnalysisResult.problem_id_ref)
            .filter_by(analysis_type="problem_full_solution")
        )

        query = Problem.query.filter(
            Problem.description.isnot(None),
            Problem.ai_skip_backfill == False,  # noqa: E712  skip flagged problems
            db.or_(
                Problem.ai_analyzed == False,  # noqa: E712
                Problem.difficulty == 0,       # classify 成功但 difficulty 无效，需重试
                ~Problem.id.in_(classified_ids),
                ~Problem.id.in_(has_solution_ids),
                ~Problem.id.in_(has_full_ids),
            ),
        ).order_by(Problem.created_at.desc())

        if platform:
            query = query.filter_by(platform=platform)
        if limit:
            query = query.limit(limit)

        problem_ids = [p.id for p in query.all()]

        def _process(pid, uid):
            result = analyzer.analyze_problem_comprehensive(
                pid, force=False, user_id=uid,
            )
            return result is not None and len(result) > 0

        self._run_phase_concurrent(
            job, problem_ids, _process,
            'comprehensive_ok', 'comprehensive_total', stats, user_id,
        )

    # ------------------------------------------------------------------
    # Phase 2: Code review (unchanged logic, now concurrent)
    # ------------------------------------------------------------------

    def _run_phase_review(self, job, analyzer, stats, user_id,
                          platform, account_id, limit):
        """Phase 2: Code review of submissions."""
        job.current_phase = 'review'

        # Count existing reviews per (problem, account)
        reviewed_counts = {
            (pid, aid): cnt
            for pid, aid, cnt in db.session.query(
                Submission.problem_id_ref,
                Submission.platform_account_id,
                sa_func.count(AnalysisResult.id),
            )
            .join(AnalysisResult, AnalysisResult.submission_id == Submission.id)
            .filter(AnalysisResult.analysis_type == "submission_review")
            .group_by(Submission.problem_id_ref, Submission.platform_account_id)
            .all()
        }

        reviewed_ids = (
            db.session.query(AnalysisResult.submission_id)
            .filter_by(analysis_type="submission_review")
        )
        query = Submission.query.join(
            PlatformAccount,
            Submission.platform_account_id == PlatformAccount.id,
        ).join(
            Problem, Submission.problem_id_ref == Problem.id,
        ).filter(
            PlatformAccount.is_active == True,  # noqa: E712
            Submission.problem_id_ref.isnot(None),
            Submission.source_code.isnot(None),
            Submission.source_code != '',
            ~Submission.id.in_(reviewed_ids),
            Problem.ai_analyzed == True,        # noqa: E712  classification must have succeeded
            Problem.difficulty > 0,             # difficulty must be valid
            Problem.ai_skip_backfill == False,  # noqa: E712  not flagged for skip
        ).order_by(Submission.submitted_at.desc())

        if account_id:
            query = query.filter(
                Submission.platform_account_id == account_id
            )
        elif platform:
            query = query.filter(Problem.platform == platform)

        if limit:
            query = query.limit(limit)

        all_submissions = query.all()

        # Per-(problem, account) cap: at most 3 reviews total
        submissions = []
        def key_fn(s):
            return (s.problem_id_ref, s.platform_account_id)
        for (pid, aid), group in groupby(
            sorted(all_submissions, key=key_fn), key=key_fn
        ):
            existing = reviewed_counts.get((pid, aid), 0)
            if existing >= 3:
                continue
            remaining = 3 - existing
            subs = sorted(
                group,
                key=lambda s: s.submitted_at or datetime.min,
                reverse=True,
            )
            submissions.extend(subs[:remaining])

        submission_ids = [s.id for s in submissions]

        def _process(sid, uid):
            result = analyzer.review_submission(sid, user_id=uid)
            return result is not None

        self._run_phase_concurrent(
            job, submission_ids, _process,
            'review_ok', 'review_total', stats, user_id,
        )
