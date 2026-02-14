from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Generator

import requests

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)

# Luogu status code mapping
_STATUS_MAP = {
    0: SubmissionStatus.PENDING,
    1: SubmissionStatus.JUDGING,
    2: SubmissionStatus.CE,
    3: SubmissionStatus.UNKNOWN,   # Output Limit Exceeded
    4: SubmissionStatus.MLE,
    5: SubmissionStatus.TLE,
    6: SubmissionStatus.WA,
    7: SubmissionStatus.RE,
    11: SubmissionStatus.RE,       # RE variants
    12: SubmissionStatus.AC,
    14: SubmissionStatus.WA,       # Unaccepted (partial)
    21: SubmissionStatus.UNKNOWN,  # Hack Success
    22: SubmissionStatus.UNKNOWN,  # Hack Failure
}

# Luogu difficulty level mapping
_DIFFICULTY_LABELS = {
    0: '暂无评定',
    1: '入门',
    2: '普及-',
    3: '普及/提高-',
    4: '普及+/提高',
    5: '提高+/省选-',
    6: '省选/NOI-',
    7: 'NOI/NOI+',
}

# Reverse lookup: label text to numeric level
_DIFFICULTY_LABEL_TO_LEVEL = {v: k for k, v in _DIFFICULTY_LABELS.items()}


