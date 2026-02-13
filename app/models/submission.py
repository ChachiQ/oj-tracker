from datetime import datetime

from app.extensions import db


class Submission(db.Model):
    """A single submission record synced from an online judge platform."""

    __tablename__ = 'submission'
    __table_args__ = (
        db.UniqueConstraint(
            'platform_account_id', 'platform_record_id',
            name='uq_submission_account_record',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    platform_account_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_account.id'),
        nullable=False,
        index=True,
    )
    problem_id_ref = db.Column(
        db.Integer,
        db.ForeignKey('problem.id'),
        nullable=True,
        index=True,
    )
    platform_record_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    score = db.Column(db.Integer, nullable=True)
    language = db.Column(db.String(50), nullable=True)
    time_ms = db.Column(db.Integer, nullable=True)
    memory_kb = db.Column(db.Integer, nullable=True)
    source_code = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    platform_account = db.relationship(
        'PlatformAccount', back_populates='submissions'
    )
    problem = db.relationship('Problem', back_populates='submissions')
    analysis_results = db.relationship(
        'AnalysisResult',
        back_populates='submission',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    def __repr__(self) -> str:
        return (
            f'<Submission {self.platform_record_id} '
            f'status={self.status!r} score={self.score}>'
        )
