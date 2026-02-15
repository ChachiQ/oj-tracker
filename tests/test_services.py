"""Tests for StatsService and SyncService."""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.extensions import db
from app.models import (
    User, Student, PlatformAccount, Problem, Submission, Tag, AnalysisResult,
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
        assert 'weekly_trend' in data
        assert 'platform_stats' in data

    def test_get_dashboard_data_empty_student(self, app, db):
        user = User(username='dash_user', email='dash@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='dash_kid')
        db.session.add(student)
        db.session.commit()

        data = StatsService.get_dashboard_data(student.id)
        assert isinstance(data, dict)
        assert data['stats']['total_problems'] == 0
        assert data['streak'] == 0
        assert data['weekly_trend'] == []
        assert data['platform_stats'] == []

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

    def test_dashboard_total_problems_semantics(self, app, db, sample_data):
        """stats.total_problems should equal basic.unique_attempted."""
        data = StatsService.get_dashboard_data(sample_data['student_id'])
        assert data['stats']['total_problems'] == data['basic']['unique_attempted']

    def test_dashboard_weekly_trend(self, app, db, sample_data):
        """weekly_trend should be a list with expected fields."""
        data = StatsService.get_dashboard_data(sample_data['student_id'])
        assert isinstance(data['weekly_trend'], list)
        for item in data['weekly_trend']:
            assert 'week' in item
            assert 'submissions' in item
            assert 'ac_count' in item
            assert 'pass_rate' in item

    def test_dashboard_platform_stats(self, app, db, sample_data):
        """platform_stats should contain per-platform data including luogu."""
        data = StatsService.get_dashboard_data(sample_data['student_id'])
        assert isinstance(data['platform_stats'], list)
        for item in data['platform_stats']:
            assert 'platform' in item
            assert 'submissions' in item
            assert 'ac_count' in item
            assert 'pass_rate' in item
        # sample_data uses luogu platform
        platforms = [item['platform'] for item in data['platform_stats']]
        assert 'luogu' in platforms
        luogu = [item for item in data['platform_stats'] if item['platform'] == 'luogu'][0]
        assert luogu['submissions'] == 3
        assert luogu['ac_count'] == 2

    def test_knowledge_graph_efficiency_metrics(self, app, db, sample_data):
        """Knowledge graph nodes should include first_ac_rate and avg_attempts."""
        data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
        for node in data['nodes']:
            assert 'first_ac_rate' in node
            assert 'avg_attempts' in node
            assert node['first_ac_rate'] >= 0
            assert node['avg_attempts'] >= 0

    def test_knowledge_graph_stages_have_learning_weak(self, app, db, sample_data):
        """Stages dict should include learning and weak counts."""
        data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
        for stage_num, stage in data['stages'].items():
            assert 'learning' in stage, f'Stage {stage_num} missing learning count'
            assert 'weak' in stage, f'Stage {stage_num} missing weak count'
            assert 'tags' in stage, f'Stage {stage_num} missing tags list'

    def test_knowledge_graph_stages_tags_list(self, app, db, sample_data):
        """Each stage should have a 'tags' list with expected fields."""
        data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
        for stage_num, stage in data['stages'].items():
            assert isinstance(stage['tags'], list), \
                f'Stage {stage_num} tags should be a list'
            for tag in stage['tags']:
                assert 'name' in tag, f'Tag in stage {stage_num} missing name'
                assert 'display_name' in tag, f'Tag in stage {stage_num} missing display_name'
                assert 'status' in tag, f'Tag in stage {stage_num} missing status'
                assert 'score' in tag, f'Tag in stage {stage_num} missing score'

    def test_knowledge_graph_node_has_status_field(self, app, db, sample_data):
        """Each node should have a 'status' field."""
        data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
        valid_statuses = {'mastered', 'learning', 'weak', 'untouched'}
        for node in data['nodes']:
            assert 'status' in node, f'Node {node.get("id")} missing status field'
            assert node['status'] in valid_statuses, \
                f'Node {node.get("id")} has invalid status: {node["status"]}'


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

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_triggers_auto_analysis(self, mock_get_scraper, app, db):
        """Sync should call _analyze_new_content when new items are found."""
        user = User(username='sync_auto', email='syncauto@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='auto_kid')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='luogu',
            platform_uid='auto_user',
            is_active=True,
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id

        mock_scraper = MagicMock()
        mock_scraper.SUPPORT_CODE_FETCH = False
        scraped_subs = [
            ScrapedSubmission(
                platform_record_id='auto_001',
                problem_id='P6000',
                status='AC',
                score=100,
                language='C++',
                source_code='#include <iostream>\nint main(){}',
                submitted_at=datetime.utcnow(),
            ),
        ]
        mock_scraper.fetch_submissions.return_value = iter(scraped_subs)
        mock_scraper.fetch_problem.return_value = ScrapedProblem(
            problem_id='P6000',
            title='Auto Problem',
            description='A test problem.',
            difficulty_raw='1',
        )
        mock_scraper.map_difficulty.return_value = 1
        mock_scraper.get_problem_url.return_value = 'https://example.com/P6000'
        mock_get_scraper.return_value = mock_scraper

        service = SyncService()
        with patch.object(service, '_analyze_new_content') as mock_analyze:
            result = service.sync_account(acct_id)
            assert result['new_submissions'] == 1
            mock_analyze.assert_called_once()

    def test_analyze_new_content_skips_existing(self, app, db, sample_data):
        """_analyze_new_content should skip problems already analyzed."""
        pid = sample_data['problem_ids'][0]
        # Pre-create an existing analysis
        existing = AnalysisResult(
            problem_id_ref=pid,
            analysis_type="problem_solution",
            result_json='{"approach":"test"}',
            analyzed_at=datetime.utcnow(),
        )
        db.session.add(existing)
        db.session.commit()

        service = SyncService()
        with patch('app.analysis.ai_analyzer.AIAnalyzer') as MockAnalyzer:
            mock_instance = MockAnalyzer.return_value
            mock_instance.analyze_problem_solution.return_value = None
            mock_instance.review_submission.return_value = None
            service._analyze_new_content(
                sample_data['account_id'],
                user_id=sample_data['user_id'],
            )
            # Should not call analyze_problem_solution for already-analyzed problem
            for call_args in mock_instance.analyze_problem_solution.call_args_list:
                assert call_args[0][0] != pid
