"""Remove CTOJ objective/quiz problems (MCQ) from the database.

Hydro MCQ problems contain '{{ select(N) }}' template syntax in their
description. These are not programming problems and should not be tracked.

Usage:
    python scripts/cleanup_ctoj_objective.py --dry-run   # preview deletions
    python scripts/cleanup_ctoj_objective.py              # apply deletions
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import create_app
from sqlalchemy import or_

from app.extensions import db
from app.models import Problem, Submission, AnalysisResult
from app.models.tag import problem_tags

# Content fields that may contain MCQ template syntax after Hydro parsing
_CONTENT_FIELDS = [
    Problem.description, Problem.input_desc, Problem.output_desc,
    Problem.examples, Problem.hint,
]


def find_objective_problems():
    """Find CTOJ problems whose content contains MCQ template syntax.

    Checks all content fields since _parse_hydro_content() distributes
    the raw pdoc.content across description, input_desc, output_desc,
    examples, and hint.
    """
    return Problem.query.filter(
        Problem.platform == 'ctoj',
        or_(*(field.like('%{{ select(%') for field in _CONTENT_FIELDS)),
    ).all()


def cleanup(dry_run: bool = True):
    problems = find_objective_problems()

    if not problems:
        print("No CTOJ objective problems found.")
        return

    print(f"Found {len(problems)} CTOJ objective problem(s):\n")
    for p in problems:
        sub_count = Submission.query.filter_by(problem_id_ref=p.id).count()
        ar_count = AnalysisResult.query.filter_by(problem_id_ref=p.id).count()
        print(f"  [{p.problem_id}] {p.title}  "
              f"({sub_count} submissions, {ar_count} analysis results)")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run without --dry-run to delete.")
        return

    total_subs = 0
    total_ar = 0

    for p in problems:
        # Delete submissions referencing this problem
        subs_deleted = Submission.query.filter_by(problem_id_ref=p.id).delete()
        total_subs += subs_deleted

        # AnalysisResults: delete before Problem to avoid cascade conflicts
        ar_deleted = AnalysisResult.query.filter_by(problem_id_ref=p.id).delete()
        total_ar += ar_deleted

        # Clear problem_tags association
        db.session.execute(
            problem_tags.delete().where(problem_tags.c.problem_id == p.id)
        )

        # Delete the problem itself
        db.session.delete(p)

    db.session.commit()

    print(f"\nDeleted:")
    print(f"  {len(problems)} problem(s)")
    print(f"  {total_subs} submission(s)")
    print(f"  {total_ar} analysis result(s)")
    print("Done.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview deletions without applying them')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        cleanup(dry_run=args.dry_run)
