"""Fix Coderlands problem URLs that are missing UUIDs.

Correct format: https://course.coderlands.com/web/#/newAnswer#{UUID}
Some early-ingested problems have fallback URLs pointing to the generic
exercise page instead of the specific problem page.

Usage:
    python scripts/fix_coderlands_urls.py --dry-run   # preview changes
    python scripts/fix_coderlands_urls.py              # apply fixes
"""
import argparse
import logging
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import create_app
from app.extensions import db
from app.models import PlatformAccount, Problem

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Matches a 32-char hex UUID in the URL fragment
_URL_UUID_RE = re.compile(r'#[0-9a-fA-F]{32}')
BASE_URL = "https://course.coderlands.com"


def _make_url(uuid: str) -> str:
    return f"{BASE_URL}/web/#/newAnswer#{uuid}"


def _needs_fix(problem: Problem) -> bool:
    """Return True if the problem URL is missing a valid UUID."""
    if not problem.url:
        return True
    return not _URL_UUID_RE.search(problem.url)


def fix_urls(dry_run: bool = False) -> None:
    app = create_app()
    with app.app_context():
        problems = Problem.query.filter_by(platform='coderlands').all()
        to_fix = [p for p in problems if _needs_fix(p)]

        logger.info(
            "Coderlands problems: %d total, %d need URL fix",
            len(problems), len(to_fix),
        )
        if not to_fix:
            logger.info("Nothing to fix.")
            return

        # Split into batch A (has UUID) and batch B (needs API)
        batch_a = [p for p in to_fix if p.platform_uuid]
        batch_b = [p for p in to_fix if not p.platform_uuid]

        logger.info(
            "  Batch A (UUID in DB, direct fix): %d", len(batch_a),
        )
        logger.info(
            "  Batch B (UUID missing, needs API): %d", len(batch_b),
        )

        stats = {'direct': 0, 'api': 0, 'failed': 0}

        # ── Batch A: direct fix ──
        for p in batch_a:
            new_url = _make_url(p.platform_uuid)
            logger.info(
                "  [A] %s — %s → %s",
                p.problem_id, p.url or '(empty)', new_url,
            )
            if not dry_run:
                p.url = new_url
            stats['direct'] += 1

        # ── Batch B: fetch UUID via API ──
        scraper = None
        if batch_b:
            account = PlatformAccount.query.filter_by(
                platform='coderlands', is_active=True,
            ).filter(
                PlatformAccount.auth_cookie.isnot(None),
                PlatformAccount.auth_cookie != '',
            ).first()

            if not account:
                logger.error(
                    "No active Coderlands account with auth_cookie found. "
                    "Cannot resolve UUIDs for %d problems.", len(batch_b),
                )
                stats['failed'] = len(batch_b)
            else:
                from app.scrapers.coderlands import CoderlandsScraper
                scraper = CoderlandsScraper(auth_cookie=account.auth_cookie)
                logger.info(
                    "  Using account: %s (student_id=%d)",
                    account.platform_uid, account.student_id,
                )

                for p in batch_b:
                    # Extract numeric part from problem_id like "P1234"
                    m = re.match(r'^P(\d+)$', p.problem_id, re.IGNORECASE)
                    if not m:
                        logger.warning(
                            "  [B] %s — cannot parse problem number, skipping",
                            p.problem_id,
                        )
                        stats['failed'] += 1
                        continue

                    problem_no = m.group(1)
                    uuid = scraper._fetch_problem_uuid(problem_no)

                    if not uuid:
                        logger.warning(
                            "  [B] %s — API returned no UUID, skipping",
                            p.problem_id,
                        )
                        stats['failed'] += 1
                        continue

                    new_url = _make_url(uuid)
                    logger.info(
                        "  [B] %s — uuid=%s, %s → %s",
                        p.problem_id, uuid, p.url or '(empty)', new_url,
                    )
                    if not dry_run:
                        p.platform_uuid = uuid
                        p.url = new_url
                    stats['api'] += 1

        if not dry_run:
            db.session.commit()
            logger.info("Changes committed.")

        logger.info("")
        logger.info("=== Summary ===")
        logger.info(
            "Direct fix (had UUID): %d | API fix: %d | Failed: %d | Total fixed: %d",
            stats['direct'], stats['api'], stats['failed'],
            stats['direct'] + stats['api'],
        )
        if dry_run:
            logger.info("(dry-run mode — no changes written)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Fix Coderlands problem URLs missing UUIDs',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview changes without writing to database',
    )
    args = parser.parse_args()
    fix_urls(dry_run=args.dry_run)
