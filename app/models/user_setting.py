from app.extensions import db


class UserSetting(db.Model):
    """Key-value store for per-user configuration (AI provider, API keys, etc.)."""

    __tablename__ = 'user_setting'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'key', name='uq_user_setting_user_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False, index=True
    )
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref='settings')

    @staticmethod
    def get(user_id, key, default=None):
        """Read a single setting value, returning *default* if not found."""
        s = UserSetting.query.filter_by(user_id=user_id, key=key).first()
        return s.value if s else default

    @staticmethod
    def set(user_id, key, value):
        """Create or update a setting. Caller must commit the session."""
        s = UserSetting.query.filter_by(user_id=user_id, key=key).first()
        if s:
            s.value = value
        else:
            s = UserSetting(user_id=user_id, key=key, value=value)
            db.session.add(s)

    def __repr__(self) -> str:
        return f'<UserSetting user_id={self.user_id} key={self.key!r}>'
