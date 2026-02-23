"""Backfill UNKNOWN submission statuses for YBT platform.

All UNKNOWN YBT submissions were caused by missing Chinese status mappings
('部分正确' and '答案正确') in _RESULT_STATUS_MAP.  AC submissions were
already correctly mapped via the English "Accepted" text, so every remaining
UNKNOWN is '部分正确' → WA.

Usage:
    python backfill_ybt_status.py            # fix all UNKNOWN YBT submissions
    python backfill_ybt_status.py --dry-run  # preview without writing
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import PlatformAccount, Submission

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Backfill UNKNOWN YBT submission statuses')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        unknown_subs = (
            Submission.query
            .join(PlatformAccount)
            .filter(
                PlatformAccount.platform == 'ybt',
                Submission.status == 'UNKNOWN',
            )
            .all()
        )

        if not unknown_subs:
            logger.info('No UNKNOWN YBT submissions found. Nothing to do.')
            return

        logger.info(f'Found {len(unknown_subs)} UNKNOWN YBT submissions.')

        for sub in unknown_subs:
            action = '[DRY RUN] Would update' if args.dry_run else 'Updating'
            logger.info(
                f'  {action} submission {sub.id} (record {sub.platform_record_id}): '
                f'UNKNOWN -> WA (score={sub.score})'
            )
            if not args.dry_run:
                sub.status = 'WA'

        if not args.dry_run:
            db.session.commit()
            logger.info(f'Done. Updated {len(unknown_subs)} submissions to WA.')
        else:
            logger.info(f'Dry run complete. Would update {len(unknown_subs)} submissions.')


if __name__ == '__main__':
    main()
