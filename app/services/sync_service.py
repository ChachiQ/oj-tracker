from __future__ import annotations

import json
import logging
from datetime import datetime
from sqlalchemy import func

from app.extensions import db
from app.models import PlatformAccount, Submission, Problem, Tag
from app.scrapers import get_scraper_instance
from app.scrapers.common import SubmissionStatus
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
        seen_new_problems = set()  # avoid counting the same new problem twice

        try:
            for scraped_sub in scraper.fetch_submissions(
                platform_uid=account.platform_uid,
                since=account.last_sync_at,
                cursor=account.sync_cursor,
            ):
                if first_record_id is None:
                    first_record_id = scraped_sub.platform_record_id
                # Skip compile error submissions – no analytical value
                if scraped_sub.status == SubmissionStatus.CE.value:
                    continue

                try:
                    # Check if submission already exists
                    existing = Submission.query.filter_by(
                        platform_account_id=account.id,
                        platform_record_id=scraped_sub.platform_record_id,
                    ).first()
                    if existing:
                        continue

                    # Track new problems
                    problem_key = f"{account.platform}:{scraped_sub.problem_id}"
                    if problem_key not in seen_new_problems:
                        existing_problem = Problem.query.filter_by(
                            platform=account.platform,
                            problem_id=scraped_sub.problem_id,
                        ).first()
                        if not existing_problem:
                            seen_new_problems.add(problem_key)
                            stats['new_problems'] += 1

                    # Ensure problem exists in DB
                    problem = self._ensure_problem(
                        account.platform, scraped_sub.problem_id, scraper
                    )

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
            # Some scrapers (e.g. Coderlands) use a custom cursor (hash-based)
            scraper_cursor = getattr(scraper, '_new_cursor', None)
            if isinstance(scraper_cursor, str):
                account.sync_cursor = scraper_cursor
            elif first_record_id:
                account.sync_cursor = first_record_id
            account.last_sync_error = None
            account.consecutive_sync_failures = 0

            # Update last_submission_at from actual submission data
            max_submitted = db.session.query(
                func.max(Submission.submitted_at)
            ).filter(
                Submission.platform_account_id == account.id
            ).scalar()
            if max_submitted:
                account.last_submission_at = max_submitted

            db.session.commit()

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
            # Also backfill Coderlands problems missing UUID (needed for URL)
            needs_uuid = (platform == 'coderlands' and not problem.platform_uuid)
            if missing or needs_uuid:
                try:
                    scraped = scraper.fetch_problem(problem_id)
                    if scraped:
                        for f in missing:
                            val = getattr(scraped, f, None)
                            if val:
                                setattr(problem, f, val)
                        # Update URL if we got a more specific one
                        if scraped.url and scraped.url != problem.url:
                            problem.url = scraped.url
                except Exception as e:
                    logger.debug(f"Backfill failed for {platform}:{problem_id}: {e}")
            return problem

        try:
            scraped = scraper.fetch_problem(problem_id)
            if scraped:
                problem = Problem(
                    platform=platform,
                    problem_id=problem_id,
                    title=scraped.title,
                    description=scraped.description,
                    input_desc=scraped.input_desc,
                    output_desc=scraped.output_desc,
                    examples=scraped.examples,
                    hint=scraped.hint,
                    difficulty=0,
                    difficulty_raw=scraped.difficulty_raw,
                    url=scraped.url or scraper.get_problem_url(problem_id),
                    source=scraped.source,
                )
                # Set platform_uuid if provided (e.g. Coderlands)
                if scraped.platform_uuid:
                    problem.platform_uuid = scraped.platform_uuid

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

    def sync_all_accounts(self, student_id: int = None, user_id: int = None) -> dict:
        """Sync all active accounts, optionally filtered by student.

        Args:
            student_id: Filter by specific student.
            user_id: Filter by accounts belonging to this user's students.
        """
        from app.models import Student
        query = PlatformAccount.query.filter_by(is_active=True)
        if user_id:
            student_ids = [
                s.id for s in Student.query.filter_by(parent_id=user_id).all()
            ]
            query = query.filter(PlatformAccount.student_id.in_(student_ids))
        elif student_id:
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
