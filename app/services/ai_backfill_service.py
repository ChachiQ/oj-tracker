"""Unified 4-phase AI backfill service.

Consolidates AI analysis logic previously scattered across SyncService,
scheduler, and backfill_tags.py. Designed to run in a background thread
with Flask app context, updating SyncJob progress as it goes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from itertools import groupby
from operator import attrgetter

from sqlalchemy import func as sa_func

from app.extensions import db
from app.models import (
    Problem, Submission, AnalysisResult, PlatformAccount, SyncJob,
)

logger = logging.getLogger(__name__)


class AIBackfillService:
    def __init__(self, app):
        self.app = app

    def run(self, job_id: int, user_id: int, platform: str = None,
            account_id: int = None, limit: int = 0):
        """Main entry: run 4-phase AI backfill, updating SyncJob progress."""
        with self.app.app_context():
            job = db.session.get(SyncJob, job_id)
            if not job:
                logger.error(f"SyncJob {job_id} not found")
                return

            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()

            stats = {
                'classify_ok': 0, 'classify_total': 0,
                'solution_ok': 0, 'solution_total': 0,
                'full_solution_ok': 0, 'full_solution_total': 0,
                'review_ok': 0, 'review_total': 0,
            }

            try:
                from app.analysis.problem_classifier import ProblemClassifier
                from app.analysis.ai_analyzer import AIAnalyzer

                classifier = ProblemClassifier(app=self.app)
                analyzer = AIAnalyzer(app=self.app)

                self._run_phase_classify(
                    job, classifier, stats, user_id, platform, limit
                )
                self._run_phase_solution(
                    job, analyzer, stats, user_id, platform, limit
                )
                self._run_phase_full_solution(
                    job, analyzer, stats, user_id, platform, limit
                )
                self._run_phase_review(
                    job, analyzer, stats, user_id, platform, account_id, limit
                )

                job.status = 'completed'

            except Exception as e:
                logger.error(f"AI backfill job {job_id} failed: {e}")
                job.status = 'failed'
                job.error_message = str(e)

            finally:
                job.stats = stats
                job.finished_at = datetime.utcnow()
                job.current_phase = None
                db.session.commit()

    def _run_phase_classify(self, job, classifier, stats, user_id,
                            platform, limit):
        """Phase 1: AI classification of unanalyzed problems."""
        job.current_phase = 'classify'

        query = Problem.query.filter(
            db.or_(Problem.ai_analyzed == False, Problem.difficulty == 0)  # noqa: E712
        ).order_by(Problem.created_at.desc())
        if platform:
            query = query.filter_by(platform=platform)
        if limit:
            query = query.limit(limit)

        problems = query.all()
        stats['classify_total'] = len(problems)
        job.progress_total = len(problems)
        job.progress_current = 0
        db.session.commit()

        for i, p in enumerate(problems, 1):
            try:
                if classifier.classify_problem(p.id, user_id=user_id):
                    stats['classify_ok'] += 1
            except Exception as e:
                logger.debug(f"Classify failed for {p.problem_id}: {e}")
            job.progress_current = i
            db.session.commit()

    def _run_phase_solution(self, job, analyzer, stats, user_id,
                            platform, limit):
        """Phase 2: Solution analysis for problems missing it."""
        job.current_phase = 'solution'

        query = Problem.query.filter(
            Problem.description.isnot(None),
            ~Problem.id.in_(
                db.session.query(AnalysisResult.problem_id_ref)
                .filter_by(analysis_type="problem_solution")
            ),
        )
        if platform:
            query = query.filter_by(platform=platform)
        if limit:
            query = query.limit(limit)

        problems = query.all()
        stats['solution_total'] = len(problems)
        job.progress_total = len(problems)
        job.progress_current = 0
        db.session.commit()

        for i, p in enumerate(problems, 1):
            try:
                result = analyzer.analyze_problem_solution(
                    p.id, user_id=user_id
                )
                if result:
                    stats['solution_ok'] += 1
            except Exception as e:
                logger.debug(f"Solution analysis failed for {p.problem_id}: {e}")
            job.progress_current = i
            db.session.commit()

    def _run_phase_full_solution(self, job, analyzer, stats, user_id,
                                 platform, limit):
        """Phase 3: Full solution (code) generation for problems."""
        job.current_phase = 'full_solution'

        query = Problem.query.filter(
            Problem.description.isnot(None),
            ~Problem.id.in_(
                db.session.query(AnalysisResult.problem_id_ref)
                .filter_by(analysis_type="problem_full_solution")
            ),
        )
        if platform:
            query = query.filter_by(platform=platform)
        if limit:
            query = query.limit(limit)

        problems = query.all()
        stats['full_solution_total'] = len(problems)
        job.progress_total = len(problems)
        job.progress_current = 0
        db.session.commit()

        for i, p in enumerate(problems, 1):
            try:
                result = analyzer.analyze_problem_full_solution(
                    p.id, user_id=user_id
                )
                if result:
                    stats['full_solution_ok'] += 1
            except Exception as e:
                logger.debug(
                    f"Full solution failed for {p.problem_id}: {e}"
                )
            job.progress_current = i
            db.session.commit()

    def _run_phase_review(self, job, analyzer, stats, user_id,
                          platform, account_id, limit):
        """Phase 4: Code review of submissions."""
        job.current_phase = 'review'

        # Count existing reviews per problem
        reviewed_counts = dict(
            db.session.query(
                Submission.problem_id_ref,
                sa_func.count(AnalysisResult.id),
            )
            .join(AnalysisResult, AnalysisResult.submission_id == Submission.id)
            .filter(AnalysisResult.analysis_type == "submission_review")
            .group_by(Submission.problem_id_ref)
            .all()
        )

        reviewed_ids = (
            db.session.query(AnalysisResult.submission_id)
            .filter_by(analysis_type="submission_review")
        )
        query = Submission.query.join(
            PlatformAccount,
            Submission.platform_account_id == PlatformAccount.id,
        ).filter(
            PlatformAccount.is_active == True,  # noqa: E712
            Submission.problem_id_ref.isnot(None),
            Submission.source_code.isnot(None),
            Submission.source_code != '',
            ~Submission.id.in_(reviewed_ids),
        ).order_by(Submission.submitted_at.desc())

        if account_id:
            query = query.filter(
                Submission.platform_account_id == account_id
            )
        elif platform:
            query = query.join(
                Problem, Submission.problem_id_ref == Problem.id
            ).filter(Problem.platform == platform)

        if limit:
            query = query.limit(limit)

        all_submissions = query.all()

        # Per-problem cap: at most 3 reviews total
        submissions = []
        key_fn = attrgetter('problem_id_ref')
        for pid, group in groupby(
            sorted(all_submissions, key=key_fn), key=key_fn
        ):
            existing = reviewed_counts.get(pid, 0)
            if existing >= 3:
                continue
            remaining = 3 - existing
            subs = sorted(
                group,
                key=lambda s: s.submitted_at or datetime.min,
                reverse=True,
            )
            submissions.extend(subs[:remaining])

        stats['review_total'] = len(submissions)
        job.progress_total = len(submissions)
        job.progress_current = 0
        db.session.commit()

        for i, sub in enumerate(submissions, 1):
            try:
                result = analyzer.review_submission(sub.id, user_id=user_id)
                if result:
                    stats['review_ok'] += 1
            except Exception as e:
                logger.debug(f"Review failed for submission {sub.id}: {e}")
            job.progress_current = i
            db.session.commit()
