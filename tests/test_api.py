"""Tests for JSON API endpoints."""

import json
import pytest
from unittest.mock import patch, MagicMock
from app.extensions import db
from app.models import User, Student, Problem, Submission, PlatformAccount, AnalysisResult


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


class TestProblemSolutionAPI:
    def test_problem_solution_success(self, app, logged_in_client):
        client, data = logged_in_client
        pid = data['problem_ids'][0]

        mock_result = MagicMock()
        mock_result.result_json = json.dumps({"approach": "test approach"})
        mock_result.analyzed_at = MagicMock()
        mock_result.analyzed_at.strftime.return_value = "2026-02-15 12:00"
        mock_result.ai_model = "test-model"

        with patch('app.analysis.ai_analyzer.AIAnalyzer') as MockAnalyzer:
            MockAnalyzer.return_value.analyze_problem_comprehensive.return_value = {
                'classify': MagicMock(), 'solution': mock_result, 'full_solution': MagicMock(),
            }
            resp = client.post(f'/api/problem/{pid}/solution')

        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True
        assert result['analysis']['approach'] == 'test approach'

    def test_problem_solution_unauthorized(self, app, db, logged_in_client):
        """Cannot analyze a problem the user has no submissions for."""
        client, data = logged_in_client
        # Create a problem the user has no submissions for
        with app.app_context():
            prob = Problem(platform='luogu', problem_id='P9999', title='Other')
            db.session.add(prob)
            db.session.commit()
            pid = prob.id

        resp = client.post(f'/api/problem/{pid}/solution')
        assert resp.status_code == 403

    def test_problem_full_solution_success(self, app, logged_in_client):
        client, data = logged_in_client
        pid = data['problem_ids'][0]

        mock_result = MagicMock()
        mock_result.result_json = json.dumps({
            "approach": "dp approach",
            "code": "#include <iostream>",
        })
        mock_result.analyzed_at = MagicMock()
        mock_result.analyzed_at.strftime.return_value = "2026-02-15 12:00"
        mock_result.ai_model = "test-model"

        with patch('app.analysis.ai_analyzer.AIAnalyzer') as MockAnalyzer:
            MockAnalyzer.return_value.analyze_problem_comprehensive.return_value = {
                'classify': MagicMock(), 'solution': MagicMock(), 'full_solution': mock_result,
            }
            resp = client.post(f'/api/problem/{pid}/full-solution')

        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True
        assert 'code' in result['analysis']

    def test_problem_solution_force_refresh(self, app, logged_in_client):
        client, data = logged_in_client
        pid = data['problem_ids'][0]

        mock_result = MagicMock()
        mock_result.result_json = json.dumps({"approach": "refreshed"})
        mock_result.analyzed_at = MagicMock()
        mock_result.analyzed_at.strftime.return_value = "2026-02-15 12:00"
        mock_result.ai_model = "test-model"

        with patch('app.analysis.ai_analyzer.AIAnalyzer') as MockAnalyzer:
            MockAnalyzer.return_value.analyze_problem_comprehensive.return_value = {
                'classify': MagicMock(), 'solution': mock_result, 'full_solution': MagicMock(),
            }
            resp = client.post(f'/api/problem/{pid}/solution?force=1')
            assert resp.status_code == 200
            MockAnalyzer.return_value.analyze_problem_comprehensive.assert_called_once_with(
                pid, force=True, user_id=data['user_id'],
            )


class TestSubmissionReviewAPI:
    def test_submission_review_success(self, app, db, logged_in_client):
        client, data = logged_in_client

        # Add source code to a submission
        with app.app_context():
            sub = Submission.query.get(data['submission_ids'][0])
            sub.source_code = '#include <iostream>\nint main() { return 0; }'
            db.session.commit()

        mock_result = MagicMock()
        mock_result.result_json = json.dumps({
            "approach_analysis": "student used brute force",
            "code_quality": "良好",
            "mastery_level": "掌握",
        })
        mock_result.analyzed_at = MagicMock()
        mock_result.analyzed_at.strftime.return_value = "2026-02-15 12:00"
        mock_result.ai_model = "test-model"

        with patch('app.analysis.ai_analyzer.AIAnalyzer') as MockAnalyzer:
            MockAnalyzer.return_value.review_submission.return_value = mock_result
            sub_id = data['submission_ids'][0]
            resp = client.post(f'/api/submission/{sub_id}/review')

        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True
        assert result['analysis']['code_quality'] == '良好'

    def test_submission_review_no_code(self, app, logged_in_client):
        """Cannot review a submission without source code."""
        client, data = logged_in_client
        sub_id = data['submission_ids'][0]
        # sample_data submissions have no source_code by default
        resp = client.post(f'/api/submission/{sub_id}/review')
        assert resp.status_code == 400

    def test_submission_review_unauthorized(self, app, db, logged_in_client):
        """Cannot review another user's submission."""
        client, data = logged_in_client

        with app.app_context():
            other = User(username='other_rev', email='other_rev@test.com')
            other.set_password('pw')
            db.session.add(other)
            db.session.flush()
            other_student = Student(parent_id=other.id, name='Other kid')
            db.session.add(other_student)
            db.session.flush()
            other_acct = PlatformAccount(
                student_id=other_student.id,
                platform='luogu',
                platform_uid='other_uid',
                is_active=True,
            )
            db.session.add(other_acct)
            db.session.flush()
            from datetime import datetime
            other_sub = Submission(
                platform_account_id=other_acct.id,
                platform_record_id='other_rec001',
                status='AC',
                source_code='int main(){}',
                submitted_at=datetime.utcnow(),
            )
            db.session.add(other_sub)
            db.session.commit()
            other_sub_id = other_sub.id

        resp = client.post(f'/api/submission/{other_sub_id}/review')
        assert resp.status_code == 403

    def test_submission_review_not_found(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.post('/api/submission/99999/review')
        assert resp.status_code == 404
