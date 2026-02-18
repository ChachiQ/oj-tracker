"""Tests for v0.3.0 fixes: Dashboard API, knowledge graph, sync_cursor,
consecutive failures, AJAX sync, platform rate limiter, and seed data."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models import PlatformAccount, Submission, Problem, Tag
from app.services.stats_service import StatsService
from app.services.sync_service import SyncService
from app.scrapers.rate_limiter import get_platform_limiter, _platform_limiters


class TestDashboardDataStructure:
    """Step 2: Dashboard API returns correct keys."""

    def test_dashboard_data_has_stats_key(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_dashboard_data(sample_data['student_id'])
            assert 'stats' in data
            stats = data['stats']
            assert 'total_problems' in stats
            assert 'ac_count' in stats
            assert 'week_submissions' in stats
            assert 'streak_days' in stats

    def test_dashboard_data_has_recent_submissions(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_dashboard_data(sample_data['student_id'])
            assert 'recent_submissions' in data
            assert isinstance(data['recent_submissions'], list)

    def test_dashboard_data_has_weaknesses(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_dashboard_data(sample_data['student_id'])
            assert 'weaknesses' in data

    def test_dashboard_data_preserves_backward_compat(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_dashboard_data(sample_data['student_id'])
            assert 'basic' in data
            assert 'weekly' in data
            assert 'streak' in data

    def test_recent_submissions_format(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_dashboard_data(sample_data['student_id'])
            subs = data['recent_submissions']
            if subs:
                sub = subs[0]
                assert 'platform' in sub
                assert 'problem_title' in sub
                assert 'status' in sub
                assert 'submitted_at' in sub


class TestKnowledgeGraphStages:
    """Step 4-5: Knowledge graph returns 'stages' and recommended_problems."""

    def test_knowledge_graph_has_stages_key(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
            assert 'stages' in data
            assert 'nodes' in data
            assert 'links' in data

    def test_knowledge_graph_nodes_have_recommended_problems(self, app, db, sample_data):
        with app.app_context():
            data = StatsService.get_knowledge_graph_data(sample_data['student_id'])
            for node in data['nodes']:
                assert 'recommended_problems' in node
                assert isinstance(node['recommended_problems'], list)


class TestSyncCursorFix:
    """Step 6: sync_cursor stores record_id, not timestamp."""

    def test_sync_cursor_uses_record_id(self, app, db, sample_data):
        with app.app_context():
            account = PlatformAccount.query.get(sample_data['account_id'])

            mock_sub = MagicMock()
            mock_sub.platform_record_id = 'rec_test_123'
            mock_sub.problem_id = 'P1001'  # Use existing problem
            mock_sub.status = 'AC'
            mock_sub.score = 100
            mock_sub.language = 'C++'
            mock_sub.time_ms = None
            mock_sub.memory_kb = None
            mock_sub.source_code = None
            mock_sub.submitted_at = datetime.utcnow()

            mock_scraper = MagicMock()
            mock_scraper.fetch_submissions.return_value = iter([mock_sub])
            mock_scraper.SUPPORT_CODE_FETCH = False
            mock_scraper.fetch_problem.return_value = None

            with patch('app.services.sync_service.get_scraper_instance', return_value=mock_scraper):
                service = SyncService()
                stats = service.sync_account(sample_data['account_id'])

            account = PlatformAccount.query.get(sample_data['account_id'])
            # Should be set to first record ID, not a timestamp
            assert account.sync_cursor == 'rec_test_123'


class TestConsecutiveFailureTracking:
    """Step 7: Failures increment counter, success resets, auto-disable at 10."""

    def test_failure_increments_counter(self, app, db, sample_data):
        with app.app_context():
            account = PlatformAccount.query.get(sample_data['account_id'])
            assert account.consecutive_sync_failures == 0

            mock_scraper = MagicMock()
            mock_scraper.fetch_submissions.side_effect = Exception("Connection error")

            with patch('app.services.sync_service.get_scraper_instance', return_value=mock_scraper):
                service = SyncService()
                service.sync_account(sample_data['account_id'])

            account = PlatformAccount.query.get(sample_data['account_id'])
            assert account.consecutive_sync_failures == 1

    def test_success_resets_counter(self, app, db, sample_data):
        with app.app_context():
            account = PlatformAccount.query.get(sample_data['account_id'])
            account.consecutive_sync_failures = 5
            db.session.commit()

            mock_scraper = MagicMock()
            mock_scraper.fetch_submissions.return_value = iter([])
            mock_scraper.SUPPORT_CODE_FETCH = False

            with patch('app.services.sync_service.get_scraper_instance', return_value=mock_scraper):
                service = SyncService()
                service.sync_account(sample_data['account_id'])

            account = PlatformAccount.query.get(sample_data['account_id'])
            assert account.consecutive_sync_failures == 0

    def test_auto_disable_at_10_failures(self, app, db, sample_data):
        with app.app_context():
            account = PlatformAccount.query.get(sample_data['account_id'])
            account.consecutive_sync_failures = 9
            db.session.commit()

            mock_scraper = MagicMock()
            mock_scraper.fetch_submissions.side_effect = Exception("Connection error")

            with patch('app.services.sync_service.get_scraper_instance', return_value=mock_scraper):
                service = SyncService()
                service.sync_account(sample_data['account_id'])

            account = PlatformAccount.query.get(sample_data['account_id'])
            assert account.consecutive_sync_failures == 10
            assert account.is_active is False


class TestSyncBlueprintJSON:
    """Sync blueprint routes return JSON."""

    def test_sync_content_returns_json(self, app, db, logged_in_client):
        client, data = logged_in_client
        resp = client.post(
            f'/sync/content/{data["account_id"]}',
        )
        assert resp.content_type.startswith('application/json')
        body = resp.get_json()
        assert 'success' in body
        assert 'message' in body

    def test_sync_content_all_returns_json(self, app, db, logged_in_client):
        client, data = logged_in_client
        resp = client.post(
            '/sync/content-all',
        )
        assert resp.content_type.startswith('application/json')
        body = resp.get_json()
        assert 'success' in body
        assert 'stats' in body


class TestPlatformRateLimiter:
    """Step 10: Shared platform rate limiter registry."""

    def test_same_platform_returns_same_instance(self):
        # Clear registry first
        _platform_limiters.clear()
        limiter1 = get_platform_limiter('test_platform', 1.0)
        limiter2 = get_platform_limiter('test_platform', 1.0)
        assert limiter1 is limiter2

    def test_different_platform_returns_different_instance(self):
        _platform_limiters.clear()
        limiter1 = get_platform_limiter('platform_a', 1.0)
        limiter2 = get_platform_limiter('platform_b', 1.0)
        assert limiter1 is not limiter2


class TestSeedDataUpsert:
    """Step 11: seed_tags idempotent — no duplicates."""

    def test_seed_upsert_no_duplicates(self, app, db):
        with app.app_context():
            from seed_data import TAGS

            # Seed once
            for tag_data in TAGS:
                tag = Tag(
                    name=tag_data['name'],
                    display_name=tag_data['display_name'],
                    category=tag_data.get('category', 'other'),
                    stage=tag_data.get('stage', 1),
                    description=tag_data.get('description'),
                    prerequisite_tags=tag_data.get('prerequisite_tags'),
                )
                db.session.add(tag)
            db.session.commit()
            count_first = Tag.query.count()

            # Upsert (simulating seed_tags logic)
            for tag_data in TAGS:
                existing = Tag.query.filter_by(name=tag_data['name']).first()
                if existing:
                    for key, value in tag_data.items():
                        if key != 'name':
                            setattr(existing, key, value)
                else:
                    tag = Tag(
                        name=tag_data['name'],
                        display_name=tag_data['display_name'],
                        category=tag_data.get('category', 'other'),
                        stage=tag_data.get('stage', 1),
                        description=tag_data.get('description'),
                        prerequisite_tags=tag_data.get('prerequisite_tags'),
                    )
                    db.session.add(tag)
            db.session.commit()
            count_second = Tag.query.count()

            assert count_first == count_second

    def test_union_find_is_stage_3(self, app, db):
        """Verify union_find was moved to stage 3."""
        from seed_data import TAGS
        uf = [t for t in TAGS if t['name'] == 'union_find']
        assert len(uf) == 1
        assert uf[0]['stage'] == 3

    def test_new_tags_exist(self, app, db):
        """Verify new tags added in v0.3.0 are in the TAGS list."""
        from seed_data import TAGS
        tag_names = {t['name'] for t in TAGS}
        new_tags = [
            'bit_operation', 'hash_table', 'sliding_window', 'deque',
            'lis', 'meet_in_middle', 'two_sat', 'slope_optimization',
        ]
        for name in new_tags:
            assert name in tag_names, f"Missing new tag: {name}"

    def test_all_tags_have_descriptions(self, app, db):
        """Verify all tags have description fields."""
        from seed_data import TAGS
        for tag_data in TAGS:
            assert 'description' in tag_data and tag_data['description'], \
                f"Tag {tag_data['name']} missing description"
