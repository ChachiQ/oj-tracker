from datetime import datetime

from app.extensions import db


class AnalysisLog(db.Model):
    """Periodic analysis log summarising a student's progress over a time window."""

    __tablename__ = 'analysis_log'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey('student.id'),
        nullable=False,
        index=True,
    )
    log_type = db.Column(db.String(20), nullable=False)
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False)
    content = db.Column(db.Text, nullable=True)
    key_findings = db.Column(db.Text, nullable=True)
    error_pattern_stats = db.Column(db.Text, nullable=True)
    improvement_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    student = db.relationship('Student')

    def __repr__(self) -> str:
        return (
            f'<AnalysisLog type={self.log_type!r} '
            f'student_id={self.student_id} '
            f'period={self.period_start}..{self.period_end}>'
        )
