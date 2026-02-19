"""Tests for scraper registry, data classes, and enums."""

import pytest
from datetime import datetime

from app.scrapers import get_all_scrapers, get_scraper_class, get_scraper_instance
from app.scrapers.common import ScrapedSubmission, ScrapedProblem, SubmissionStatus


class TestScraperRegistry:
    def test_all_scrapers_registered(self):
        scrapers = get_all_scrapers()
        assert isinstance(scrapers, dict)
        assert len(scrapers) >= 4
        assert 'luogu' in scrapers
        assert 'bbcoj' in scrapers
        assert 'ybt' in scrapers
        assert 'ctoj' in scrapers

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

    def test_get_scraper_class_ctoj(self):
        cls = get_scraper_class('ctoj')
        assert cls is not None
        assert cls.PLATFORM_NAME == 'ctoj'
        assert cls.PLATFORM_DISPLAY == 'CTOJ (酷思未来)'
        assert cls.SUPPORT_CODE_FETCH is True
        assert cls.REQUIRES_LOGIN is True

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
        assert scrapers['ctoj'].REQUIRES_LOGIN is True


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


class TestCTOJScraper:
    """Tests for CTOJ (Hydro) scraper logic."""

    @pytest.fixture
    def scraper(self):
        from app.scrapers.ctoj import CTOJScraper
        return CTOJScraper()

    def test_status_mapping(self, scraper):
        """Cover all Hydro status codes."""
        assert scraper.map_status(0) == 'PENDING'    # WAITING
        assert scraper.map_status(1) == 'AC'          # ACCEPTED
        assert scraper.map_status(2) == 'WA'          # WRONG_ANSWER
        assert scraper.map_status(3) == 'TLE'         # TIME_LIMIT_EXCEEDED
        assert scraper.map_status(4) == 'MLE'         # MEMORY_LIMIT_EXCEEDED
        assert scraper.map_status(5) == 'RE'          # OUTPUT_LIMIT_EXCEEDED
        assert scraper.map_status(6) == 'RE'          # RUNTIME_ERROR
        assert scraper.map_status(7) == 'CE'          # COMPILE_ERROR
        assert scraper.map_status(8) == 'UNKNOWN'     # SYSTEM_ERROR
        assert scraper.map_status(9) == 'UNKNOWN'     # CANCELED
        assert scraper.map_status(20) == 'JUDGING'    # JUDGING
        assert scraper.map_status(21) == 'JUDGING'    # COMPILING
        assert scraper.map_status(30) == 'UNKNOWN'    # IGNORED
        assert scraper.map_status(31) == 'WA'         # FORMAT_ERROR
        # Unknown code
        assert scraper.map_status(99) == 'UNKNOWN'
        # String status
        assert scraper.map_status('1') == 'AC'
        assert scraper.map_status('invalid') == 'UNKNOWN'

    def test_difficulty_mapping(self, scraper):
        """Test 0/5/10 boundary mapping from Hydro 0-10 to project 0-7."""
        assert scraper.map_difficulty(0) == 0
        assert scraper.map_difficulty(5) == 4    # round(5*7/10) = round(3.5) = 4
        assert scraper.map_difficulty(10) == 7
        # String input
        assert scraper.map_difficulty('3') == 2  # round(3*7/10) = round(2.1) = 2
        assert scraper.map_difficulty('invalid') == 0
        # Out of range clamped
        assert scraper.map_difficulty(-1) == 0
        assert scraper.map_difficulty(15) == 7

    def test_problem_url(self, scraper):
        """Test problem URL generation with domain/pid format."""
        url = scraper.get_problem_url('LevelA/1')
        assert url == 'https://ctoj.ac/d/LevelA/p/1'

        url2 = scraper.get_problem_url('CSP2024/P1234')
        assert url2 == 'https://ctoj.ac/d/CSP2024/p/P1234'

    def test_parse_hydro_content_standard(self, scraper):
        """Test parsing standard Hydro markdown with ## sections."""
        content = """这是题目描述

## 输入格式
第一行一个整数 n

## 输出格式
输出答案

## 样例
输入：1
输出：1

## 提示
注意边界条件"""

        desc, inp, out, examples, hint = scraper._parse_hydro_content(content)
        assert desc == '这是题目描述'
        assert inp == '第一行一个整数 n'
        assert out == '输出答案'
        assert examples == '输入：1\n输出：1'
        assert hint == '注意边界条件'

    def test_parse_hydro_content_no_sections(self, scraper):
        """Test parsing content with no ## headings."""
        content = "这是一道简单的题目，没有分节"
        desc, inp, out, examples, hint = scraper._parse_hydro_content(content)
        assert desc == '这是一道简单的题目，没有分节'
        assert inp is None
        assert out is None
        assert examples is None
        assert hint is None

    def test_parse_hydro_content_empty(self, scraper):
        """Test parsing empty content."""
        desc, inp, out, examples, hint = scraper._parse_hydro_content('')
        assert desc is None
        assert inp is None
        assert out is None
        assert examples is None
        assert hint is None
