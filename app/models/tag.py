from app.extensions import db

# Association table for many-to-many Problem <-> Tag relationship.
problem_tags = db.Table(
    'problem_tags',
    db.Column(
        'problem_id',
        db.Integer,
        db.ForeignKey('problem.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    db.Column(
        'tag_id',
        db.Integer,
        db.ForeignKey('tag.id', ondelete='CASCADE'),
        primary_key=True,
    ),
)


class Tag(db.Model):
    """A knowledge-point / algorithm tag that can be attached to problems."""

    __tablename__ = 'tag'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    stage = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    prerequisite_tags = db.Column(db.Text, nullable=True)

    # Relationship to Problem is established via backref in Problem.tags
    problems = db.relationship(
        'Problem', secondary=problem_tags, back_populates='tags', lazy='dynamic'
    )

    def __repr__(self) -> str:
        return f'<Tag {self.name!r}>'
