from __future__ import annotations

from datetime import date, datetime

from app.extensions import db

# Mapping from grade strings to approximate math knowledge stages.
# Stages represent cumulative mathematical maturity that informs
# which competitive-programming topics the student can handle.
_GRADE_TO_MATH_STAGE: dict[str, str] = {
    '小三': '小学中段：掌握整数四则运算、初步几何认知',
    '小四': '小学中段：掌握整数四则运算、初步几何认知',
    '小五': '小学高段：分数小数运算、简单方程、面积体积',
    '小六': '小学高段：分数小数运算、简单方程、面积体积',
    '初一': '初中入门：有理数、一元一次方程、几何初步',
    '初二': '初中进阶：二元方程组、勾股定理、函数初步',
    '初三': '初中完整：二次函数、圆、概率统计基础',
    '高一': '高中入门：集合、函数与导数初步、三角函数',
    '高二': '高中进阶：数列、排列组合、圆锥曲线',
    '高三': '高中完整：导数应用、概率与统计、综合运用',
}


class Student(db.Model):
    """A child/student profile managed by a parent User."""

    __tablename__ = 'student'

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False, index=True
    )
    name = db.Column(db.String(80), nullable=False)
    birthday = db.Column(db.Date, nullable=True)
    grade = db.Column(db.String(20), nullable=True)
    school_math_level = db.Column(db.String(200), nullable=True)
    level = db.Column(db.String(20), nullable=False, default='提高')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    parent = db.relationship('User', back_populates='students')
    platform_accounts = db.relationship(
        'PlatformAccount',
        back_populates='student',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def age(self) -> int | None:
        """Return the student's current age in years, or None if birthday is not set."""
        if self.birthday is None:
            return None
        today = date.today()
        years = today.year - self.birthday.year
        if (today.month, today.day) < (self.birthday.month, self.birthday.day):
            years -= 1
        return years

    @property
    def math_knowledge_stage(self) -> str | None:
        """Return an appropriate math-knowledge stage description based on grade.

        If ``school_math_level`` is set it takes precedence as a manual override.
        Otherwise the stage is derived from the ``grade`` field.
        Returns ``None`` when neither grade nor override is available.
        """
        if self.school_math_level:
            return self.school_math_level
        if self.grade:
            return _GRADE_TO_MATH_STAGE.get(self.grade)
        return None

    def __repr__(self) -> str:
        return f'<Student {self.name!r} (id={self.id})>'
