from datetime import datetime

from app.extensions import db
from .tag import problem_tags


class Problem(db.Model):
    """A competitive-programming problem sourced from an online judge."""

    __tablename__ = 'problem'
    __table_args__ = (
        db.UniqueConstraint(
            'platform', 'problem_id',
            name='uq_problem_platform_problem_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(50), nullable=False, index=True)
    problem_id = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    input_desc = db.Column(db.Text, nullable=True)
    output_desc = db.Column(db.Text, nullable=True)
    examples = db.Column(db.Text, nullable=True)
    hint = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.Integer, nullable=False, default=0)
    difficulty_raw = db.Column(db.String(50), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    source = db.Column(db.String(200), nullable=True)
    platform_tags = db.Column(db.Text, nullable=True)  # JSON: raw tags from scraper
    ai_tags = db.Column(db.Text, nullable=True)
    ai_problem_type = db.Column(db.String(200), nullable=True)
    ai_analyzed = db.Column(db.Boolean, nullable=False, default=False)
    ai_analysis_error = db.Column(db.String(500), nullable=True)
    ai_retry_count = db.Column(db.Integer, nullable=False, default=0)
    last_scanned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    tags = db.relationship(
        'Tag', secondary=problem_tags, back_populates='problems', lazy='select'
    )
    submissions = db.relationship(
        'Submission', back_populates='problem', lazy='dynamic'
    )
    analysis_results = db.relationship(
        'AnalysisResult', back_populates='problem',
        cascade='all, delete-orphan', lazy='dynamic',
    )

    def __repr__(self) -> str:
        return f'<Problem {self.platform}:{self.problem_id} {self.title!r}>'
