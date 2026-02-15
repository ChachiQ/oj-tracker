from datetime import datetime

from app.extensions import db


class AnalysisResult(db.Model):
    """AI analysis result linked to a specific submission."""

    __tablename__ = 'analysis_result'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer,
        db.ForeignKey('submission.id'),
        nullable=True,
        index=True,
    )
    problem_id_ref = db.Column(
        db.Integer,
        db.ForeignKey('problem.id'),
        nullable=True,
        index=True,
    )
    analysis_type = db.Column(db.String(50), nullable=False)
    result_json = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    error_patterns = db.Column(db.Text, nullable=True)
    suggestions = db.Column(db.Text, nullable=True)
    ai_model = db.Column(db.String(100), nullable=True)
    token_cost = db.Column(db.Integer, nullable=False, default=0)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    analyzed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    submission = db.relationship('Submission', back_populates='analysis_results')
    problem = db.relationship('Problem', back_populates='analysis_results')

    def __repr__(self) -> str:
        return (
            f'<AnalysisResult type={self.analysis_type!r} '
            f'submission_id={self.submission_id}>'
        )
