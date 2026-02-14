"""Tests for all database models: CRUD, relationships, constraints, and computed properties."""

import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    User,
    Student,
    PlatformAccount,
    Problem,
    Submission,
    Tag,
    AnalysisResult,
    AnalysisLog,
    Report,
)


# ──────────────────────────────────────────────
# User model
# ──────────────────────────────────────────────

class TestUser:
    def test_set_and_check_password(self, app, db):
        user = User(username='alice', email='alice@test.com')
        user.set_password('secret')
        db.session.add(user)
        db.session.commit()

        assert user.check_password('secret')
        assert not user.check_password('wrong')

    def test_unique_username(self, app, db):
        u1 = User(username='bob', email='bob1@test.com')
        u1.set_password('pw')
        db.session.add(u1)
        db.session.commit()

        u2 = User(username='bob', email='bob2@test.com')
        u2.set_password('pw')
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_unique_email(self, app, db):
        u1 = User(username='user1', email='same@test.com')
        u1.set_password('pw')
        db.session.add(u1)
        db.session.commit()

        u2 = User(username='user2', email='same@test.com')
        u2.set_password('pw')
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_user_repr(self, app, db):
        user = User(username='charlie', email='c@test.com')
        user.set_password('pw')
        assert 'charlie' in repr(user)

    def test_user_students_relationship(self, app, db):
        user = User(username='parent', email='p@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        s = Student(parent_id=user.id, name='child')
        db.session.add(s)
        db.session.commit()

        assert user.students.count() == 1
        assert user.students.first().name == 'child'


# ──────────────────────────────────────────────
# Student model
# ──────────────────────────────────────────────

class TestStudent:
    def test_age_with_birthday(self, app, db):
        user = User(username='p1', email='p1@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        # A student born 12 years ago
        bday = date.today().replace(year=date.today().year - 12)
        student = Student(parent_id=user.id, name='kid', birthday=bday)
        db.session.add(student)
        db.session.commit()

        assert student.age == 12

    def test_age_without_birthday(self, app, db):
        user = User(username='p2', email='p2@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        student = Student(parent_id=user.id, name='kid2', birthday=None)
        db.session.add(student)
        db.session.commit()

        assert student.age is None

    def test_age_before_birthday_this_year(self, app, db):
        user = User(username='p3', email='p3@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        # Birthday hasn't happened yet this year
        today = date.today()
        future_month = today.month + 1 if today.month < 12 else 1
        future_year = today.year if today.month < 12 else today.year + 1
        bday = date(future_year - 10, future_month, 15)
        student = Student(parent_id=user.id, name='kid3', birthday=bday)
        db.session.add(student)
        db.session.commit()

        assert student.age == 9

    def test_math_knowledge_stage_from_grade(self, app, db):
        user = User(username='p4', email='p4@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        student = Student(parent_id=user.id, name='kid4', grade='初一')
        db.session.add(student)
        db.session.commit()

        stage = student.math_knowledge_stage
        assert stage is not None
        assert '初中' in stage

    def test_math_knowledge_stage_override(self, app, db):
        user = User(username='p5', email='p5@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        student = Student(
            parent_id=user.id,
            name='kid5',
            grade='初一',
            school_math_level='自定义数学水平',
        )
        db.session.add(student)
        db.session.commit()

        assert student.math_knowledge_stage == '自定义数学水平'

    def test_math_knowledge_stage_no_grade(self, app, db):
        user = User(username='p6', email='p6@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        student = Student(parent_id=user.id, name='kid6')
        db.session.add(student)
        db.session.commit()

        assert student.math_knowledge_stage is None

    def test_math_knowledge_stage_all_grades(self, app, db):
        user = User(username='p7', email='p7@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        grades = ['小三', '小四', '小五', '小六', '初一', '初二', '初三', '高一', '高二', '高三']
        for grade in grades:
            s = Student(parent_id=user.id, name=f'kid_{grade}', grade=grade)
            db.session.add(s)
            db.session.flush()
            assert s.math_knowledge_stage is not None, f"Grade {grade} returned None"


# ──────────────────────────────────────────────
# PlatformAccount model
# ──────────────────────────────────────────────

class TestPlatformAccount:
    def test_create_account(self, app, db, sample_data):
        accts = PlatformAccount.query.filter_by(
            student_id=sample_data['student_id']
        ).all()
        assert len(accts) == 1
        assert accts[0].platform == 'luogu'

    def test_unique_constraint(self, app, db, sample_data):
        dup = PlatformAccount(
            student_id=sample_data['student_id'],
            platform='luogu',
            platform_uid='123456',
        )
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_different_platform_ok(self, app, db, sample_data):
        acc = PlatformAccount(
            student_id=sample_data['student_id'],
            platform='bbcoj',
            platform_uid='123456',
        )
        db.session.add(acc)
        db.session.commit()
        assert acc.id is not None

    def test_last_sync_error_crud(self, app, db, sample_data):
        acct = PlatformAccount.query.get(sample_data['account_id'])
        assert acct.last_sync_error is None

        acct.last_sync_error = 'Connection refused'
        db.session.commit()

        acct = PlatformAccount.query.get(sample_data['account_id'])
        assert acct.last_sync_error == 'Connection refused'

        acct.last_sync_error = None
        db.session.commit()
        acct = PlatformAccount.query.get(sample_data['account_id'])
        assert acct.last_sync_error is None


# ──────────────────────────────────────────────
# Problem model
# ──────────────────────────────────────────────

class TestProblem:
    def test_unique_constraint(self, app, db):
        p1 = Problem(platform='luogu', problem_id='P9999', title='Test')
        db.session.add(p1)
        db.session.commit()

        p2 = Problem(platform='luogu', problem_id='P9999', title='Dup')
        db.session.add(p2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_tags_many_to_many(self, app, db, sample_data):
        prob = Problem.query.filter_by(problem_id='P1002').first()
        assert prob is not None
        tag_names = [t.name for t in prob.tags]
        assert 'greedy' in tag_names
        assert 'dp' in tag_names

    def test_problem_submissions_relationship(self, app, db, sample_data):
        prob = Problem.query.filter_by(problem_id='P1002').first()
        subs = prob.submissions.all()
        assert len(subs) == 2  # WA + AC for P1002


# ──────────────────────────────────────────────
# Submission model
# ──────────────────────────────────────────────

class TestSubmission:
    def test_unique_constraint(self, app, db, sample_data):
        dup = Submission(
            platform_account_id=sample_data['account_id'],
            platform_record_id='rec001',
            status='AC',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_submission_relationships(self, app, db, sample_data):
        sub = Submission.query.filter_by(platform_record_id='rec001').first()
        assert sub is not None
        assert sub.problem is not None
        assert sub.problem.title == 'A+B Problem'
        assert sub.platform_account.platform == 'luogu'


# ──────────────────────────────────────────────
# Tag model
# ──────────────────────────────────────────────

class TestTag:
    def test_tag_fields(self, app, db, sample_data):
        tag = Tag.query.filter_by(name='greedy').first()
        assert tag.display_name == '贪心'
        assert tag.category == '算法'
        assert tag.stage == 2

    def test_tag_prerequisite_json(self, app, db, sample_data):
        tag = Tag.query.filter_by(name='greedy').first()
        prereqs = json.loads(tag.prerequisite_tags)
        assert prereqs == ['simulation']

    def test_tag_unique_name(self, app, db):
        t1 = Tag(name='unique_tag', display_name='唯一标签')
        db.session.add(t1)
        db.session.commit()

        t2 = Tag(name='unique_tag', display_name='重复标签')
        db.session.add(t2)
        with pytest.raises(IntegrityError):
            db.session.commit()


# ──────────────────────────────────────────────
# AnalysisResult model
# ──────────────────────────────────────────────

class TestAnalysisResult:
    def test_crud(self, app, db, sample_data):
        sub_id = sample_data['submission_ids'][0]
        ar = AnalysisResult(
            submission_id=sub_id,
            analysis_type='single',
            result_json='{"quality": "good"}',
            summary='Good solution',
            ai_model='test-model',
            token_cost=100,
            cost_usd=0.01,
        )
        db.session.add(ar)
        db.session.commit()

        fetched = AnalysisResult.query.filter_by(submission_id=sub_id).first()
        assert fetched is not None
        assert fetched.analysis_type == 'single'
        assert fetched.cost_usd == 0.01


# ──────────────────────────────────────────────
# AnalysisLog model
# ──────────────────────────────────────────────

class TestAnalysisLog:
    def test_crud(self, app, db, sample_data):
        log = AnalysisLog(
            student_id=sample_data['student_id'],
            log_type='weekly',
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            content='Weekly summary content',
            key_findings='Found some issues',
        )
        db.session.add(log)
        db.session.commit()

        fetched = AnalysisLog.query.first()
        assert fetched.log_type == 'weekly'
        assert fetched.content == 'Weekly summary content'


# ──────────────────────────────────────────────
# Report model
# ──────────────────────────────────────────────

class TestReport:
    def test_crud(self, app, db, sample_data):
        report = Report(
            student_id=sample_data['student_id'],
            report_type='weekly',
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            stats_json='{"total": 10}',
            ai_content='AI generated report content',
        )
        db.session.add(report)
        db.session.commit()

        fetched = Report.query.first()
        assert fetched.report_type == 'weekly'
        assert fetched.ai_content == 'AI generated report content'
        assert fetched.student.name == '小明'
