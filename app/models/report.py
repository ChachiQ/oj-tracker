import json
from datetime import datetime

from app.extensions import db


class Report(db.Model):
    """Generated report (weekly/monthly) for a student."""

    __tablename__ = 'report'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey('student.id'),
        nullable=False,
        index=True,
    )
    report_type = db.Column(db.String(20), nullable=False)
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False)
    stats_json = db.Column(db.Text, nullable=True)
    ai_content = db.Column(db.Text, nullable=True)
    radar_data_prev = db.Column(db.Text, nullable=True)
    radar_data_curr = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    student = db.relationship('Student')

    def __repr__(self) -> str:
        return (
            f'<Report type={self.report_type!r} '
            f'student_id={self.student_id} '
            f'period={self.period_start}..{self.period_end}>'
        )

    @property
    def content(self):
        return self.ai_content

    @property
    def stats(self):
        if not self.stats_json:
            return {}
        try:
            return json.loads(self.stats_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def prev_scores(self):
        if not self.radar_data_prev:
            return {}
        try:
            return json.loads(self.radar_data_prev)
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def curr_scores(self):
        if not self.radar_data_curr:
            return {}
        try:
            return json.loads(self.radar_data_curr)
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def sections(self):
        return []