@register_scraper
class LuoguScraper(BaseScraper):
    PLATFORM_NAME = "luogu"
    PLATFORM_DISPLAY = "洛谷"
    BASE_URL = "https://www.luogu.com.cn"
    SUPPORT_CODE_FETCH = True

    # Language ID to name mapping (common ones)
    _LANG_MAP = {
        0: 'Auto',
        1: 'Pascal',
        2: 'C',
        3: 'C++',
        4: 'C++11',
        6: 'Python 2',
        7: 'Python 3',
        8: 'Java 8',
        9: 'Node.js',
        11: 'C++14',
        12: 'C++17',
        14: 'C++20',
        15: 'Go',
        16: 'Rust',
        17: 'PHP',
        21: 'C# Mono',
        22: 'Haskell',
        23: 'Kotlin/JVM',
        25: 'Scala',
        27: 'Perl',
        28: 'PyPy 2',
        29: 'PyPy 3',
    }

    def __init__(self, auth_cookie: str = None, auth_password: str = None, rate_limit: float = 2.0):
        super().__init__(auth_cookie=auth_cookie, auth_password=auth_password, rate_limit=rate_limit)
        # Add the content-only header for JSON responses
        self.session.headers.update({
            'x-lentille-request': 'content-only',
            'Referer': 'https://www.luogu.com.cn/',
        })

    def validate_account(self, platform_uid: str) -> bool:
        """Validate that a Luogu user account exists."""
        try:
            url = f"{self.BASE_URL}/user/{platform_uid}"
            resp = self._rate_limited_get(url)
            data = resp.json()
            # Check that currentData.user exists
            current_data = data.get('currentData', {})
            user = current_data.get('user', None)
            if user and user.get('uid'):
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to validate Luogu account {platform_uid}: {e}")
            return False

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions for a Luogu user, paginated."""
        page = 1
        reached_end = False
        MAX_PAGES = 100

        while not reached_end and page <= MAX_PAGES:
            try:
                url = f"{self.BASE_URL}/record/list?user={platform_uid}&page={page}"
                resp = self._rate_limited_get(url)

                content_type = resp.headers.get('Content-Type', '')
                if 'application/json' not in content_type and 'text/json' not in content_type:
                    self.logger.error(f"Unexpected Content-Type: {content_type} for page {page}")
                    break

                data = resp.json()

                current_data = data.get('currentData', {})
                records_data = current_data.get('records', {})
                records = records_data.get('result', [])

                if not records:
                    break

                for record in records:
                    record_id = str(record.get('id', ''))
                    problem = record.get('problem', {})
                    problem_id = str(problem.get('pid', ''))

                    # If we have a cursor (last seen record ID), stop when we reach it
                    if cursor and record_id == cursor:
                        reached_end = True
                        break

                    # Parse submission time
                    submit_time_epoch = record.get('submitTime', 0)
                    submitted_at = datetime.utcfromtimestamp(submit_time_epoch)

                    # If we have a since datetime, stop fetching older records
                    if since and submitted_at < since:
                        reached_end = True
                        break

                    # Map status
                    raw_status = record.get('status', -1)
                    status = self.map_status(raw_status)

                    # Score
                    score = record.get('score', None)
                    if score is not None:
                        score = int(score)

                    # Language
                    lang_code = record.get('language', None)
                    language = self._LANG_MAP.get(lang_code, str(lang_code) if lang_code is not None else None)

                    # Time and memory
                    time_ms = record.get('time', None)
                    memory_kb = record.get('memory', None)

                    yield ScrapedSubmission(
                        platform_record_id=record_id,
                        problem_id=problem_id,
                        status=status,
                        score=score,
                        language=language,
                        time_ms=int(time_ms) if time_ms is not None else None,
                        memory_kb=int(memory_kb) if memory_kb is not None else None,
                        submitted_at=submitted_at,
                    )

                # Check if there are more pages
                count = records_data.get('count', 0)
                per_page = records_data.get('perPage', 20)
                if per_page <= 0:
                    per_page = 20
                total_pages = (count + per_page - 1) // per_page if count > 0 else 1
                if page >= total_pages:
                    break
                page += 1

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    self.logger.warning(f"Luogu rate limited (429), waiting 30s before retry")
                    time.sleep(30)
                    continue  # Retry the same page
                self.logger.error(f"Error fetching Luogu submissions page {page} for user {platform_uid}: {e}")
                break
            except Exception as e:
                self.logger.error(f"Error fetching Luogu submissions page {page} for user {platform_uid}: {e}")
                break

    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        """Fetch problem details from Luogu."""
        try:
            url = f"{self.BASE_URL}/problem/{problem_id}"
            resp = self._rate_limited_get(url)
            data = resp.json()

            current_data = data.get('currentData', {})
            problem = current_data.get('problem', {})

            if not problem:
                self.logger.warning(f"Problem {problem_id} not found on Luogu")
                return None

            title = problem.get('title', '')
            difficulty_raw_code = problem.get('difficulty', 0)
            difficulty_label = _DIFFICULTY_LABELS.get(difficulty_raw_code, '暂无评定')

            # Tags
            tags = []
            for tag_obj in problem.get('tags', []):
                if isinstance(tag_obj, dict):
                    tags.append(tag_obj.get('name', ''))
                elif isinstance(tag_obj, (int, str)):
                    tags.append(str(tag_obj))

            # Tag names might need resolving from tag IDs; store raw IDs if names unavailable
            tag_names = []
            tag_data = current_data.get('tags', [])
            if tag_data:
                tag_id_to_name = {}
                for t in tag_data:
                    if isinstance(t, dict):
                        tag_id_to_name[t.get('id')] = t.get('name', '')
                # Resolve tags
                for tag_id in problem.get('tags', []):
                    name = tag_id_to_name.get(tag_id)
                    if name:
                        tag_names.append(name)
                    else:
                        tag_names.append(str(tag_id))
            else:
                tag_names = tags

            # Source
            source = problem.get('provider', {}).get('name', '') if isinstance(problem.get('provider'), dict) else None

            # Description content
            description = problem.get('background', '') or ''
            content = problem.get('description', '')
            if content:
                if description:
                    description += '\n\n'
                description += content

            input_desc = problem.get('inputFormat', None)
            output_desc = problem.get('outputFormat', None)

            # Examples
            samples = problem.get('samples', [])
            examples_parts = []
            for i, sample in enumerate(samples):
                if isinstance(sample, (list, tuple)) and len(sample) >= 2:
                    examples_parts.append(f"输入样例 {i + 1}:\n{sample[0]}\n输出样例 {i + 1}:\n{sample[1]}")
            examples = '\n\n'.join(examples_parts) if examples_parts else None

            hint = problem.get('hint', None)

            return ScrapedProblem(
                problem_id=problem_id,
                title=title,
                difficulty_raw=difficulty_label,
                tags=tag_names,
                source=source,
                url=self.get_problem_url(problem_id),
                description=description if description else None,
                input_desc=input_desc,
                output_desc=output_desc,
                examples=examples,
                hint=hint,
            )

        except Exception as e:
            self.logger.error(f"Error fetching Luogu problem {problem_id}: {e}")
            return None

    def fetch_submission_code(self, record_id: str) -> str | None:
        """Fetch source code for a specific submission."""
        try:
            url = f"{self.BASE_URL}/record/{record_id}"
            resp = self._rate_limited_get(url)
            data = resp.json()

            current_data = data.get('currentData', {})
            record = current_data.get('record', {})
            source_code = record.get('sourceCode', None)

            return source_code

        except Exception as e:
            self.logger.error(f"Error fetching Luogu submission code for record {record_id}: {e}")
            return None

    def map_status(self, raw_status) -> str:
        """Map Luogu numeric status code to SubmissionStatus string."""
        if isinstance(raw_status, str):
            try:
                raw_status = int(raw_status)
            except (ValueError, TypeError):
                return SubmissionStatus.UNKNOWN

        status = _STATUS_MAP.get(raw_status, SubmissionStatus.UNKNOWN)
        return status.value if isinstance(status, SubmissionStatus) else str(status)

    def map_difficulty(self, raw_difficulty) -> int:
        """Map Luogu difficulty label or code to numeric level (0-7)."""
        if isinstance(raw_difficulty, int):
            return raw_difficulty if 0 <= raw_difficulty <= 7 else 0
        if isinstance(raw_difficulty, str):
            return _DIFFICULTY_LABEL_TO_LEVEL.get(raw_difficulty, 0)
        return 0

    def get_problem_url(self, problem_id: str) -> str:
        return f"https://www.luogu.com.cn/problem/{problem_id}"

    def get_auth_instructions(self) -> str:
        return "请在浏览器登录洛谷后，F12 → Application → Cookies → 复制 __client_id 和 _uid 的值"
