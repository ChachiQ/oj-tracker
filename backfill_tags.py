"""Backfill problem_tags for existing problems using TagMapper or AI.

Usage:
    python backfill_tags.py                # backfill all untagged problems
    python backfill_tags.py --dry-run      # preview without writing
    python backfill_tags.py --platform luogu
    python backfill_tags.py --refetch      # re-fetch tags from platform API
    python backfill_tags.py --all          # re-map ALL problems (even already tagged)
    python backfill_tags.py --ai           # use AI to classify unanalyzed problems
    python backfill_tags.py --ai --limit 15  # AI classify only 15 problems
    python backfill_tags.py --ai --user-id 1 # use specific user's AI config
    python backfill_tags.py --review --dry-run  # preview comprehensive backfill
    python backfill_tags.py --review            # comprehensive AI backfill (4 phases)
    python backfill_tags.py --review --platform luogu --limit 30
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime
from itertools import groupby
from operator import attrgetter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Problem, Submission, AnalysisResult
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


def _find_ai_user():
    """Find the first user that has an AI API key configured in UserSetting."""
    from app.models import UserSetting
    for key in ('api_key_zhipu', 'api_key_claude', 'api_key_openai'):
        setting = UserSetting.query.filter_by(key=key).filter(
            UserSetting.value.isnot(None),
            UserSetting.value != '',
        ).first()
        if setting:
            return setting.user_id
    return None


def backfill_ai(platform=None, limit=15, user_id=None):
    """Use AI to classify unanalyzed problems."""
    app = create_app()
    with app.app_context():
        from app.analysis.problem_classifier import ProblemClassifier

        # Auto-discover a user with AI config if not specified
        if user_id is None:
            user_id = _find_ai_user()
            if user_id:
                logger.info("Auto-detected user_id=%d with AI config", user_id)
            else:
                logger.warning(
                    "No --user-id given and no user with AI API key found. "
                    "Falling back to environment variables."
                )

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
            if classifier.classify_problem(p.id, user_id=user_id):
                success += 1
                logger.info(
                    "    → tags=%s, difficulty=%s, type=%s",
                    [t.name for t in p.tags], p.difficulty, p.ai_problem_type,
                )
            else:
                logger.warning("    → classification failed")

        logger.info("Done! %d/%d classified successfully.", success, len(problems))


def backfill_reviews(platform=None, limit=0, user_id=None, dry_run=False):
    """Comprehensive AI backfill: classify, solution, full solution, code review."""
    app = create_app()
    with app.app_context():
        from app.analysis.problem_classifier import ProblemClassifier
        from app.analysis.ai_analyzer import AIAnalyzer

        # Auto-discover a user with AI config if not specified
        if user_id is None:
            user_id = _find_ai_user()
            if user_id:
                logger.info("Auto-detected user_id=%d with AI config", user_id)
            else:
                logger.warning(
                    "No --user-id given and no user with AI API key found. "
                    "Falling back to environment variables."
                )

        classifier = ProblemClassifier(app=app)
        analyzer = AIAnalyzer(app=app)

        stats = {
            'classify_ok': 0, 'classify_total': 0,
            'solution_ok': 0, 'solution_total': 0,
            'full_solution_ok': 0, 'full_solution_total': 0,
            'review_ok': 0, 'review_total': 0,
        }

        # ── Phase 1: AI Classification ──────────────────────────────
        logger.info("")
        logger.info("=== 阶段 1/4：AI 分类 ===")

        query = Problem.query.filter(
            db.or_(Problem.ai_analyzed == False, Problem.difficulty == 0)  # noqa: E712
        ).order_by(Problem.created_at.desc())
        if platform:
            query = query.filter_by(platform=platform)
        if limit:
            query = query.limit(limit)

        problems_1 = query.all()
        stats['classify_total'] = len(problems_1)
        limit_info = f" (limit={limit})" if limit else ""
        logger.info("Found %d problems to classify%s", len(problems_1), limit_info)

        if dry_run:
            for i, p in enumerate(problems_1, 1):
                logger.info("  [%d/%d] %s:%s — %s", i, len(problems_1),
                            p.platform, p.problem_id, p.title)
        else:
            for i, p in enumerate(problems_1, 1):
                if classifier.classify_problem(p.id, user_id=user_id):
                    stats['classify_ok'] += 1
                    logger.info(
                        "  [%d/%d] %s:%s — %s → tags=%s, difficulty=%s, type=%s",
                        i, len(problems_1), p.platform, p.problem_id, p.title,
                        [t.name for t in p.tags], p.difficulty, p.ai_problem_type,
                    )
                else:
                    logger.warning(
                        "  [%d/%d] %s:%s — %s → classification failed",
                        i, len(problems_1), p.platform, p.problem_id, p.title,
                    )

        logger.info("Done! %d/%d classified.", stats['classify_ok'], stats['classify_total'])

        # ── Phase 2: Solution Analysis ──────────────────────────────
        logger.info("")
        logger.info("=== 阶段 2/4：思路分析 ===")

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

        problems_2 = query.all()
        stats['solution_total'] = len(problems_2)
        logger.info("Found %d problems without solution analysis%s",
                     len(problems_2), limit_info)

        if dry_run:
            for i, p in enumerate(problems_2, 1):
                logger.info("  [%d/%d] %s:%s — %s", i, len(problems_2),
                            p.platform, p.problem_id, p.title)
        else:
            for i, p in enumerate(problems_2, 1):
                result = analyzer.analyze_problem_solution(p.id, user_id=user_id)
                if result:
                    stats['solution_ok'] += 1
                    logger.info(
                        "  [%d/%d] %s:%s — %s → OK",
                        i, len(problems_2), p.platform, p.problem_id, p.title,
                    )
                else:
                    logger.warning(
                        "  [%d/%d] %s:%s — %s → failed",
                        i, len(problems_2), p.platform, p.problem_id, p.title,
                    )

        logger.info("Done! %d/%d analyzed.", stats['solution_ok'], stats['solution_total'])

        # ── Phase 3: Full Solution ──────────────────────────────────
        logger.info("")
        logger.info("=== 阶段 3/4：AI 解题 ===")

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

        problems_3 = query.all()
        stats['full_solution_total'] = len(problems_3)
        logger.info("Found %d problems without full solution%s",
                     len(problems_3), limit_info)

        if dry_run:
            for i, p in enumerate(problems_3, 1):
                logger.info("  [%d/%d] %s:%s — %s", i, len(problems_3),
                            p.platform, p.problem_id, p.title)
        else:
            for i, p in enumerate(problems_3, 1):
                result = analyzer.analyze_problem_full_solution(p.id, user_id=user_id)
                if result:
                    stats['full_solution_ok'] += 1
                    logger.info(
                        "  [%d/%d] %s:%s — %s → OK",
                        i, len(problems_3), p.platform, p.problem_id, p.title,
                    )
                else:
                    logger.warning(
                        "  [%d/%d] %s:%s — %s → failed",
                        i, len(problems_3), p.platform, p.problem_id, p.title,
                    )

        logger.info("Done! %d/%d analyzed.", stats['full_solution_ok'],
                     stats['full_solution_total'])

        # ── Phase 4: Code Review ────────────────────────────────────
        logger.info("")
        logger.info("=== 阶段 4/4：代码审查 ===")

        from sqlalchemy import func as sa_func

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
        query = Submission.query.filter(
            Submission.problem_id_ref.isnot(None),
            Submission.source_code.isnot(None),
            Submission.source_code != '',
            ~Submission.id.in_(reviewed_ids),
        ).order_by(Submission.submitted_at.desc())
        if platform:
            query = query.join(Problem, Submission.problem_id_ref == Problem.id).filter(
                Problem.platform == platform
            )
        if limit:
            query = query.limit(limit)

        all_submissions = query.all()

        # Per-problem cap: at most 3 reviews total (existing + new)
        submissions = []
        key_fn = attrgetter('problem_id_ref')
        for pid, group in groupby(sorted(all_submissions, key=key_fn), key=key_fn):
            existing = reviewed_counts.get(pid, 0)
            if existing >= 3:
                continue
            remaining = 3 - existing
            subs = sorted(group, key=lambda s: s.submitted_at or datetime.min, reverse=True)
            submissions.extend(subs[:remaining])
        stats['review_total'] = len(submissions)
        logger.info("Found %d submissions without review%s",
                     len(submissions), limit_info)

        if dry_run:
            for i, sub in enumerate(submissions, 1):
                prob = sub.problem
                prob_label = f"{prob.platform}:{prob.problem_id}" if prob else "unknown"
                logger.info(
                    "  [%d/%d] %s — submission #%s (%s, %s)",
                    i, len(submissions), prob_label,
                    sub.platform_record_id, sub.status, sub.language or "?",
                )
        else:
            for i, sub in enumerate(submissions, 1):
                prob = sub.problem
                prob_label = f"{prob.platform}:{prob.problem_id}" if prob else "unknown"
                result = analyzer.review_submission(sub.id, user_id=user_id)
                if result:
                    stats['review_ok'] += 1
                    logger.info(
                        "  [%d/%d] %s — submission #%s (%s, %s) → OK",
                        i, len(submissions), prob_label,
                        sub.platform_record_id, sub.status, sub.language or "?",
                    )
                else:
                    logger.warning(
                        "  [%d/%d] %s — submission #%s (%s, %s) → failed",
                        i, len(submissions), prob_label,
                        sub.platform_record_id, sub.status, sub.language or "?",
                    )

        logger.info("Done! %d/%d reviewed.", stats['review_ok'], stats['review_total'])

        # ── Summary ─────────────────────────────────────────────────
        logger.info("")
        if dry_run:
            logger.info("=== 预览完成 (dry-run) ===")
            logger.info(
                "分类: %d | 思路: %d | 解题: %d | 审查: %d",
                stats['classify_total'], stats['solution_total'],
                stats['full_solution_total'], stats['review_total'],
            )
        else:
            logger.info("=== 回填完成 ===")
            logger.info(
                "分类: %d/%d | 思路: %d/%d | 解题: %d/%d | 审查: %d/%d",
                stats['classify_ok'], stats['classify_total'],
                stats['solution_ok'], stats['solution_total'],
                stats['full_solution_ok'], stats['full_solution_total'],
                stats['review_ok'], stats['review_total'],
            )


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
    parser.add_argument('--review', action='store_true',
                        help='Comprehensive backfill: classify + solution + full solution + code review')
    parser.add_argument('--limit', type=int, default=0,
                        help='Max items per phase (0=unlimited, default for --ai: 15)')
    parser.add_argument('--user-id', type=int, default=None,
                        help='User ID whose AI config to use (auto-detects if omitted)')
    args = parser.parse_args()

    if args.review:
        backfill_reviews(
            platform=args.platform,
            limit=args.limit,
            user_id=args.user_id,
            dry_run=args.dry_run,
        )
    elif args.ai:
        ai_limit = args.limit if args.limit else 15
        backfill_ai(platform=args.platform, limit=ai_limit, user_id=args.user_id)
    else:
        backfill(
            platform=args.platform,
            dry_run=args.dry_run,
            refetch=args.refetch,
            remap_all=args.remap_all,
        )
