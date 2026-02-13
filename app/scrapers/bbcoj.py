from __future__ import annotations

import logging
from datetime import datetime
from typing import Generator

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)

# HOJ status code mapping
_STATUS_MAP = {
    0: SubmissionStatus.AC,
    -1: SubmissionStatus.WA,
    -2: SubmissionStatus.TLE,
    -3: SubmissionStatus.MLE,
    -4: SubmissionStatus.RE,
    -5: SubmissionStatus.CE,
    -10: SubmissionStatus.UNKNOWN,   # System Error
    1: SubmissionStatus.PENDING,     # Pending
    2: SubmissionStatus.PENDING,     # Not Submitted
    3: SubmissionStatus.PENDING,     # Submitted Unknown
    4: SubmissionStatus.JUDGING,     # Judging
    5: SubmissionStatus.JUDGING,     # Compiling
    6: SubmissionStatus.PENDING,     # Pending (Rejudge)
    7: SubmissionStatus.JUDGING,     # Judging (Rejudge)
    8: SubmissionStatus.WA,          # Partial Accepted
    9: SubmissionStatus.UNKNOWN,     # Submitting
}

# HOJ language mapping (common)
_LANG_MAP = {
    'C': 'C',
    'C++': 'C++',
    'C++ With O2': 'C++ (O2)',
    'C++ 17': 'C++17',
    'C++ 17 With O2': 'C++17 (O2)',
    'Java': 'Java',
    'Python2': 'Python 2',
    'Python3': 'Python 3',
    'PyPy2': 'PyPy 2',
    'PyPy3': 'PyPy 3',
    'Go': 'Go',
    'C#': 'C#',
    'JavaScript V8': 'JavaScript',
    'JavaScript Node': 'Node.js',
    'PHP': 'PHP',
    'Ruby': 'Ruby',
}


