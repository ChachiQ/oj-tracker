"""Tests for analysis engines: AnalysisEngine, WeaknessDetector, TrendAnalyzer."""

import pytest
from datetime import datetime, timedelta

from app.extensions import db
from app.models import (
    User, Student, PlatformAccount, Problem, Submission, Tag,
)
from app.analysis.engine import AnalysisEngine
from app.analysis.weakness import WeaknessDetector, STAGE_EXPECTATIONS, GRADE_STAGE_MAP
from app.analysis.trend import TrendAnalyzer


class TestAnalysisEngine:
    def test_basic_stats(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        stats = engine.get_basic_stats()

        assert stats['total_submissions'] == 3
        assert stats['ac_submissions'] == 2  # sub1 AC, sub3 AC
        assert stats['unique_attempted'] >= 1
        assert stats['unique_solved'] >= 1
        assert 0 <= stats['pass_rate'] <= 100

    def test_basic_stats_no_submissions(self, app, db):
        user = User(username='empty', email='empty@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='empty_kid')
        db.session.add(student)
        db.session.commit()

        engine = AnalysisEngine(student.id)
        stats = engine.get_basic_stats()
        assert stats['total_submissions'] == 0
        assert stats['pass_rate'] == 0

    def test_weekly_stats(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        stats = engine.get_weekly_stats(1)

        assert 'submissions' in stats
        assert 'ac_count' in stats
        assert 'active_days' in stats
        assert 'pass_rate' in stats

    def test_streak_days(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        streak = engine.get_streak_days()
        assert isinstance(streak, int)
        assert streak >= 0

    def test_streak_no_submissions(self, app, db):
        user = User(username='nstreak', email='nstreak@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='ns_kid')
        db.session.add(student)
        db.session.commit()

        engine = AnalysisEngine(student.id)
        assert engine.get_streak_days() == 0

    def test_status_distribution(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        dist = engine.get_status_distribution()
        assert 'AC' in dist
        assert dist['AC'] == 2
        assert dist.get('WA', 0) == 1

    def test_difficulty_distribution(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        dist = engine.get_difficulty_distribution()
        assert isinstance(dist, dict)

    def test_daily_submissions(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        daily = engine.get_daily_submissions(7)
        assert isinstance(daily, list)
        for item in daily:
            assert 'date' in item
            assert 'count' in item

    def test_heatmap_data(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        heatmap = engine.get_heatmap_data(365)
        assert isinstance(heatmap, list)

    def test_tag_scores(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        scores = engine.get_tag_scores()
        assert isinstance(scores, dict)
        if scores:
            for tag_name, info in scores.items():
                assert 'score' in info
                assert 'display_name' in info
                assert 0 <= info['score'] <= 100

    def test_first_ac_rate(self, app, db, sample_data):
        engine = AnalysisEngine(sample_data['student_id'])
        rate = engine.get_first_ac_rate()
        assert isinstance(rate, float)
        assert 0 <= rate <= 100


class TestWeaknessDetector:
    def test_detect_with_data(self, app, db, sample_data):
        detector = WeaknessDetector(sample_data['student_id'])
        weaknesses = detector.detect()
        assert isinstance(weaknesses, list)
        for w in weaknesses:
            assert 'tag_name' in w
            assert 'severity' in w
            assert w['severity'] in ('critical', 'moderate', 'mild')

    def test_detect_no_submissions(self, app, db):
        user = User(username='weak_user', email='weak@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='weak_kid', grade='小五')
        db.session.add(student)

        # Add tags to test against
        tag = Tag(name='test_tag', display_name='测试标签', stage=1, category='基础')
        db.session.add(tag)
        db.session.commit()

        detector = WeaknessDetector(student.id)
        weaknesses = detector.detect()
        assert any(w['severity'] == 'mild' for w in weaknesses)

    def test_get_max_stage(self, app, db):
        user = User(username='stage_user', email='stage@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        student = Student(parent_id=user.id, name='s1', grade='初一')
        db.session.add(student)
        db.session.commit()

        detector = WeaknessDetector(student.id)
        assert detector._get_max_stage() == GRADE_STAGE_MAP['初一']

    def test_get_max_stage_default(self, app, db):
        user = User(username='stage_user2', email='stage2@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()

        student = Student(parent_id=user.id, name='s2')
        db.session.add(student)
        db.session.commit()

        detector = WeaknessDetector(student.id)
        assert detector._get_max_stage() == 4

    def test_critical_weaknesses(self, app, db):
        user = User(username='crit_user', email='crit@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='crit_kid', grade='初一')
        db.session.add(student)
        db.session.commit()

        detector = WeaknessDetector(student.id)
        critical = detector.get_critical_weaknesses()
        assert isinstance(critical, list)
        for w in critical:
            assert w['severity'] == 'critical'

    def test_stage_expectations_valid(self):
        for stage in range(1, 7):
            assert stage in STAGE_EXPECTATIONS
            assert STAGE_EXPECTATIONS[stage] > 0

    def test_grade_stage_map_valid(self):
        expected_grades = ['小三', '小四', '小五', '小六', '初一', '初二', '初三', '高一', '高二', '高三']
        for grade in expected_grades:
            assert grade in GRADE_STAGE_MAP


class TestTrendAnalyzer:
    def test_weekly_trend(self, app, db, sample_data):
        analyzer = TrendAnalyzer(sample_data['student_id'])
        trend = analyzer.get_weekly_trend(12)
        assert isinstance(trend, list)
        for item in trend:
            assert 'week' in item
            assert 'submissions' in item
            assert 'ac_count' in item
            assert 'pass_rate' in item

    def test_monthly_trend(self, app, db, sample_data):
        analyzer = TrendAnalyzer(sample_data['student_id'])
        trend = analyzer.get_monthly_trend(6)
        assert isinstance(trend, list)
        for item in trend:
            assert 'month' in item
            assert 'submissions' in item
            assert 'ac_count' in item

    def test_weekly_trend_no_accounts(self, app, db):
        user = User(username='trend_user', email='trend@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='trend_kid')
        db.session.add(student)
        db.session.commit()

        analyzer = TrendAnalyzer(student.id)
        assert analyzer.get_weekly_trend() == []

    def test_monthly_trend_no_accounts(self, app, db):
        user = User(username='trend_user2', email='trend2@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='trend_kid2')
        db.session.add(student)
        db.session.commit()

        analyzer = TrendAnalyzer(student.id)
        assert analyzer.get_monthly_trend() == []
