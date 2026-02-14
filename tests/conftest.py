"""Shared test fixtures for the OJ Tracker test suite."""

import json
from datetime import date, datetime, timedelta

import pytest

from app import create_app
from app.extensions import db as _db
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
    UserSetting,
    problem_tags,
)


@pytest.fixture()
def app():
    """Create a Flask application configured for testing."""
    application = create_app('testing')
    yield application


@pytest.fixture()
def db(app):
    """Provide a clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app, db):
    """Provide a Flask test client."""
    return app.test_client()


@pytest.fixture()
def auth_client(app, db, client):
    """Provide a test client that is already logged in."""
    user = User(username='testuser', email='test@example.com')
    user.set_password('testpass123')
    db.session.add(user)
    db.session.commit()

    # Log in
    client.post('/auth/login', data={
        'username': 'testuser',
        'password': 'testpass123',
    })
    return client


@pytest.fixture()
def sample_data(app, db):
    """Create a full set of sample data for testing.

    Returns a dict of plain IDs (not model objects) so they survive
    across Flask request context boundaries without DetachedInstanceError.
    """
    # User
    user = User(username='testparent', email='parent@test.com')
    user.set_password('password123')
    db.session.add(user)
    db.session.flush()

    # Student
    student = Student(
        parent_id=user.id,
        name='小明',
        birthday=date(2012, 6, 15),
        grade='小五',
        level='提高',
    )
    db.session.add(student)
    db.session.flush()

    # Tags
    tag1 = Tag(
        name='simulation',
        display_name='模拟',
        category='基础',
        stage=1,
        description='模拟题',
        prerequisite_tags=None,
    )
    tag2 = Tag(
        name='greedy',
        display_name='贪心',
        category='算法',
        stage=2,
        description='贪心算法',
        prerequisite_tags=json.dumps(['simulation']),
    )
    tag3 = Tag(
        name='dp',
        display_name='动态规划',
        category='算法',
        stage=3,
        description='动态规划',
        prerequisite_tags=json.dumps(['greedy']),
    )
    db.session.add_all([tag1, tag2, tag3])
    db.session.flush()

    # Platform account
    account = PlatformAccount(
        student_id=student.id,
        platform='luogu',
        platform_uid='123456',
        is_active=True,
    )
    db.session.add(account)
    db.session.flush()

    # Problems
    prob1 = Problem(
        platform='luogu',
        problem_id='P1001',
        title='A+B Problem',
        difficulty=1,
        url='https://www.luogu.com.cn/problem/P1001',
    )
    prob2 = Problem(
        platform='luogu',
        problem_id='P1002',
        title='过河卒',
        difficulty=3,
        url='https://www.luogu.com.cn/problem/P1002',
    )
    db.session.add_all([prob1, prob2])
    db.session.flush()

    # Attach tags to problems
    prob1.tags.append(tag1)
    prob2.tags.append(tag2)
    prob2.tags.append(tag3)

    # Submissions
    now = datetime.utcnow()
    sub1 = Submission(
        platform_account_id=account.id,
        problem_id_ref=prob1.id,
        platform_record_id='rec001',
        status='AC',
        score=100,
        language='C++',
        time_ms=10,
        memory_kb=1024,
        submitted_at=now - timedelta(days=1),
    )
    sub2 = Submission(
        platform_account_id=account.id,
        problem_id_ref=prob2.id,
        platform_record_id='rec002',
        status='WA',
        score=50,
        language='C++',
        time_ms=100,
        memory_kb=2048,
        submitted_at=now - timedelta(hours=12),
    )
    sub3 = Submission(
        platform_account_id=account.id,
        problem_id_ref=prob2.id,
        platform_record_id='rec003',
        status='AC',
        score=100,
        language='C++',
        time_ms=50,
        memory_kb=1536,
        submitted_at=now - timedelta(hours=6),
    )
    db.session.add_all([sub1, sub2, sub3])
    db.session.commit()

    # Return plain IDs — safe across request context boundaries
    return {
        'user_id': user.id,
        'student_id': student.id,
        'account_id': account.id,
        'tag_ids': [tag1.id, tag2.id, tag3.id],
        'problem_ids': [prob1.id, prob2.id],
        'submission_ids': [sub1.id, sub2.id, sub3.id],
    }


@pytest.fixture()
def logged_in_client(app, db, client, sample_data):
    """Provide a client logged in as the sample_data user."""
    client.post('/auth/login', data={
        'username': 'testparent',
        'password': 'password123',
    })
    return client, sample_data
