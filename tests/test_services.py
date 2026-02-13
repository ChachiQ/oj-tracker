"""Tests for StatsService and SyncService."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.extensions import db
from app.models import (
    User, Student, PlatformAccount, Problem, Submission, Tag,
)
from app.services.stats_service import StatsService
from app.services.sync_service import SyncService
from app.scrapers.common import ScrapedSubmission, ScrapedProblem


class TestStatsService:
    def test_get_dashboard_data(self, app, db, sample_data):
        data = StatsService.get_dashboard_data(sample_data['student_id'])
        assert 'basic' in data
        assert 'weekly' in data
        assert 'streak' in data
        assert 'status_dist' in data
        assert 'difficulty_dist' in data
        assert 'heatmap' in data
        assert 'tag_scores' in data
        assert 'first_ac_rate' in data

    def test_get_dashboard_data_empty_student(self, app, db):
        user = User(username='dash_user', email='dash@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='dash_kid')
        db.session.add(student)
        db.session.commit()

        data = StatsService.get_dashboard_data(student.id)
        assert data['basic']['total_submissions'] == 0
        assert data['streak'] == 0

    def test_get_knowledge_graph_data(self, app, db, sample_data):
        data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
        assert 'nodes' in data
        assert 'links' in data
        assert 'stages' in data
        assert isinstance(data['nodes'], list)
        assert isinstance(data['links'], list)
        assert isinstance(data['stages'], dict)

    def test_get_weakness_data(self, app, db, sample_data):
        data = StatsService.get_weakness_data(sample_data['student_id'])
        assert isinstance(data, list)

    def test_get_trend_data(self, app, db, sample_data):
        data = StatsService.get_trend_data(sample_data['student_id'])
        assert 'weekly' in data
        assert 'monthly' in data


class TestSyncService:
    def test_sync_account_not_found(self, app, db):
        service = SyncService()
        result = service.sync_account(99999)
        assert 'error' in result

    def test_sync_account_inactive(self, app, db):
        user = User(username='sync_user', email='sync@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='sync_kid')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='luogu',
            platform_uid='inactive_user',
            is_active=False,
        )
        db.session.add(acct)
        db.session.commit()

        service = SyncService()
        result = service.sync_account(acct.id)
        assert 'error' in result

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_account_with_mock_scraper(self, mock_get_scraper, app, db):
        user = User(username='sync2', email='sync2@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='sync_kid2')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='luogu',
            platform_uid='mock_user',
            is_active=True,
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id

        # Set up mock scraper
        mock_scraper = MagicMock()
        mock_scraper.SUPPORT_CODE_FETCH = False

        scraped_subs = [
            ScrapedSubmission(
                platform_record_id='mock_001',
                problem_id='P5000',
                status='AC',
                score=100,
                language='Python',
                submitted_at=datetime.utcnow(),
            ),
        ]
        mock_scraper.fetch_submissions.return_value = iter(scraped_subs)
        mock_scraper.fetch_problem.return_value = ScrapedProblem(
            problem_id='P5000',
            title='Mock Problem',
            difficulty_raw='2',
        )
        mock_scraper.map_difficulty.return_value = 2
        mock_scraper.get_problem_url.return_value = 'https://example.com/P5000'

        mock_get_scraper.return_value = mock_scraper

        service = SyncService()
        result = service.sync_account(acct_id)

        assert result['new_submissions'] == 1
        sub = Submission.query.filter_by(
            platform_record_id='mock_001'
        ).first()
        assert sub is not None
        assert sub.status == 'AC'

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_account_skips_existing(self, mock_get_scraper, app, db):
        user = User(username='sync3', email='sync3@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='sync_kid3')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='luogu',
            platform_uid='dup_user',
            is_active=True,
        )
        db.session.add(acct)
        db.session.flush()

        existing = Submission(
            platform_account_id=acct.id,
            platform_record_id='existing_001',
            status='AC',
            submitted_at=datetime.utcnow(),
        )
        db.session.add(existing)
        db.session.commit()
        acct_id = acct.id

        mock_scraper = MagicMock()
        mock_scraper.SUPPORT_CODE_FETCH = False
        scraped_subs = [
            ScrapedSubmission(
                platform_record_id='existing_001',
                problem_id='P9999',
                status='AC',
                submitted_at=datetime.utcnow(),
            ),
        ]
        mock_scraper.fetch_submissions.return_value = iter(scraped_subs)
        mock_get_scraper.return_value = mock_scraper

        service = SyncService()
        result = service.sync_account(acct_id)
        assert result['new_submissions'] == 0

    def test_sync_all_accounts(self, app, db):
        user = User(username='syncall', email='syncall@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='syncall_kid')
        db.session.add(student)
        db.session.commit()

        service = SyncService()
        result = service.sync_all_accounts(student_id=student.id)
        assert 'accounts_synced' in result
        assert 'total_new_submissions' in result

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_unknown_platform(self, mock_get_scraper, app, db):
        user = User(username='sync_unk', email='syncunk@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='sync_unk_kid')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='unknown_platform',
            platform_uid='user1',
            is_active=True,
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id

        mock_get_scraper.side_effect = ValueError("Unknown platform: unknown_platform")

        service = SyncService()
        result = service.sync_account(acct_id)
        assert 'error' in result
