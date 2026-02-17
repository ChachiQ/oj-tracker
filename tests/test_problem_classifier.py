"""Tests for ProblemClassifier with mocked LLM."""

import json
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models import Problem, Tag
from app.analysis.problem_classifier import ProblemClassifier


class TestProblemClassifier:
    def _seed_tags(self):
        """Create a few tags in the DB for testing."""
        tags = [
            Tag(name='dp_linear', display_name='线性DP Linear DP',
                category='dp', stage=3),
            Tag(name='greedy_basic', display_name='贪心 Greedy',
                category='basic', stage=2),
            Tag(name='binary_search', display_name='二分查找 Binary Search',
                category='basic', stage=2),
            Tag(name='simulation', display_name='模拟 Simulation',
                category='basic', stage=2),
        ]
        db.session.add_all(tags)
        db.session.commit()
        return {t.name: t for t in tags}

    def _create_problem(self, **kwargs):
        defaults = dict(
            platform='luogu',
            problem_id='P1000',
            title='Test Problem',
            difficulty=0,
            ai_analyzed=False,
        )
        defaults.update(kwargs)
        p = Problem(**defaults)
        db.session.add(p)
        db.session.commit()
        return p

    def _mock_response(self, content):
        """Build a mock LLM response with token cost attributes."""
        resp = MagicMock()
        resp.content = content
        resp.input_tokens = 100
        resp.output_tokens = 50
        resp.cost = 0.001
        return resp

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_writes_m2m_tags(self, mock_get_provider, app, db):
        """AI classification should write M2M tags to problem.tags."""
        self._seed_tags()
        problem = self._create_problem(
            description='给定一个序列，求最长递增子序列的长度',
        )

        mock_response = self._mock_response(json.dumps({
            "problem_type": "线性DP",
            "knowledge_points": [
                {"tag_name": "dp_linear", "importance": "核心"},
                {"tag_name": "binary_search", "importance": "辅助"},
            ],
            "difficulty_assessment": {
                "thinking": 5,
                "coding": 3,
                "math": 2,
                "overall": 4,
            },
            "brief_solution_idea": "使用动态规划求LIS",
        }))
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        result = classifier.classify_problem(problem.id)

        assert result is True

        # Refresh problem from DB
        p = Problem.query.get(problem.id)
        tag_names = sorted([t.name for t in p.tags])
        assert 'dp_linear' in tag_names
        assert 'binary_search' in tag_names
        assert p.ai_analyzed is True
        assert p.ai_problem_type == '线性DP'

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_writes_difficulty(self, mock_get_provider, app, db):
        """AI classification should set problem.difficulty from overall score."""
        self._seed_tags()
        problem = self._create_problem()

        mock_response = self._mock_response(json.dumps({
            "problem_type": "模拟",
            "knowledge_points": [
                {"tag_name": "simulation", "importance": "核心"},
            ],
            "difficulty_assessment": {
                "thinking": 2,
                "coding": 2,
                "math": 1,
                "overall": 2,
            },
            "brief_solution_idea": "按题意模拟",
        }))
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        result = classifier.classify_problem(problem.id)

        assert result is True
        p = Problem.query.get(problem.id)
        assert p.difficulty == 2

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_skips_already_analyzed(self, mock_get_provider, app, db):
        """Should skip problems already analyzed."""
        problem = self._create_problem(ai_analyzed=True, difficulty=5)

        classifier = ProblemClassifier(app=app)
        result = classifier.classify_problem(problem.id)

        assert result is False
        mock_get_provider.assert_not_called()

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_ignores_unknown_tags(self, mock_get_provider, app, db):
        """Unknown tag_name from AI should be silently ignored."""
        self._seed_tags()
        problem = self._create_problem()

        mock_response = self._mock_response(json.dumps({
            "problem_type": "未知",
            "knowledge_points": [
                {"tag_name": "nonexistent_tag", "importance": "核心"},
                {"tag_name": "greedy_basic", "importance": "核心"},
            ],
            "difficulty_assessment": {"overall": 3},
            "brief_solution_idea": "test",
        }))
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        result = classifier.classify_problem(problem.id)

        assert result is True
        p = Problem.query.get(problem.id)
        tag_names = [t.name for t in p.tags]
        assert 'greedy_basic' in tag_names
        assert 'nonexistent_tag' not in tag_names

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_handles_malformed_json(self, mock_get_provider, app, db):
        """Should handle non-JSON response gracefully."""
        problem = self._create_problem()

        mock_response = self._mock_response("This is not valid JSON at all")
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        result = classifier.classify_problem(problem.id)

        assert result is True
        p = Problem.query.get(problem.id)
        assert p.ai_analyzed is True
        # Should store raw content since parsing failed
        assert p.ai_tags == "This is not valid JSON at all"

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_extracts_json_from_text(self, mock_get_provider, app, db):
        """Should extract JSON even when wrapped in text."""
        self._seed_tags()
        problem = self._create_problem()

        mock_response = self._mock_response(
            'Here is my analysis:\n'
            '```json\n'
            '{"problem_type": "贪心", "knowledge_points": '
            '[{"tag_name": "greedy_basic", "importance": "核心"}], '
            '"difficulty_assessment": {"overall": 3}, '
            '"brief_solution_idea": "贪心策略"}\n'
            '```'
        )
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        result = classifier.classify_problem(problem.id)

        assert result is True
        p = Problem.query.get(problem.id)
        assert 'greedy_basic' in [t.name for t in p.tags]

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_unanalyzed_batch(self, mock_get_provider, app, db):
        """classify_unanalyzed should process multiple problems."""
        self._seed_tags()
        p1 = self._create_problem(problem_id='P1001', title='Problem 1')
        p2 = self._create_problem(problem_id='P1002', title='Problem 2')

        mock_response = self._mock_response(json.dumps({
            "problem_type": "模拟",
            "knowledge_points": [{"tag_name": "simulation", "importance": "核心"}],
            "difficulty_assessment": {"overall": 1},
            "brief_solution_idea": "模拟",
        }))
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        count = classifier.classify_unanalyzed(limit=10)

        assert count == 2

    @patch('app.analysis.problem_classifier.get_provider')
    def test_classify_does_not_duplicate_tags(self, mock_get_provider, app, db):
        """Should not add duplicate M2M tag entries."""
        tags = self._seed_tags()
        problem = self._create_problem()
        # Pre-attach a tag
        problem.tags.append(tags['greedy_basic'])
        db.session.commit()

        mock_response = self._mock_response(json.dumps({
            "problem_type": "贪心",
            "knowledge_points": [
                {"tag_name": "greedy_basic", "importance": "核心"},
            ],
            "difficulty_assessment": {"overall": 3},
            "brief_solution_idea": "贪心",
        }))
        mock_provider = MagicMock()
        mock_provider.chat.return_value = mock_response
        mock_get_provider.return_value = mock_provider

        classifier = ProblemClassifier(app=app)
        classifier.classify_problem(problem.id)

        p = Problem.query.get(problem.id)
        greedy_count = sum(1 for t in p.tags if t.name == 'greedy_basic')
        assert greedy_count == 1