@register_scraper
class BBCOJScraper(BaseScraper):
    PLATFORM_NAME = "bbcoj"
    PLATFORM_DISPLAY = "BBC OJ"
    BASE_URL = "https://www.bbcoj.cn"
    SUPPORT_CODE_FETCH = True

    def __init__(self, auth_cookie: str = None, auth_password: str = None, rate_limit: float = 2.0):
        super().__init__(auth_cookie=auth_cookie, auth_password=auth_password, rate_limit=rate_limit)
        self._logged_in = False
        self._tag_cache = None

    def login(self, username: str, password: str) -> bool:
        """Authenticate with BBC OJ and set up session headers."""
        try:
            url = f"{self.BASE_URL}/api/login"
            payload = {
                'username': username,
                'password': password,
            }
            resp = self._request_with_retry(url, method='POST', json=payload)
            data = resp.json()

            status = data.get('status', None)
            if status != 200:
                msg = data.get('msg', 'Unknown error')
                self.logger.error(f"BBC OJ login failed: {msg}")
                return False

            # Extract JWT token from response
            result = data.get('data', {})
            token = None
            if isinstance(result, dict):
                token = result.get('token', None)

            if not token:
                self.logger.error("BBC OJ login succeeded but no token returned")
                return False

            # Set Authorization header with Bearer token
            self.session.headers['Authorization'] = token

            # JSESSIONID should be set automatically via cookie jar from Set-Cookie
            self._logged_in = True
            self.logger.info(f"BBC OJ login successful for user: {username}")
            return True

        except Exception as e:
            self.logger.error(f"BBC OJ login error: {e}")
            return False

    def _ensure_logged_in(self, platform_uid: str) -> bool:
        """Ensure we are logged in. Attempt login if not already authenticated."""
        if self._logged_in:
            return True

        if not self.auth_password:
            self.logger.error("BBC OJ requires a password for authentication")
            return False

        return self.login(platform_uid, self.auth_password)

    def validate_account(self, platform_uid: str) -> bool:
        """Validate account by attempting to login."""
        return self._ensure_logged_in(platform_uid)

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions for the authenticated BBC OJ user."""
        if not self._ensure_logged_in(platform_uid):
            self.logger.error("Cannot fetch submissions: not logged in")
            return

        page = 1
        limit = 20
        reached_end = False

        while not reached_end:
            try:
                url = (
                    f"{self.BASE_URL}/api/get-submission-list"
                    f"?limit={limit}&currentPage={page}&onlyMine=true"
                )
                resp = self._rate_limited_get(url)
                data = resp.json()

                status = data.get('status', None)
                if status != 200:
                    self.logger.error(f"BBC OJ submission list error: {data.get('msg', 'Unknown')}")
                    break

                result = data.get('data', {})
                records = result.get('records', [])

                if not records:
                    break

                for record in records:
                    submit_id = str(record.get('submitId', ''))

                    # If we have a cursor, stop at the last seen submission
                    if cursor and submit_id == cursor:
                        reached_end = True
                        break

                    # Parse submission time
                    submit_time_str = record.get('submitTime', None)
                    submitted_at = datetime.utcnow()
                    if submit_time_str:
                        try:
                            # HOJ returns ISO-8601 or epoch-style timestamps
                            if isinstance(submit_time_str, str):
                                # Try ISO format first
                                clean_time = submit_time_str.replace('T', ' ').replace('Z', '')
                                if '.' in clean_time:
                                    clean_time = clean_time.split('.')[0]
                                submitted_at = datetime.strptime(clean_time, '%Y-%m-%d %H:%M:%S')
                            elif isinstance(submit_time_str, (int, float)):
                                submitted_at = datetime.utcfromtimestamp(submit_time_str / 1000.0)
                        except (ValueError, TypeError) as e:
                            self.logger.debug(f"Could not parse submit time '{submit_time_str}': {e}")

                    # Check since boundary
                    if since and submitted_at < since:
                        reached_end = True
                        break

                    # Map fields
                    problem_id = str(record.get('displayPid', record.get('pid', '')))
                    raw_status = record.get('status', -10)
                    status_str = self.map_status(raw_status)

                    score = record.get('score', None)
                    if score is not None:
                        score = int(score)

                    language = record.get('language', None)
                    if language and language in _LANG_MAP:
                        language = _LANG_MAP[language]

                    time_ms = record.get('time', None)
                    if time_ms is not None:
                        time_ms = int(time_ms)

                    memory_kb = record.get('memory', None)
                    if memory_kb is not None:
                        memory_kb = int(memory_kb)

                    yield ScrapedSubmission(
                        platform_record_id=submit_id,
                        problem_id=problem_id,
                        status=status_str,
                        score=score,
                        language=language,
                        time_ms=time_ms,
                        memory_kb=memory_kb,
                        submitted_at=submitted_at,
                    )

                # Pagination check
                total = result.get('total', 0)
                if page * limit >= total:
                    break
                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching BBC OJ submissions page {page}: {e}")
                break

    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        """Fetch problem details from BBC OJ."""
        try:
            url = f"{self.BASE_URL}/api/get-problem-detail?problemId={problem_id}"
            resp = self._rate_limited_get(url)
            data = resp.json()

            status = data.get('status', None)
            if status != 200:
                self.logger.warning(f"BBC OJ problem {problem_id} not found: {data.get('msg', '')}")
                return None

            result = data.get('data', {})
            problem = result.get('problem', result)

            title = problem.get('title', '')
            description = problem.get('description', None)
            input_desc = problem.get('input', None)
            output_desc = problem.get('output', None)
            hint = problem.get('hint', None)
            source = problem.get('source', None)
            difficulty_raw = problem.get('difficulty', None)

            # Parse examples
            examples_parts = []
            samples = problem.get('examples', [])
            if isinstance(samples, list):
                for i, sample in enumerate(samples):
                    if isinstance(sample, dict):
                        inp = sample.get('input', '')
                        out = sample.get('output', '')
                        examples_parts.append(f"输入样例 {i + 1}:\n{inp}\n输出样例 {i + 1}:\n{out}")
                    elif isinstance(sample, str):
                        examples_parts.append(sample)
            examples = '\n\n'.join(examples_parts) if examples_parts else None

            # Tags
            tags = []
            tag_list = problem.get('tags', [])
            if isinstance(tag_list, list):
                for tag in tag_list:
                    if isinstance(tag, dict):
                        tags.append(tag.get('name', str(tag.get('id', ''))))
                    elif isinstance(tag, str):
                        tags.append(tag)

            # If tags not in problem, try fetching from tags API
            if not tags:
                tags = self._fetch_problem_tags(problem_id)

            return ScrapedProblem(
                problem_id=problem_id,
                title=title,
                difficulty_raw=str(difficulty_raw) if difficulty_raw is not None else None,
                tags=tags,
                source=source,
                url=self.get_problem_url(problem_id),
                description=description,
                input_desc=input_desc,
                output_desc=output_desc,
                examples=examples,
                hint=hint,
            )

        except Exception as e:
            self.logger.error(f"Error fetching BBC OJ problem {problem_id}: {e}")
            return None

    def _fetch_problem_tags(self, problem_id: str) -> list[str]:
        """Fetch tags for a specific problem from the tags API."""
        try:
            if self._tag_cache is None:
                url = f"{self.BASE_URL}/api/get-problem-tags-and-classification?oj=ME"
                resp = self._rate_limited_get(url)
                data = resp.json()
                if data.get('status') == 200:
                    self._tag_cache = data.get('data', {})
                else:
                    self._tag_cache = {}

            # The tag cache has classification/tag data; matching to problem requires
            # the problem detail to include tag IDs. Return empty if not resolvable.
            return []

        except Exception as e:
            self.logger.debug(f"Error fetching tags: {e}")
            return []

    def fetch_submission_code(self, record_id: str) -> str | None:
        """Fetch source code for a specific submission."""
        try:
            url = f"{self.BASE_URL}/api/get-submission-detail?submitId={record_id}&cid=0"
            resp = self._rate_limited_get(url)
            data = resp.json()

            status = data.get('status', None)
            if status != 200:
                self.logger.warning(f"BBC OJ submission detail error for {record_id}: {data.get('msg', '')}")
                return None

            result = data.get('data', {})
            submission = result.get('submission', result)
            code = submission.get('code', None)

            return code

        except Exception as e:
            self.logger.error(f"Error fetching BBC OJ submission code for {record_id}: {e}")
            return None

    def map_status(self, raw_status) -> str:
        """Map HOJ numeric status code to SubmissionStatus string."""
        if isinstance(raw_status, str):
            try:
                raw_status = int(raw_status)
            except (ValueError, TypeError):
                return SubmissionStatus.UNKNOWN.value

        status = _STATUS_MAP.get(raw_status, SubmissionStatus.UNKNOWN)
        return status.value if isinstance(status, SubmissionStatus) else str(status)

    def map_difficulty(self, raw_difficulty) -> int:
        """Map BBC OJ difficulty to numeric level.

        HOJ typically uses string difficulty labels or numeric levels.
        Maps: 简单=1, 中等=2, 困难=3. Numeric values pass through.
        """
        if isinstance(raw_difficulty, int):
            return raw_difficulty

        if isinstance(raw_difficulty, str):
            difficulty_map = {
                '简单': 1,
                '中等': 2,
                '困难': 3,
                'Easy': 1,
                'Medium': 2,
                'Hard': 3,
            }
            try:
                return int(raw_difficulty)
            except (ValueError, TypeError):
                return difficulty_map.get(raw_difficulty, 0)

        return 0

    def get_problem_url(self, problem_id: str) -> str:
        return f"https://www.bbcoj.cn/problem/{problem_id}"

    def get_auth_instructions(self) -> str:
        return "请输入BBC OJ的用户名和密码，系统会自动登录获取数据"
