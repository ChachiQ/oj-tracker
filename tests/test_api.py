"""Tests for JSON API endpoints."""

import json
import pytest
from app.extensions import db
from app.models import User, Student


class TestDashboardAPI:
    def test_dashboard_data(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/dashboard/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        assert 'basic' in result
        assert 'weekly' in result
        assert 'streak' in result
        assert 'heatmap' in result
        assert 'weekly_trend' in result
        assert 'platform_stats' in result

    def test_dashboard_unauthorized(self, app, db, logged_in_client):
        """Cannot access another user's student dashboard data."""
        client, data = logged_in_client
        with app.app_context():
            other = User(username='other2', email='other2@test.com')
            other.set_password('pw')
            db.session.add(other)
            db.session.flush()
            other_student = Student(parent_id=other.id, name='Other child')
            db.session.add(other_student)
            db.session.commit()
            other_sid = other_student.id

        resp = client.get(f'/api/dashboard/{other_sid}')
        assert resp.status_code == 403


class TestKnowledgeAPI:
    def test_knowledge_data(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/knowledge/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        assert 'nodes' in result
        assert 'links' in result
        assert 'stages' in result

    def test_knowledge_unauthorized(self, app, db, logged_in_client):
        client, data = logged_in_client
        with app.app_context():
            other = User(username='other3', email='other3@test.com')
            other.set_password('pw')
            db.session.add(other)
            db.session.flush()
            other_student = Student(parent_id=other.id, name='Other child 2')
            db.session.add(other_student)
            db.session.commit()
            other_sid = other_student.id

        resp = client.get(f'/api/knowledge/{other_sid}')
        assert resp.status_code == 403

    def test_knowledge_stages_structure(self, app, logged_in_client):
        """API should return stages with learning/weak/tags fields."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/knowledge/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        for stage_key, stage in result['stages'].items():
            assert 'learning' in stage, f'Stage {stage_key} missing learning'
            assert 'weak' in stage, f'Stage {stage_key} missing weak'
            assert 'tags' in stage, f'Stage {stage_key} missing tags'
            assert isinstance(stage['tags'], list)

    def test_knowledge_nodes_have_status(self, app, logged_in_client):
        """API nodes should include status field."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/knowledge/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        for node in result['nodes']:
            assert 'status' in node, f'Node {node.get("id")} missing status'


class TestWeaknessAPI:
    def test_weakness_data(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/weakness/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        assert isinstance(result, list)


class TestTrendAPI:
    def test_trend_data(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/trend/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        assert 'weekly' in result
        assert 'monthly' in result


class TestSubmissionsAPI:
    def test_submissions_data(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/submissions/{sid}')
        assert resp.status_code == 200
        result = resp.get_json()
        assert 'items' in result
        assert 'total' in result
        assert 'page' in result
        assert len(result['items']) == 3

    def test_submissions_pagination(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/submissions/{sid}?per_page=1&page=1')
        assert resp.status_code == 200
        result = resp.get_json()
        assert len(result['items']) == 1
        assert result['total'] == 3

    def test_submissions_filter_status(self, app, logged_in_client):
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/api/submissions/{sid}?status=AC')
        assert resp.status_code == 200
        result = resp.get_json()
        for item in result['items']:
            assert item['status'] == 'AC'


class TestProblemsAPI:
    def test_problems_list(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/api/problems')
        assert resp.status_code == 200
        result = resp.get_json()
        assert 'items' in result
        assert 'total' in result

    def test_problems_filter_platform(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/api/problems?platform=luogu')
        assert resp.status_code == 200
        result = resp.get_json()
        for item in result['items']:
            assert item['platform'] == 'luogu'
