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
            from app.analysis.ai_analyzer import AIAnalyzer
            from app.analysis.problem_classifier import ProblemClassifier
            from app.models import Submission, AnalysisResult

            # Classify unanalyzed problems
            classifier = ProblemClassifier(app)
            classified = classifier.classify_unanalyzed(limit=20)
            logger.info(f"Classified {classified} problems")

            # Analyze recent non-AC submissions without analysis
            analyzer = AIAnalyzer(app)
            analyzed = 0
            subs = (
                Submission.query.filter(
                    Submission.status != 'AC',
                    Submission.source_code.isnot(None),
                    ~Submission.id.in_(
                        db.session.query(
                            AnalysisResult.submission_id
                        ).filter_by(analysis_type='single_submission')
                    ),
                )
                .order_by(Submission.submitted_at.desc())
                .limit(20)
                .all()
            )

            for sub in subs:
                result = analyzer.analyze_submission(sub.id)
                if result:
                    analyzed += 1
            logger.info(f"Analyzed {analyzed} submissions")

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
