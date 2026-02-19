from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Generator

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)

# Hydro status code mapping (from Hydro source status.ts)
_STATUS_MAP = {
    0: SubmissionStatus.PENDING,     # WAITING
    1: SubmissionStatus.AC,          # ACCEPTED
    2: SubmissionStatus.WA,          # WRONG_ANSWER
    3: SubmissionStatus.TLE,         # TIME_LIMIT_EXCEEDED
    4: SubmissionStatus.MLE,         # MEMORY_LIMIT_EXCEEDED
    5: SubmissionStatus.RE,          # OUTPUT_LIMIT_EXCEEDED
    6: SubmissionStatus.RE,          # RUNTIME_ERROR
    7: SubmissionStatus.CE,          # COMPILE_ERROR
    8: SubmissionStatus.UNKNOWN,     # SYSTEM_ERROR
    9: SubmissionStatus.UNKNOWN,     # CANCELED
    20: SubmissionStatus.JUDGING,    # JUDGING
    21: SubmissionStatus.JUDGING,    # COMPILING
    30: SubmissionStatus.UNKNOWN,    # IGNORED
    31: SubmissionStatus.WA,         # FORMAT_ERROR
}


@register_scraper
class CTOJScraper(BaseScraper):
    PLATFORM_NAME = "ctoj"
    PLATFORM_DISPLAY = "CTOJ (酷思未来)"
    BASE_URL = "https://ctoj.ac"
    SUPPORT_CODE_FETCH = True
    REQUIRES_LOGIN = True

    def __init__(self, auth_cookie: str = None, auth_password: str = None, rate_limit: float = 2.0):
        super().__init__(auth_cookie=auth_cookie, auth_password=auth_password, rate_limit=rate_limit)
        self._logged_in = False
        self._domains_cache = None
        # Hydro supports JSON responses via Accept header
        self.session.headers['Accept'] = 'application/json'

    def login(self, username: str, password: str) -> bool:
        """Authenticate with CTOJ via POST /login."""
        try:
            url = f"{self.BASE_URL}/login"
            payload = {
                'uname': username,
                'password': password,
            }
            resp = self._request_with_retry(url, method='POST', json=payload)
            resp.encoding = 'utf-8'
            data = resp.json()

            # Hydro returns url field on success for redirect
            if 'url' in data:
                self._logged_in = True
                self.logger.info(f"CTOJ login successful for user: {username}")
                return True

            # Check for error
            error = data.get('error', '')
            self.logger.error(f"CTOJ login failed: {error}")
            return False

        except Exception as e:
            self.logger.error(f"CTOJ login error ({type(e).__name__}): {e}")
            return False

    def _ensure_logged_in(self, platform_uid: str) -> bool:
        """Ensure we are logged in. Attempt login if not already authenticated."""
        if self._logged_in:
            return True

        if not self.auth_password:
            self.logger.error("CTOJ requires a password for authentication")
            return False

        self.logger.info(f"CTOJ attempting login for user: {platform_uid}")
        return self.login(platform_uid, self.auth_password)

    def _fetch_domains(self) -> list[str]:
        """Fetch all domains the logged-in user belongs to.

        GET /home/domain returns JSON with ddocs array.
        Results are cached for the session lifetime.
        """
        if self._domains_cache is not None:
            return self._domains_cache

        try:
            url = f"{self.BASE_URL}/home/domain"
            resp = self._rate_limited_get(url)
            resp.encoding = 'utf-8'
            data = resp.json()

            ddocs = data.get('ddocs', [])
            domains = []
            for doc in ddocs:
                domain_id = doc.get('_id', '')
                if domain_id:
                    domains.append(domain_id)

            self._domains_cache = domains
            self.logger.info(f"CTOJ found {len(domains)} domains: {domains}")
            return domains

        except Exception as e:
            self.logger.error(f"Error fetching CTOJ domains: {e}")
            self._domains_cache = []
            return []

    def validate_account(self, platform_uid: str) -> bool:
        """Validate account by logging in and checking domain list is non-empty."""
        if not self._ensure_logged_in(platform_uid):
            return False

        domains = self._fetch_domains()
        if not domains:
            self.logger.warning("CTOJ login succeeded but no domains found")
            return False

        return True

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions across all domains for the authenticated user."""
        if not self._ensure_logged_in(platform_uid):
            self.logger.error("Cannot fetch submissions: not logged in")
            return

        domains = self._fetch_domains()
        if not domains:
            self.logger.warning("No domains to fetch submissions from")
            return

        for domain in domains:
            yield from self._fetch_domain_submissions(domain, platform_uid, since, cursor)

    def _fetch_domain_submissions(
        self, domain: str, uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions from a single domain."""
        page = 1
        reached_end = False

        while not reached_end:
            try:
                url = f"{self.BASE_URL}/d/{domain}/record?uidOrName={uid}&page={page}"
                resp = self._rate_limited_get(url)
                resp.encoding = 'utf-8'
                data = resp.json()

                records = data.get('rdocs', [])
                if not records:
                    break

                # Build uid→uname map from udocs if available
                udict = {}
                for udoc in data.get('udocs', []):
                    udict[udoc.get('_id')] = udoc.get('uname', '')

                # Build pid→title map from pdict if available
                pdict = data.get('pdict', {})

                for record in records:
                    # Record ID namespaced by domain
                    rid = str(record.get('_id', ''))
                    record_id = f"{domain}/{rid}"

                    # Filter by user: Hydro returns all records, filter by uid/uname
                    record_uid = record.get('uid', '')
                    record_uname = udict.get(record_uid, '')
                    if str(record_uid) != uid and record_uname != uid:
                        continue

                    # Cursor check
                    if cursor and record_id == cursor:
                        reached_end = True
                        break

                    # Parse submission time
                    submitted_at = datetime.utcnow()
                    judge_at = record.get('judgeAt', None)
                    if judge_at:
                        try:
                            if isinstance(judge_at, str):
                                clean_time = judge_at.replace('T', ' ').replace('Z', '')
                                if '.' in clean_time:
                                    clean_time = clean_time.split('.')[0]
                                submitted_at = datetime.strptime(clean_time, '%Y-%m-%d %H:%M:%S')
                            elif isinstance(judge_at, (int, float)):
                                submitted_at = datetime.utcfromtimestamp(judge_at / 1000.0)
                        except (ValueError, TypeError) as e:
                            self.logger.debug(f"Could not parse judgeAt '{judge_at}': {e}")

                    # Check since boundary
                    if since and submitted_at < since:
                        reached_end = True
                        break

                    # Problem ID namespaced by domain
                    pid = record.get('pid', '')
                    problem_id = f"{domain}/{pid}"

                    # Status
                    raw_status = record.get('status', 8)
                    status_str = self.map_status(raw_status)

                    # Score
                    score = record.get('score', None)
                    if score is not None:
                        score = int(score)

                    # Language
                    language = record.get('lang', None)

                    # Time and memory
                    time_ms = record.get('time', None)
                    if time_ms is not None:
                        time_ms = int(time_ms)

                    memory_kb = record.get('memory', None)
                    if memory_kb is not None:
                        # Hydro returns memory in bytes
                        memory_kb = int(memory_kb) // 1024

                    yield ScrapedSubmission(
                        platform_record_id=record_id,
                        problem_id=problem_id,
                        status=status_str,
                        score=score,
                        language=language,
                        time_ms=time_ms,
                        memory_kb=memory_kb,
                        submitted_at=submitted_at,
                    )

                # Pagination: check if there are more pages
                total_pages = data.get('rpcount', 1)
                if page >= total_pages:
                    break
                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching CTOJ submissions for domain {domain} page {page}: {e}")
                break

    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        """Fetch problem details. problem_id format: {domain}/{pid}."""
        try:
            parts = problem_id.split('/', 1)
            if len(parts) != 2:
                self.logger.warning(f"Invalid CTOJ problem_id format: {problem_id}")
                return None

            domain, pid = parts
            url = f"{self.BASE_URL}/d/{domain}/p/{pid}"
            resp = self._rate_limited_get(url)
            resp.encoding = 'utf-8'
            data = resp.json()

            pdoc = data.get('pdoc', {})
            if not pdoc:
                self.logger.warning(f"CTOJ problem {problem_id} not found")
                return None

            title = pdoc.get('title', '')
            content = pdoc.get('content', '')

            # Parse Hydro markdown content into structured fields
            description, input_desc, output_desc, examples, hint = self._parse_hydro_content(content)

            # Difficulty
            difficulty_raw = pdoc.get('difficulty', None)

            # Tags
            tags = []
            tag_list = pdoc.get('tag', [])
            if isinstance(tag_list, list):
                for tag in tag_list:
                    if isinstance(tag, str):
                        tags.append(tag)

            return ScrapedProblem(
                problem_id=problem_id,
                title=title,
                difficulty_raw=str(difficulty_raw) if difficulty_raw is not None else None,
                tags=tags,
                url=self.get_problem_url(problem_id),
                description=description,
                input_desc=input_desc,
                output_desc=output_desc,
                examples=examples,
                hint=hint,
            )

        except Exception as e:
            self.logger.error(f"Error fetching CTOJ problem {problem_id}: {e}")
            return None

    def _parse_hydro_content(self, content: str) -> tuple[str | None, str | None, str | None, str | None, str | None]:
        """Parse Hydro problem markdown content into structured fields.

        Hydro uses ## headings to separate sections. Common section names:
        题目描述, 输入格式, 输出格式, 样例, 提示/说明
        """
        if not content:
            return None, None, None, None, None

        # Split by ## headings
        sections: dict[str, str] = {}
        current_key = '__description__'
        current_lines: list[str] = []

        for line in content.split('\n'):
            heading_match = re.match(r'^##\s+(.+)', line)
            if heading_match:
                sections[current_key] = '\n'.join(current_lines).strip()
                current_key = heading_match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        sections[current_key] = '\n'.join(current_lines).strip()

        # Map section names to fields
        description = sections.get('__description__', '') or None
        input_desc = None
        output_desc = None
        examples = None
        hint = None

        for key, value in sections.items():
            if not value:
                continue
            key_lower = key.lower()
            if '输入' in key_lower and '格式' in key_lower or key_lower == '输入':
                input_desc = value
            elif '输出' in key_lower and '格式' in key_lower or key_lower == '输出':
                output_desc = value
            elif '样例' in key_lower or 'sample' in key_lower or 'example' in key_lower:
                if examples:
                    examples += '\n\n' + value
                else:
                    examples = value
            elif '提示' in key_lower or '说明' in key_lower or 'hint' in key_lower or 'note' in key_lower:
                hint = value

        return description, input_desc, output_desc, examples, hint

    def fetch_submission_code(self, record_id: str) -> str | None:
        """Fetch source code for a submission. record_id format: {domain}/{rid}."""
        try:
            parts = record_id.split('/', 1)
            if len(parts) != 2:
                self.logger.warning(f"Invalid CTOJ record_id format: {record_id}")
                return None

            domain, rid = parts
            url = f"{self.BASE_URL}/d/{domain}/record/{rid}"
            resp = self._rate_limited_get(url)
            resp.encoding = 'utf-8'
            data = resp.json()

            rdoc = data.get('rdoc', {})
            code = rdoc.get('code', None)
            return code

        except Exception as e:
            self.logger.error(f"Error fetching CTOJ submission code for {record_id}: {e}")
            return None

    def map_status(self, raw_status) -> str:
        """Map Hydro numeric status code to SubmissionStatus string."""
        if isinstance(raw_status, str):
            try:
                raw_status = int(raw_status)
            except (ValueError, TypeError):
                return SubmissionStatus.UNKNOWN.value

        status = _STATUS_MAP.get(raw_status, SubmissionStatus.UNKNOWN)
        return status.value if isinstance(status, SubmissionStatus) else str(status)

    def map_difficulty(self, raw_difficulty) -> int:
        """Map Hydro difficulty (0-10) to project difficulty (0-7).

        Hydro uses 0-10 scale. We linearly map to 0-7.
        """
        if isinstance(raw_difficulty, str):
            try:
                raw_difficulty = int(raw_difficulty)
            except (ValueError, TypeError):
                return 0

        if isinstance(raw_difficulty, (int, float)):
            raw_difficulty = int(raw_difficulty)
            # Map 0-10 to 0-7
            return min(max(round(raw_difficulty * 7 / 10), 0), 7)

        return 0

    def get_problem_url(self, problem_id: str) -> str:
        """Generate problem URL. problem_id format: {domain}/{pid}."""
        parts = problem_id.split('/', 1)
        if len(parts) == 2:
            domain, pid = parts
            return f"{self.BASE_URL}/d/{domain}/p/{pid}"
        return f"{self.BASE_URL}/p/{problem_id}"

    def get_auth_instructions(self) -> str:
        return "请输入CTOJ (酷思未来) 的用户名和密码，系统会自动登录获取数据"
