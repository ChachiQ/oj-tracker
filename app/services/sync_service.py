from __future__ import annotations

import json
import logging
from datetime import datetime
from app.extensions import db
from app.models import PlatformAccount, Submission, Problem, Tag
from app.scrapers import get_scraper_instance
from app.services.tag_mapper import TagMapper

logger = logging.getLogger(__name__)


class SyncService:
    def sync_account(self, account_id: int) -> dict:
        """Sync submissions for a platform account. Returns stats dict."""
        account = PlatformAccount.query.get(account_id)
        if not account or not account.is_active:
            return {'error': 'Account not found or inactive'}

        try:
            scraper = get_scraper_instance(
                account.platform,
                auth_cookie=account.auth_cookie,
                auth_password=account.auth_password,
            )
        except ValueError as e:
            return {'error': str(e)}

        stats = {'new_submissions': 0, 'new_problems': 0, 'errors': 0}
        first_record_id = None

        try:
            for scraped_sub in scraper.fetch_submissions(
                platform_uid=account.platform_uid,
                since=account.last_sync_at,
                cursor=account.sync_cursor,
            ):
                if first_record_id is None:
                    first_record_id = scraped_sub.platform_record_id
                try:
                    # Check if submission already exists
                    existing = Submission.query.filter_by(
                        platform_account_id=account.id,
                        platform_record_id=scraped_sub.platform_record_id,
                    ).first()
                    if existing:
                        continue

                    # Ensure problem exists in DB
                    problem = self._ensure_problem(
                        account.platform, scraped_sub.problem_id, scraper
                    )
                    if problem and problem.id is None:
                        # Newly created problem, count it
                        stats['new_problems'] += 1

                    # Create submission
                    submission = Submission(
                        platform_account_id=account.id,
                        problem_id_ref=problem.id if problem else None,
                        platform_record_id=scraped_sub.platform_record_id,
                        status=scraped_sub.status,
                        score=scraped_sub.score,
                        language=scraped_sub.language,
                        time_ms=scraped_sub.time_ms,
                        memory_kb=scraped_sub.memory_kb,
                        source_code=scraped_sub.source_code,
                        submitted_at=scraped_sub.submitted_at,
                    )
                    db.session.add(submission)
                    stats['new_submissions'] += 1

                    # Try to fetch source code if not included and scraper supports it
                    if not scraped_sub.source_code and scraper.SUPPORT_CODE_FETCH:
                        try:
                            code = scraper.fetch_submission_code(
                                scraped_sub.platform_record_id
                            )
                            if code:
                                submission.source_code = code
                        except Exception as e:
                            logger.debug(
                                f"Failed to fetch code for "
                                f"{scraped_sub.platform_record_id}: {e}"
                            )

                except Exception as e:
                    logger.error(
                        f"Error processing submission "
                        f"{scraped_sub.platform_record_id}: {e}"
                    )
                    stats['errors'] += 1

            # Update sync cursor and clear any previous error
            account.last_sync_at = datetime.utcnow()
            account.sync_cursor = first_record_id if first_record_id else account.sync_cursor
            account.last_sync_error = None
            account.consecutive_sync_failures = 0
            db.session.commit()

            # AI-classify newly synced problems (best-effort, after commit)
            user_id = (
                account.student.parent_id
                if account.student else None
            )
            if stats['new_problems'] > 0:
                self._classify_new_problems(account.platform, user_id=user_id)

            # Auto-analyze new content (best-effort, after commit)
            if stats['new_submissions'] > 0 or stats['new_problems'] > 0:
                self._analyze_new_content(account.id, user_id=user_id)

        except Exception as e:
            logger.error(f"Sync failed for account {account_id}: {e}")
            db.session.rollback()
            # Record the error on the account
            try:
                account = PlatformAccount.query.get(account_id)
                if account:
                    account.last_sync_error = str(e)
                    account.consecutive_sync_failures = (account.consecutive_sync_failures or 0) + 1
                    if account.consecutive_sync_failures >= 10:
                        account.is_active = False
                        logger.warning(
                            f"Account {account_id} auto-disabled after "
                            f"{account.consecutive_sync_failures} consecutive sync failures"
                        )
                    db.session.commit()
            except Exception:
                logger.error(f"Failed to record sync error for account {account_id}")
            stats['error'] = str(e)

        return stats

    def _ensure_problem(
        self, platform: str, problem_id: str, scraper
    ) -> Problem | None:
        """Ensure problem exists in DB, fetch if not."""
        problem = Problem.query.filter_by(
            platform=platform, problem_id=problem_id
        ).first()
        if problem:
            # Backfill missing content fields
            fields = ['description', 'input_desc', 'output_desc', 'examples', 'hint']
            missing = [f for f in fields if not getattr(problem, f)]
            if missing:
                try:
                    scraped = scraper.fetch_problem(problem_id)
                    if scraped:
                        for f in missing:
                            val = getattr(scraped, f, None)
                            if val:
                                setattr(problem, f, val)
                except Exception as e:
                    logger.debug(f"Backfill failed for {platform}:{problem_id}: {e}")
            return problem

        try:
            scraped = scraper.fetch_problem(problem_id)
            if scraped:
                difficulty = (
                    scraper.map_difficulty(scraped.difficulty_raw)
                    if scraped.difficulty_raw
                    else 0
                )
                problem = Problem(
                    platform=platform,
                    problem_id=problem_id,
                    title=scraped.title,
                    description=scraped.description,
                    input_desc=scraped.input_desc,
                    output_desc=scraped.output_desc,
                    examples=scraped.examples,
                    hint=scraped.hint,
                    difficulty=difficulty,
                    difficulty_raw=scraped.difficulty_raw,
                    url=scraped.url or scraper.get_problem_url(problem_id),
                    source=scraped.source,
                )
                # Store original platform tags for future re-mapping
                if scraped.tags:
                    problem.platform_tags = json.dumps(
                        scraped.tags, ensure_ascii=False
                    )

                db.session.add(problem)
                db.session.flush()

                # Map tags via TagMapper
                mapper = TagMapper(platform)
                for tag in mapper.map_tags(scraped.tags):
                    if tag not in problem.tags:
                        problem.tags.append(tag)

                return problem
        except Exception as e:
            logger.error(
                f"Failed to fetch problem {platform}:{problem_id}: {e}"
            )

        return None

    def _classify_new_problems(self, platform: str, user_id: int = None) -> None:
        """Best-effort AI classification of unanalyzed problems."""
        try:
            from app.analysis.problem_classifier import ProblemClassifier
            classifier = ProblemClassifier()
            problems = (
                Problem.query
                .filter_by(platform=platform, ai_analyzed=False)
                .order_by(Problem.created_at.desc())
                .limit(20)
                .all()
            )
            for p in problems:
                try:
                    classifier.classify_problem(p.id, user_id=user_id)
                except Exception as e:
                    logger.debug(f"AI classify skipped for {p.problem_id}: {e}")
        except Exception as e:
            logger.debug(f"AI classification unavailable: {e}")

    def _analyze_new_content(self, account_id: int, user_id: int = None) -> None:
        """Best-effort AI analysis of new problems and submissions."""
        try:
            from app.analysis.ai_analyzer import AIAnalyzer
            from app.models import AnalysisResult

            analyzer = AIAnalyzer()

            # Analyze problems that have descriptions but no solution analysis
            account = PlatformAccount.query.get(account_id)
            if not account:
                return

            account_ids = [account.id]

            # Find problems with submissions from this account, that have
            # description but no problem_solution analysis yet
            problem_ids = (
                db.session.query(Submission.problem_id_ref)
                .filter(
                    Submission.platform_account_id.in_(account_ids),
                    Submission.problem_id_ref.isnot(None),
                )
                .distinct()
                .all()
            )
            problem_ids = [pid for (pid,) in problem_ids]

            analyzed_count = 0
            for pid in problem_ids:
                if analyzed_count >= 10:
                    break
                existing = AnalysisResult.query.filter_by(
                    problem_id_ref=pid, analysis_type="problem_solution",
                ).first()
                if existing:
                    continue
                problem = Problem.query.get(pid)
                if not problem or not problem.description:
                    continue
                try:
                    analyzer.analyze_problem_solution(pid, user_id=user_id)
                    analyzed_count += 1
                except Exception as e:
                    logger.debug(f"Auto problem analysis skipped for {pid}: {e}")

            # Review submissions with source code that haven't been reviewed
            submissions = (
                Submission.query.filter(
                    Submission.platform_account_id.in_(account_ids),
                    Submission.source_code.isnot(None),
                    Submission.source_code != '',
                )
                .order_by(Submission.submitted_at.desc())
                .limit(20)
                .all()
            )

            review_count = 0
            for sub in submissions:
                if review_count >= 10:
                    break
                existing = AnalysisResult.query.filter_by(
                    submission_id=sub.id, analysis_type="submission_review",
                ).first()
                if existing:
                    continue
                try:
                    analyzer.review_submission(sub.id, user_id=user_id)
                    review_count += 1
                except Exception as e:
                    logger.debug(f"Auto submission review skipped for {sub.id}: {e}")

        except Exception as e:
            logger.debug(f"Auto-analysis unavailable: {e}")

    def sync_all_accounts(self, student_id: int = None) -> dict:
        """Sync all active accounts, optionally filtered by student."""
        query = PlatformAccount.query.filter_by(is_active=True)
        if student_id:
            query = query.filter_by(student_id=student_id)

        accounts = query.all()
        total_stats = {
            'accounts_synced': 0,
            'total_new_submissions': 0,
            'total_new_problems': 0,
        }

        for account in accounts:
            stats = self.sync_account(account.id)
            if 'error' not in stats:
                total_stats['accounts_synced'] += 1
                total_stats['total_new_submissions'] += stats.get(
                    'new_submissions', 0
                )
                total_stats['total_new_problems'] += stats.get(
                    'new_problems', 0
                )

        return total_stats
