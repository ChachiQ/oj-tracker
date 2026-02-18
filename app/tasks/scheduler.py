import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def init_scheduler(app):
    """Initialize and start the scheduler with app context."""
    if not app.config.get('SCHEDULER_ENABLED', False):
        logger.info("Scheduler disabled by config")
        return

    # Sync all accounts every 6 hours (skip platforms that require login)
    @scheduler.scheduled_job('interval', hours=6, id='sync_all')
    def sync_all_job():
        with app.app_context():
            from app.models import PlatformAccount
            from app.scrapers import get_scraper_class
            from app.services.sync_service import SyncService

            service = SyncService()
            accounts = PlatformAccount.query.filter_by(is_active=True).all()
            skipped = 0
            synced = 0
            for account in accounts:
                cls = get_scraper_class(account.platform)
                if cls and getattr(cls, 'REQUIRES_LOGIN', False):
                    skipped += 1
                    continue
                service.sync_account(account.id)
                synced += 1
            logger.info(
                f"Scheduled sync completed: synced={synced}, "
                f"skipped_login={skipped}"
            )

    # AI analysis batch - daily at 2am
    @scheduler.scheduled_job('cron', hour=2, id='ai_analysis_batch')
    def ai_analysis_job():
        with app.app_context():
            from app.extensions import db
            from app.models import UserSetting, SyncJob
            from app.services.ai_backfill_service import AIBackfillService

            # Auto-discover a user with AI API key configured
            ai_user_id = None
            for key in ('api_key_zhipu', 'api_key_claude', 'api_key_openai'):
                setting = UserSetting.query.filter_by(key=key).filter(
                    UserSetting.value.isnot(None),
                    UserSetting.value != '',
                ).first()
                if setting:
                    ai_user_id = setting.user_id
                    break

            if not ai_user_id:
                logger.info("No user with AI API key found, skipping AI batch")
                return

            # Check no running job for this user
            running = SyncJob.query.filter_by(
                user_id=ai_user_id, status='running'
            ).first()
            if running:
                logger.info(f"User {ai_user_id} already has running job {running.id}, skipping")
                return

            # Create a SyncJob and run backfill
            job = SyncJob(
                user_id=ai_user_id,
                job_type='ai_backfill',
                status='pending',
            )
            db.session.add(job)
            db.session.commit()

            service = AIBackfillService(app)
            service.run(job.id, ai_user_id)
            logger.info(f"Scheduled AI backfill completed: job_id={job.id}")

    # Weekly report - Sunday at 8am
    @scheduler.scheduled_job('cron', day_of_week='sun', hour=8, id='weekly_report')
    def weekly_report_job():
        with app.app_context():
            from app.analysis.report_generator import ReportGenerator
            from app.models import Student

            students = Student.query.all()
            for student in students:
                try:
                    generator = ReportGenerator(student.id, app)
                    report = generator.generate_weekly_report()
                    if report:
                        logger.info(
                            f"Generated weekly report for {student.name}"
                        )
                except Exception as e:
                    logger.error(
                        f"Weekly report failed for {student.name}: {e}"
                    )

    # Monthly report - 1st of month at 9am
    @scheduler.scheduled_job('cron', day=1, hour=9, id='monthly_report')
    def monthly_report_job():
        with app.app_context():
            from app.analysis.report_generator import ReportGenerator
            from app.models import Student

            students = Student.query.all()
            for student in students:
                try:
                    generator = ReportGenerator(student.id, app)
                    report = generator.generate_monthly_report()
                    if report:
                        logger.info(
                            f"Generated monthly report for {student.name}"
                        )
                except Exception as e:
                    logger.error(
                        f"Monthly report failed for {student.name}: {e}"
                    )

    try:
        scheduler.start()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")
