"""Tests for settings enhancements: platform binding, session conflict management,
AI provider configuration, and UserSetting model.

All AI-related tests use @patch to mock LLM providers — zero real API calls.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    User,
    Student,
    PlatformAccount,
    AnalysisResult,
    Submission,
    Problem,
    UserSetting,
)
from app.scrapers import get_scraper_class, get_all_scrapers


# ──────────────────────────────────────────────
# UserSetting Model
# ──────────────────────────────────────────────

class TestUserSettingModel:
    def test_set_creates_new_record(self, app, db, sample_data):
        uid = sample_data['user_id']
        UserSetting.set(uid, 'ai_provider', 'claude')
        db.session.commit()

        s = UserSetting.query.filter_by(user_id=uid, key='ai_provider').first()
        assert s is not None
        assert s.value == 'claude'

    def test_set_updates_existing_record(self, app, db, sample_data):
        uid = sample_data['user_id']
        UserSetting.set(uid, 'ai_provider', 'claude')
        db.session.commit()

        UserSetting.set(uid, 'ai_provider', 'openai')
        db.session.commit()

        count = UserSetting.query.filter_by(user_id=uid, key='ai_provider').count()
        assert count == 1
        assert UserSetting.get(uid, 'ai_provider') == 'openai'

    def test_get_returns_value(self, app, db, sample_data):
        uid = sample_data['user_id']
        UserSetting.set(uid, 'test_key', 'test_val')
        db.session.commit()

        assert UserSetting.get(uid, 'test_key') == 'test_val'

    def test_get_returns_default_when_missing(self, app, db, sample_data):
        uid = sample_data['user_id']
        assert UserSetting.get(uid, 'nonexistent') is None
        assert UserSetting.get(uid, 'nonexistent', 'fallback') == 'fallback'

    def test_unique_constraint_user_key(self, app, db, sample_data):
        uid = sample_data['user_id']
        s1 = UserSetting(user_id=uid, key='dup_key', value='a')
        s2 = UserSetting(user_id=uid, key='dup_key', value='b')
        db.session.add(s1)
        db.session.flush()
        db.session.add(s2)
        with pytest.raises(IntegrityError):
            db.session.flush()

    def test_multi_user_isolation(self, app, db, sample_data):
        uid_a = sample_data['user_id']

        user_b = User(username='user_b', email='b@test.com')
        user_b.set_password('pw')
        db.session.add(user_b)
        db.session.flush()
        uid_b = user_b.id

        UserSetting.set(uid_a, 'ai_provider', 'claude')
        UserSetting.set(uid_b, 'ai_provider', 'openai')
        db.session.commit()

        assert UserSetting.get(uid_a, 'ai_provider') == 'claude'
        assert UserSetting.get(uid_b, 'ai_provider') == 'openai'


# ──────────────────────────────────────────────
# Platform Binding UI
# ──────────────────────────────────────────────

class TestPlatformBindingUI:
    def test_settings_page_contains_bbcoj_in_dropdown(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert 'bbcoj' in html

    def test_settings_page_contains_ybt_in_dropdown(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert 'ybt' in html

    def test_settings_page_renders_platform_info(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        # Dynamic platform info should include display names from scrapers
        assert 'BBC OJ' in html
        assert '一本通OJ' in html or '一本通' in html

    def test_add_bbcoj_account_with_password(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.post('/settings/account/add', data={
            'student_id': sid,
            'platform': 'bbcoj',
            'platform_uid': 'bbcuser',
            'auth_password': 'secret123',
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            acct = PlatformAccount.query.filter_by(
                student_id=sid, platform='bbcoj'
            ).first()
            assert acct is not None
            assert acct.auth_password == 'secret123'

    def test_add_ybt_account_with_password(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.post('/settings/account/add', data={
            'student_id': sid,
            'platform': 'ybt',
            'platform_uid': 'ybtuser',
            'auth_password': 'ybtpass',
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            acct = PlatformAccount.query.filter_by(
                student_id=sid, platform='ybt'
            ).first()
            assert acct is not None
            assert acct.auth_password == 'ybtpass'

    def test_add_luogu_account_no_password_needed(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.post('/settings/account/add', data={
            'student_id': sid,
            'platform': 'luogu',
            'platform_uid': '999999',
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_last_sync_error_badge(self, app, logged_in_client):
        client, data = logged_in_client
        with app.app_context():
            acct = db.session.get(PlatformAccount, data['account_id'])
            acct.last_sync_error = 'Connection timed out'
            db.session.commit()

        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert '同步异常' in html

    def test_platform_instructions_contain_bbcoj_ybt(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert 'instr-bbcoj' in html
        assert 'instr-ybt' in html

    def test_requires_login_badge_in_instructions(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert '需登录' in html


# ──────────────────────────────────────────────
# Sync Session Conflict
# ──────────────────────────────────────────────

class TestSyncSessionConflict:
    def test_requires_login_bbcoj(self):
        cls = get_scraper_class('bbcoj')
        assert cls is not None
        assert cls.REQUIRES_LOGIN is True

    def test_requires_login_ybt(self):
        cls = get_scraper_class('ybt')
        assert cls is not None
        assert cls.REQUIRES_LOGIN is True

    def test_requires_login_luogu_false(self):
        cls = get_scraper_class('luogu')
        assert cls is not None
        assert cls.REQUIRES_LOGIN is False

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_success_clears_last_sync_error(self, mock_get, app, db, sample_data):
        # Set up a mock scraper that returns no submissions
        mock_scraper = MagicMock()
        mock_scraper.fetch_submissions.return_value = iter([])
        mock_scraper.SUPPORT_CODE_FETCH = False
        mock_get.return_value = mock_scraper

        with app.app_context():
            acct = db.session.get(PlatformAccount, sample_data['account_id'])
            acct.last_sync_error = 'previous error'
            db.session.commit()

            from app.services.sync_service import SyncService
            service = SyncService()
            service.sync_account(sample_data['account_id'])

            acct = db.session.get(PlatformAccount, sample_data['account_id'])
            assert acct.last_sync_error is None

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_failure_writes_last_sync_error(self, mock_get, app, db, sample_data):
        mock_scraper = MagicMock()
        mock_scraper.fetch_submissions.side_effect = RuntimeError('network error')
        mock_get.return_value = mock_scraper

        with app.app_context():
            from app.services.sync_service import SyncService
            service = SyncService()
            stats = service.sync_account(sample_data['account_id'])

            acct = db.session.get(PlatformAccount, sample_data['account_id'])
            assert acct.last_sync_error is not None
            assert 'network error' in acct.last_sync_error

    def test_sync_button_confirm_for_login_platform(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']

        with app.app_context():
            acct = PlatformAccount(
                student_id=sid, platform='bbcoj',
                platform_uid='bbctest', auth_password='pw',
            )
            db.session.add(acct)
            db.session.commit()

        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert 'confirm(' in html


# ──────────────────────────────────────────────
# Scheduler Skip Login
# ──────────────────────────────────────────────

class TestSchedulerSkipLogin:
    @patch('app.services.sync_service.SyncService.sync_account')
    def test_scheduler_skips_requires_login(self, mock_sync, app, db, sample_data):
        with app.app_context():
            sid = sample_data['student_id']
            # Create a bbcoj account (REQUIRES_LOGIN=True)
            bbcoj_acct = PlatformAccount(
                student_id=sid, platform='bbcoj',
                platform_uid='bbctest', auth_password='pw', is_active=True,
            )
            db.session.add(bbcoj_acct)
            db.session.commit()

            # Simulate what the scheduler does
            from app.scrapers import get_scraper_class as gsc
            accounts = PlatformAccount.query.filter_by(is_active=True).all()
            synced = []
            for account in accounts:
                cls = gsc(account.platform)
                if cls and getattr(cls, 'REQUIRES_LOGIN', False):
                    continue
                synced.append(account.platform)

            # bbcoj should NOT be in the synced list; luogu should be
            assert 'bbcoj' not in synced
            assert 'luogu' in synced

    @patch('app.services.sync_service.SyncService.sync_account')
    def test_scheduler_syncs_non_login_platforms(self, mock_sync, app, db, sample_data):
        with app.app_context():
            from app.scrapers import get_scraper_class as gsc
            accounts = PlatformAccount.query.filter_by(is_active=True).all()
            non_login = []
            for account in accounts:
                cls = gsc(account.platform)
                if cls and not getattr(cls, 'REQUIRES_LOGIN', False):
                    non_login.append(account.platform)
            assert len(non_login) > 0

    def test_scheduler_ybt_also_skipped(self, app, db, sample_data):
        with app.app_context():
            sid = sample_data['student_id']
            ybt_acct = PlatformAccount(
                student_id=sid, platform='ybt',
                platform_uid='ybttest', auth_password='pw', is_active=True,
            )
            db.session.add(ybt_acct)
            db.session.commit()

            from app.scrapers import get_scraper_class as gsc
            accounts = PlatformAccount.query.filter_by(is_active=True).all()
            login_platforms = [
                a.platform for a in accounts
                if gsc(a.platform) and getattr(gsc(a.platform), 'REQUIRES_LOGIN', False)
            ]
            assert 'ybt' in login_platforms


# ──────────────────────────────────────────────
# AI Config UI
# ──────────────────────────────────────────────

class TestAIConfigUI:
    def test_settings_page_has_provider_radios(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert 'provider-claude' in html
        assert 'provider-openai' in html
        assert 'provider-zhipu' in html

    def test_settings_page_has_api_key_inputs(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        assert 'api_key_claude' in html
        assert 'api_key_openai' in html
        assert 'api_key_zhipu' in html

    def test_save_ai_config_success(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.post('/settings/ai', data={
            'ai_provider': 'claude',
            'api_key_claude': 'sk-test-key-123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'AI 配置已保存' in html

        with app.app_context():
            uid = data['user_id']
            assert UserSetting.get(uid, 'ai_provider') == 'claude'
            assert UserSetting.get(uid, 'api_key_claude') == 'sk-test-key-123'

    def test_save_ai_config_provider_stored(self, app, logged_in_client):
        client, data = logged_in_client
        client.post('/settings/ai', data={'ai_provider': 'openai'})

        with app.app_context():
            assert UserSetting.get(data['user_id'], 'ai_provider') == 'openai'

    def test_empty_api_key_does_not_overwrite(self, app, logged_in_client):
        client, data = logged_in_client
        uid = data['user_id']

        with app.app_context():
            UserSetting.set(uid, 'api_key_claude', 'existing-key')
            db.session.commit()

        # POST with empty key — should NOT overwrite
        client.post('/settings/ai', data={
            'ai_provider': 'claude',
            'api_key_claude': '',
        })

        with app.app_context():
            assert UserSetting.get(uid, 'api_key_claude') == 'existing-key'

    def test_invalid_provider_rejected(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.post('/settings/ai', data={
            'ai_provider': 'invalid_provider',
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert '无效的 AI 提供者' in html


# ──────────────────────────────────────────────
# AI Analyzer User Config (all mocked)
# ──────────────────────────────────────────────

class TestAIAnalyzerUserConfig:
    @patch('app.analysis.ai_analyzer.get_provider')
    def test_get_llm_reads_user_setting(self, mock_gp, app, db, sample_data):
        uid = sample_data['user_id']
        with app.app_context():
            UserSetting.set(uid, 'ai_provider', 'openai')
            UserSetting.set(uid, 'api_key_openai', 'sk-user-key')
            db.session.commit()

            mock_provider = MagicMock()
            mock_gp.return_value = mock_provider

            from app.analysis.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer(app)
            provider, model = analyzer._get_llm('basic', user_id=uid)

            mock_gp.assert_called_once_with('openai', api_key='sk-user-key')

    @patch('app.analysis.ai_analyzer.get_provider')
    def test_get_llm_falls_back_to_config(self, mock_gp, app, db, sample_data):
        uid = sample_data['user_id']
        with app.app_context():
            # No UserSetting configured
            mock_provider = MagicMock()
            mock_gp.return_value = mock_provider

            from app.analysis.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer(app)
            provider, model = analyzer._get_llm('basic', user_id=uid)

            # Should fall back to app.config AI_PROVIDER (zhipu in testing)
            call_args = mock_gp.call_args
            assert call_args[0][0] == 'zhipu'

    @patch('app.analysis.ai_analyzer.get_provider')
    def test_get_llm_user_config_overrides_env(self, mock_gp, app, db, sample_data):
        uid = sample_data['user_id']
        with app.app_context():
            UserSetting.set(uid, 'ai_provider', 'claude')
            UserSetting.set(uid, 'api_key_claude', 'sk-user-claude')
            db.session.commit()

            mock_provider = MagicMock()
            mock_gp.return_value = mock_provider

            from app.analysis.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer(app)
            provider, model = analyzer._get_llm('basic', user_id=uid)

            mock_gp.assert_called_once_with('claude', api_key='sk-user-claude')

    @patch('app.analysis.ai_analyzer.get_provider')
    def test_get_llm_selects_correct_tier_model(self, mock_gp, app, db, sample_data):
        uid = sample_data['user_id']
        with app.app_context():
            UserSetting.set(uid, 'ai_provider', 'openai')
            UserSetting.set(uid, 'api_key_openai', 'sk-test')
            db.session.commit()

            mock_provider = MagicMock()
            mock_gp.return_value = mock_provider

            from app.analysis.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer(app)

            _, basic_model = analyzer._get_llm('basic', user_id=uid)
            assert basic_model == 'gpt-4.1-mini'

            mock_gp.reset_mock()
            _, advanced_model = analyzer._get_llm('advanced', user_id=uid)
            assert advanced_model == 'gpt-5.2'
