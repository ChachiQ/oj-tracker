from datetime import datetime

from app.extensions import db


class PlatformAccount(db.Model):
    """Credentials and sync state for a student's account on an OJ platform."""

    __tablename__ = 'platform_account'
    __table_args__ = (
        db.UniqueConstraint(
            'student_id', 'platform', 'platform_uid',
            name='uq_platform_account_student_platform_uid',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey('student.id'), nullable=False, index=True
    )
    platform = db.Column(db.String(50), nullable=False)
    platform_uid = db.Column(db.String(100), nullable=False)
    auth_cookie = db.Column(db.Text, nullable=True)
    auth_password = db.Column(db.Text, nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    sync_cursor = db.Column(db.String(200), nullable=True)
    last_analysis_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    student = db.relationship('Student', back_populates='platform_accounts')
    submissions = db.relationship(
        'Submission',
        back_populates='platform_account',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    def __repr__(self) -> str:
        return (
            f'<PlatformAccount {self.platform}:{self.platform_uid} '
            f'(student_id={self.student_id})>'
        )
