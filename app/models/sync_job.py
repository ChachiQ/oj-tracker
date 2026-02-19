import json
import logging
from datetime import datetime, timedelta

from app.extensions import db

logger = logging.getLogger(__name__)


class SyncJob(db.Model):
    """Tracks sync and AI backfill job execution history."""

    __tablename__ = 'sync_job'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False, index=True
    )
    job_type = db.Column(db.String(30), nullable=False)  # content_sync | ai_backfill
    status = db.Column(
        db.String(20), nullable=False, default='pending'
    )  # pending | running | completed | failed
    platform_account_id = db.Column(
        db.Integer, db.ForeignKey('platform_account.id'),
        nullable=True, index=True,
    )
    current_phase = db.Column(db.String(50), nullable=True)
    progress_current = db.Column(db.Integer, nullable=False, default=0)
    progress_total = db.Column(db.Integer, nullable=False, default=0)
    stats_json = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    user = db.relationship('User', backref=db.backref('sync_jobs', lazy='dynamic'))
    platform_account = db.relationship(
        'PlatformAccount',
        backref=db.backref('sync_jobs', lazy='dynamic'),
    )

    @property
    def duration_seconds(self):
        """Calculate job duration in seconds."""
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds())
        if self.started_at:
            return int((datetime.utcnow() - self.started_at).total_seconds())
        return None

    @property
    def stats(self):
        """Parse stats_json into dict."""
        if self.stats_json:
            try:
                return json.loads(self.stats_json)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @stats.setter
    def stats(self, value):
        """Serialize dict to stats_json."""
        self.stats_json = json.dumps(value, ensure_ascii=False) if value else None

    @classmethod
    def cleanup_stale_running(cls, max_age_hours=6):
        """Mark long-running jobs as failed.

        Jobs stuck in 'running' status longer than *max_age_hours* are
        assumed to be stale (e.g. the process was killed) and are marked
        as 'failed' so they no longer block new jobs.

        Returns the number of jobs cleaned up.
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        stale_jobs = cls.query.filter(
            cls.status == 'running',
            cls.started_at < cutoff,
        ).all()

        for job in stale_jobs:
            job.status = 'failed'
            job.error_message = '任务超时，已自动标记为失败（进程可能被终止）'
            job.finished_at = datetime.utcnow()
            logger.warning(
                f'Cleaned up stale SyncJob {job.id} '
                f'(started_at={job.started_at})'
            )

        if stale_jobs:
            db.session.commit()

        return len(stale_jobs)

    def __repr__(self):
        return (
            f'<SyncJob {self.id} type={self.job_type} '
            f'status={self.status}>'
        )
