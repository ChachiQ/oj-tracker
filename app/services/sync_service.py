from __future__ import annotations

import logging
from datetime import datetime
from app.extensions import db
from app.models import PlatformAccount, Submission, Problem, Tag
from app.scrapers import get_scraper_instance

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
                db.session.add(problem)
                db.session.flush()

                # Map tags
                for tag_name in scraped.tags:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag.query.filter_by(display_name=tag_name).first()
                    if tag:
                        problem.tags.append(tag)

                return problem
        except Exception as e:
            logger.error(
                f"Failed to fetch problem {platform}:{problem_id}: {e}"
            )

        return None

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
