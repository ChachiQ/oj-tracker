"""Backfill problem_tags for existing problems using TagMapper or AI.

Usage:
    python backfill_tags.py                # backfill all untagged problems
    python backfill_tags.py --dry-run      # preview without writing
    python backfill_tags.py --platform luogu
    python backfill_tags.py --refetch      # re-fetch tags from platform API
    python backfill_tags.py --all          # re-map ALL problems (even already tagged)
    python backfill_tags.py --ai           # use AI to classify unanalyzed problems
    python backfill_tags.py --ai --limit 15  # AI classify only 15 problems
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Problem
from app.services.tag_mapper import TagMapper

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

BATCH_SIZE = 50


def backfill(platform=None, dry_run=False, refetch=False, remap_all=False):
    app = create_app()
    with app.app_context():
        query = Problem.query

        if platform:
            query = query.filter_by(platform=platform)

        if not remap_all:
            # Only problems with no tags
            query = query.filter(~Problem.tags.any())

        problems = query.all()
        logger.info("Found %d problems to process", len(problems))

        stats = {'mapped': 0, 'skipped': 0, 'no_tags': 0, 'refetched': 0}

        for i, problem in enumerate(problems, 1):
            # Determine raw platform tags
            raw_tags = []

            if problem.platform_tags:
                try:
                    raw_tags = json.loads(problem.platform_tags)
                except (json.JSONDecodeError, TypeError):
                    raw_tags = []

            if not raw_tags and refetch:
                raw_tags = _refetch_tags(problem)
                if raw_tags:
                    problem.platform_tags = json.dumps(
                        raw_tags, ensure_ascii=False
                    )
                    stats['refetched'] += 1

            if not raw_tags:
                stats['no_tags'] += 1
                continue

            mapper = TagMapper(problem.platform)
            tags = mapper.map_tags(raw_tags)

            if not tags:
                stats['skipped'] += 1
                logger.info(
                    "  [%d] %s:%s — raw=%r → no internal match",
                    i, problem.platform, problem.problem_id, raw_tags,
                )
                continue

            tag_names = [t.name for t in tags]

            if dry_run:
                logger.info(
                    "  [%d] %s:%s — %r → %s",
                    i, problem.platform, problem.problem_id, raw_tags, tag_names,
                )
            else:
                # Clear existing tags if remapping all
                if remap_all:
                    problem.tags = []

                for tag in tags:
                    if tag not in problem.tags:
                        problem.tags.append(tag)

            stats['mapped'] += 1

            # Batch commit
            if not dry_run and i % BATCH_SIZE == 0:
                db.session.commit()
                logger.info("  Committed batch (%d processed)", i)

        if not dry_run:
            db.session.commit()

        logger.info("Done! %s", stats)


def backfill_ai(platform=None, limit=15):
    """Use AI to classify unanalyzed problems."""
    app = create_app()
    with app.app_context():
        from app.analysis.problem_classifier import ProblemClassifier

        query = Problem.query.filter_by(ai_analyzed=False)
        if platform:
            query = query.filter_by(platform=platform)

        # Prioritize problems with recent submissions
        from app.models import Submission
        from sqlalchemy import func

        sub_latest = (
            db.session.query(
                Submission.problem_id_ref,
                func.max(Submission.submitted_at).label('latest'),
            )
            .group_by(Submission.problem_id_ref)
            .subquery()
        )
        query = (
            query.outerjoin(sub_latest, Problem.id == sub_latest.c.problem_id_ref)
            .order_by(sub_latest.c.latest.desc().nullslast())
        )

        problems = query.limit(limit).all()
        logger.info("AI classifying %d problems (limit=%d)", len(problems), limit)

        classifier = ProblemClassifier(app=app)
        success = 0
        for i, p in enumerate(problems, 1):
            logger.info(
                "  [%d/%d] %s:%s — %s",
                i, len(problems), p.platform, p.problem_id, p.title,
            )
            if classifier.classify_problem(p.id):
                success += 1
                logger.info(
                    "    → tags=%s, difficulty=%s, type=%s",
                    [t.name for t in p.tags], p.difficulty, p.ai_problem_type,
                )
            else:
                logger.warning("    → classification failed")

        logger.info("Done! %d/%d classified successfully.", success, len(problems))


def _refetch_tags(problem):
    """Re-fetch tags from the platform scraper."""
    try:
        from app.scrapers import get_scraper_instance
        scraper = get_scraper_instance(problem.platform)
        scraped = scraper.fetch_problem(problem.problem_id)
        if scraped and scraped.tags:
            return scraped.tags
    except Exception as e:
        logger.warning(
            "Failed to refetch tags for %s:%s — %s",
            problem.platform, problem.problem_id, e,
        )
    return []


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill problem tags')
    parser.add_argument('--platform', help='Only process problems from this platform')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--refetch', action='store_true',
                        help='Re-fetch tags from platform if platform_tags is empty')
    parser.add_argument('--all', action='store_true', dest='remap_all',
                        help='Re-map ALL problems, not just untagged ones')
    parser.add_argument('--ai', action='store_true',
                        help='Use AI to classify problems (requires API key)')
    parser.add_argument('--limit', type=int, default=15,
                        help='Max number of problems to AI-classify (default: 15)')
    args = parser.parse_args()

    if args.ai:
        backfill_ai(platform=args.platform, limit=args.limit)
    else:
        backfill(
            platform=args.platform,
            dry_run=args.dry_run,
            refetch=args.refetch,
            remap_all=args.remap_all,
        )
