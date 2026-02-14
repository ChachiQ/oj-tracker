"""Tests for scraper registry, data classes, and enums."""

import pytest
from datetime import datetime

from app.scrapers import get_all_scrapers, get_scraper_class, get_scraper_instance
from app.scrapers.common import ScrapedSubmission, ScrapedProblem, SubmissionStatus


class TestScraperRegistry:
    def test_all_scrapers_registered(self):
        scrapers = get_all_scrapers()
        assert isinstance(scrapers, dict)
        assert len(scrapers) >= 3
        assert 'luogu' in scrapers
        assert 'bbcoj' in scrapers
        assert 'ybt' in scrapers

    def test_get_scraper_class_luogu(self):
        cls = get_scraper_class('luogu')
        assert cls is not None
        assert cls.PLATFORM_NAME == 'luogu'

    def test_get_scraper_class_bbcoj(self):
        cls = get_scraper_class('bbcoj')
        assert cls is not None
        assert cls.PLATFORM_NAME == 'bbcoj'

    def test_get_scraper_class_ybt(self):
        cls = get_scraper_class('ybt')
        assert cls is not None
        assert cls.PLATFORM_NAME == 'ybt'

    def test_get_scraper_class_unknown(self):
        cls = get_scraper_class('nonexistent')
        assert cls is None

    def test_get_scraper_instance(self):
        instance = get_scraper_instance('luogu')
        assert instance is not None
        assert instance.PLATFORM_NAME == 'luogu'

    def test_get_scraper_instance_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            get_scraper_instance('nonexistent')

    def test_scraper_has_required_attributes(self):
        for name, cls in get_all_scrapers().items():
            assert hasattr(cls, 'PLATFORM_NAME')
            assert hasattr(cls, 'PLATFORM_DISPLAY')
            assert hasattr(cls, 'BASE_URL')
            assert cls.PLATFORM_NAME == name

    def test_requires_login_attribute(self):
        scrapers = get_all_scrapers()
        assert scrapers['bbcoj'].REQUIRES_LOGIN is True
        assert scrapers['ybt'].REQUIRES_LOGIN is True
        assert scrapers['luogu'].REQUIRES_LOGIN is False


class TestScrapedSubmission:
    def test_create(self):
        sub = ScrapedSubmission(
            platform_record_id='12345',
            problem_id='P1001',
            status='AC',
            score=100,
            language='C++',
            time_ms=10,
            memory_kb=1024,
        )
        assert sub.platform_record_id == '12345'
        assert sub.problem_id == 'P1001'
        assert sub.status == 'AC'
        assert sub.score == 100
        assert isinstance(sub.submitted_at, datetime)

    def test_defaults(self):
        sub = ScrapedSubmission(
            platform_record_id='99',
            problem_id='P2',
            status='WA',
        )
        assert sub.score is None
        assert sub.language is None
        assert sub.source_code is None


class TestScrapedProblem:
    def test_create(self):
        prob = ScrapedProblem(
            problem_id='P1001',
            title='Test Problem',
            difficulty_raw='3',
            tags=['dp', 'greedy'],
            url='https://example.com/P1001',
        )
        assert prob.problem_id == 'P1001'
        assert prob.title == 'Test Problem'
        assert len(prob.tags) == 2

    def test_defaults(self):
        prob = ScrapedProblem(
            problem_id='P2',
            title='Simple',
        )
        assert prob.tags == []
        assert prob.url == ''
        assert prob.description is None


class TestSubmissionStatus:
    def test_enum_values(self):
        assert SubmissionStatus.AC == 'AC'
        assert SubmissionStatus.WA == 'WA'
        assert SubmissionStatus.TLE == 'TLE'
        assert SubmissionStatus.MLE == 'MLE'
        assert SubmissionStatus.RE == 'RE'
        assert SubmissionStatus.CE == 'CE'
        assert SubmissionStatus.UNKNOWN == 'UNKNOWN'
        assert SubmissionStatus.PENDING == 'PENDING'
        assert SubmissionStatus.JUDGING == 'JUDGING'

    def test_enum_is_str(self):
        assert isinstance(SubmissionStatus.AC, str)
        assert SubmissionStatus.AC == 'AC'

    def test_all_statuses_count(self):
        assert len(SubmissionStatus) == 9
