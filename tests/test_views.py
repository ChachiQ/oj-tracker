"""Tests for all view routes: GET/POST responses and permissions."""

import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import Student, PlatformAccount, Report, User


class TestDashboardView:
    def test_dashboard_no_students(self, auth_client):
        resp = auth_client.get('/dashboard/')
        assert resp.status_code == 200

    def test_dashboard_with_data(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/dashboard/')
        assert resp.status_code == 200

    def test_dashboard_with_student_id(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        assert resp.status_code == 200


class TestStudentViews:
    def test_list_students(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/student/')
        assert resp.status_code == 200

    def test_add_student_get(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/student/add')
        assert resp.status_code == 200

    def test_add_student_post(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.post('/student/add', data={
            'name': '小红',
            'birthday': '2013-03-20',
            'grade': '小四',
            'level': '普及',
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            student = Student.query.filter_by(name='小红').first()
            assert student is not None
            assert student.grade == '小四'

    def test_add_student_no_name(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.post('/student/add', data={
            'name': '',
            'grade': '小四',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '请填写学生姓名' in resp.data.decode('utf-8')

    def test_student_detail(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/student/{sid}')
        assert resp.status_code == 200

    def test_student_detail_other_user(self, app, db, logged_in_client):
        """Cannot view another user's student."""
        client, data = logged_in_client
        with app.app_context():
            other_user = User(username='other', email='other@test.com')
            other_user.set_password('pw')
            db.session.add(other_user)
            db.session.flush()

            other_student = Student(parent_id=other_user.id, name='他的孩子')
            db.session.add(other_student)
            db.session.commit()
            other_sid = other_student.id

        resp = client.get(f'/student/{other_sid}', follow_redirects=True)
        assert resp.status_code == 200
        assert '无权访问' in resp.data.decode('utf-8')

    def test_edit_student_get(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/student/{sid}/edit')
        assert resp.status_code == 200

    def test_edit_student_post(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.post(f'/student/{sid}/edit', data={
            'name': '小明改名',
            'grade': '初一',
            'level': '提高',
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            student = db.session.get(Student, sid)
            assert student.name == '小明改名'
            assert student.grade == '初一'


class TestSettingsViews:
    def test_settings_page(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        assert resp.status_code == 200

    def test_add_account(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.post('/settings/account/add', data={
            'student_id': sid,
            'platform': 'bbcoj',
            'platform_uid': 'user789',
        }, follow_redirects=False)
        assert resp.status_code == 302

        with app.app_context():
            acct = PlatformAccount.query.filter_by(
                student_id=sid, platform='bbcoj'
            ).first()
            assert acct is not None

    def test_add_account_duplicate(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        # The sample_data already has luogu:123456
        resp = client.post('/settings/account/add', data={
            'student_id': sid,
            'platform': 'luogu',
            'platform_uid': '123456',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '该平台账号已存在' in resp.data.decode('utf-8')

    def test_delete_account(self, app, logged_in_client):
        client, data = logged_in_client
        acc_id = data['account_id']
        resp = client.post(f'/settings/account/{acc_id}/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_settings_page_passes_accounts_to_template(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        # The existing luogu account should appear in the page
        assert '123456' in html  # platform_uid from sample_data

    def test_settings_page_passes_analyzed_count(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/settings/')
        html = resp.data.decode('utf-8')
        # analyzed_count should be rendered (0 when no analysis results)
        assert '已分析题目数' in html


class TestKnowledgeViews:
    def test_knowledge_graph(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/knowledge/')
        assert resp.status_code == 200

    def test_knowledge_graph_with_student(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/knowledge/?student_id={sid}')
        assert resp.status_code == 200


class TestReportViews:
    def test_report_list(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/report/')
        assert resp.status_code == 200

    def test_report_list_with_student(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/report/?student_id={sid}')
        assert resp.status_code == 200

    def test_report_detail(self, app, logged_in_client):
        client, data = logged_in_client
        with app.app_context():
            report = Report(
                student_id=data['student_id'],
                report_type='weekly',
                period_start=datetime.utcnow() - timedelta(days=7),
                period_end=datetime.utcnow(),
                stats_json='{}',
                ai_content='Test report',
            )
            db.session.add(report)
            db.session.commit()
            rid = report.id

        resp = client.get(f'/report/{rid}')
        assert resp.status_code == 200


class TestProblemViews:
    def test_problem_list(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/problem/')
        assert resp.status_code == 200

    def test_problem_detail(self, app, logged_in_client):
        client, data = logged_in_client
        pid = data['problem_ids'][0]
        resp = client.get(f'/problem/{pid}')
        assert resp.status_code == 200

    def test_problem_list_with_filters(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/problem/?platform=luogu&difficulty=1')
        assert resp.status_code == 200
