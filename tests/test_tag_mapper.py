"""Tests for TagMapper and SyncService tag-mapping integration."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import Problem, Tag, User, Student, PlatformAccount, Submission
from app.services.tag_mapper import TagMapper, LUOGU_TAG_MAP, BBCOJ_TAG_MAP
from app.services.sync_service import SyncService
from app.scrapers.common import ScrapedSubmission, ScrapedProblem


class TestTagMapper:
    def test_luogu_basic_mapping(self, app, db):
        """'贪心' should map to greedy_basic."""
        tag = Tag(name='greedy_basic', display_name='贪心', category='basic', stage=2)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('luogu')
        result = mapper.map_tags(['贪心'])
        assert len(result) == 1
        assert result[0].name == 'greedy_basic'

    def test_one_to_many_mapping(self, app, db):
        """'排序' should map to both sort_basic and sort_advanced."""
        t1 = Tag(name='sort_basic', display_name='排序(冒泡/选择/插入)',
                 category='basic', stage=2)
        t2 = Tag(name='sort_advanced', display_name='排序(快排/归并)',
                 category='basic', stage=2)
        db.session.add_all([t1, t2])
        db.session.commit()

        mapper = TagMapper('luogu')
        result = mapper.map_tags(['排序'])
        names = [t.name for t in result]
        assert 'sort_basic' in names
        assert 'sort_advanced' in names
        assert len(result) == 2

    def test_unknown_tag_logged_not_crash(self, app, db, caplog):
        """Unrecognised tags should be logged and not cause errors."""
        mapper = TagMapper('luogu')
        result = mapper.map_tags(['不存在的标签XYZ'])
        assert result == []
        assert '不存在的标签XYZ' in caplog.text

    def test_deduplication(self, app, db):
        """Multiple platform tags mapping to the same internal tag are deduplicated."""
        tag = Tag(name='dfs', display_name='DFS深度优先搜索',
                  category='search', stage=3)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('luogu')
        # Both '搜索' and '深搜' map to dfs
        result = mapper.map_tags(['搜索', '深搜'])
        dfs_tags = [t for t in result if t.name == 'dfs']
        assert len(dfs_tags) == 1

    def test_empty_input(self, app, db):
        """Empty list should return empty result."""
        mapper = TagMapper('luogu')
        assert mapper.map_tags([]) == []

    def test_fallback_display_name(self, app, db):
        """When static map has no match, fall back to Tag.display_name."""
        tag = Tag(name='custom_tag', display_name='自定义标签',
                  category='other', stage=1)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('luogu')
        result = mapper.map_tags(['自定义标签'])
        assert len(result) == 1
        assert result[0].name == 'custom_tag'

    def test_fallback_tag_name(self, app, db):
        """When static map has no match, fall back to Tag.name exact match."""
        tag = Tag(name='simulation', display_name='模拟',
                  category='basic', stage=2)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('bbcoj')  # no static map for bbcoj
        result = mapper.map_tags(['simulation'])
        assert len(result) == 1
        assert result[0].name == 'simulation'

    def test_whitespace_stripped(self, app, db):
        """Leading/trailing whitespace in tag names should be stripped."""
        tag = Tag(name='greedy_basic', display_name='贪心', category='basic', stage=2)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('luogu')
        result = mapper.map_tags(['  贪心  '])
        assert len(result) == 1

    def test_empty_string_ignored(self, app, db):
        """Empty strings in tag list should be silently ignored."""
        mapper = TagMapper('luogu')
        result = mapper.map_tags(['', '  '])
        assert result == []

    def test_cache_avoids_repeated_queries(self, app, db):
        """TagMapper caches Tag lookups within a session."""
        tag = Tag(name='greedy_basic', display_name='贪心', category='basic', stage=2)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('luogu')
        mapper.map_tags(['贪心'])
        # Second call should use cache
        assert 'greedy_basic' in mapper._tag_cache
        result = mapper.map_tags(['贪心'])
        assert len(result) == 1

    def test_bbcoj_basic_mapping(self, app, db):
        """BBC OJ '贪心' should map to greedy_basic via BBCOJ_TAG_MAP."""
        tag = Tag(name='greedy_basic', display_name='贪心 Greedy',
                  category='basic', stage=2)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('bbcoj')
        result = mapper.map_tags(['贪心'])
        assert len(result) == 1
        assert result[0].name == 'greedy_basic'

    def test_bbcoj_dp_mapping(self, app, db):
        """BBC OJ '动态规划' should map to dp_linear."""
        tag = Tag(name='dp_linear', display_name='线性DP Linear DP',
                  category='dp', stage=3)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('bbcoj')
        result = mapper.map_tags(['动态规划'])
        assert len(result) == 1
        assert result[0].name == 'dp_linear'

    def test_bbcoj_shortest_path_mapping(self, app, db):
        """BBC OJ graph tags should map correctly."""
        tag = Tag(name='shortest_path', display_name='最短路 Shortest Path',
                  category='graph', stage=4)
        db.session.add(tag)
        db.session.commit()

        mapper = TagMapper('bbcoj')
        for platform_tag in ['最短路', 'Dijkstra', 'SPFA', 'Floyd']:
            mapper_fresh = TagMapper('bbcoj')
            result = mapper_fresh.map_tags([platform_tag])
            assert len(result) == 1, f"Failed for {platform_tag}"
            assert result[0].name == 'shortest_path'

    def test_bbcoj_map_has_entries(self, app, db):
        """BBCOJ_TAG_MAP should not be empty."""
        assert len(BBCOJ_TAG_MAP) > 0


class TestSyncServiceTagMapping:
    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_maps_luogu_tags(self, mock_get_scraper, app, db):
        """After syncing a Luogu submission, the problem should have mapped tags."""
        # Set up tags in DB
        t1 = Tag(name='greedy_basic', display_name='贪心',
                 category='basic', stage=2)
        t2 = Tag(name='dp_linear', display_name='线性DP',
                 category='dp', stage=3)
        db.session.add_all([t1, t2])

        user = User(username='tag_test_user', email='tagtest@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='tag_kid')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='luogu',
            platform_uid='tag_user',
            is_active=True,
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id

        # Mock scraper
        mock_scraper = MagicMock()
        mock_scraper.SUPPORT_CODE_FETCH = False
        mock_scraper.fetch_submissions.return_value = iter([
            ScrapedSubmission(
                platform_record_id='tag_rec_001',
                problem_id='P9001',
                status='AC',
                score=100,
                language='C++',
                submitted_at=datetime.utcnow(),
            ),
        ])
        mock_scraper.fetch_problem.return_value = ScrapedProblem(
            problem_id='P9001',
            title='Tag Test Problem',
            difficulty_raw='3',
            tags=['贪心', '动态规划'],
        )
        mock_scraper.map_difficulty.return_value = 3
        mock_scraper.get_problem_url.return_value = 'https://luogu.com.cn/problem/P9001'
        mock_get_scraper.return_value = mock_scraper

        service = SyncService()
        result = service.sync_account(acct_id)

        assert result['new_submissions'] == 1

        problem = Problem.query.filter_by(
            platform='luogu', problem_id='P9001'
        ).first()
        assert problem is not None
        tag_names = sorted([t.name for t in problem.tags])
        assert 'dp_linear' in tag_names
        assert 'greedy_basic' in tag_names

        # platform_tags should store the raw tags
        assert problem.platform_tags is not None
        raw = json.loads(problem.platform_tags)
        assert '贪心' in raw
        assert '动态规划' in raw

    @patch('app.services.sync_service.get_scraper_instance')
    def test_sync_empty_tags_no_crash(self, mock_get_scraper, app, db):
        """Syncing a problem with no tags should not crash."""
        user = User(username='emptytag_user', email='emptytag@test.com')
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        student = Student(parent_id=user.id, name='emptytag_kid')
        db.session.add(student)
        db.session.flush()
        acct = PlatformAccount(
            student_id=student.id,
            platform='ybt',
            platform_uid='ybt_user',
            is_active=True,
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id

        mock_scraper = MagicMock()
        mock_scraper.SUPPORT_CODE_FETCH = False
        mock_scraper.fetch_submissions.return_value = iter([
            ScrapedSubmission(
                platform_record_id='ybt_001',
                problem_id='1001',
                status='AC',
                submitted_at=datetime.utcnow(),
            ),
        ])
        mock_scraper.fetch_problem.return_value = ScrapedProblem(
            problem_id='1001',
            title='YBT Problem',
            tags=[],
        )
        mock_scraper.map_difficulty.return_value = 0
        mock_scraper.get_problem_url.return_value = 'http://ybt.com/1001'
        mock_get_scraper.return_value = mock_scraper

        service = SyncService()
        result = service.sync_account(acct_id)
        assert result['new_submissions'] == 1

        problem = Problem.query.filter_by(problem_id='1001').first()
        assert problem is not None
        assert len(problem.tags) == 0
