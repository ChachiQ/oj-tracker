from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Generator
from urllib.parse import unquote

import requests

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)


class LuoguSessionExpired(Exception):
    """Raised when Luogu cookies are missing or expired."""
    pass


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
    14: SubmissionStatus.PA,       # Unaccepted (partial)
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
    REQUIRES_LOGIN = True
    AUTH_METHOD = 'cookie'

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

    _EMBEDDED_JSON_RE = re.compile(r'decodeURIComponent\("([^"]+)"\)')

    def __init__(self, auth_cookie: str = None, auth_password: str = None, rate_limit: float = 2.0):
        # Normalize cookie: strip "Cookie:" prefix if user pasted from DevTools
        if auth_cookie:
            auth_cookie = auth_cookie.strip()
            if auth_cookie.lower().startswith('cookie:'):
                auth_cookie = auth_cookie[7:].strip()
        super().__init__(auth_cookie=auth_cookie, auth_password=auth_password, rate_limit=rate_limit)
        self._tag_cache: dict[int, str] | None = None
        # Luogu needs cookies in the jar (not header) for authenticated sessions.
        # Move auth_cookie from header to jar.
        if self.auth_cookie:
            self.session.headers.pop('Cookie', None)
            for part in self.auth_cookie.split(';'):
                part = part.strip()
                if '=' in part:
                    k, v = part.split('=', 1)
                    self.session.cookies.set(k.strip(), v.strip(), domain='.luogu.com.cn')
        self.session.headers.update({
            'x-lentille-request': 'content-only',
            'Referer': 'https://www.luogu.com.cn/',
        })

    def _parse_response(self, resp: requests.Response) -> dict:
        """Parse Luogu response — JSON directly or embedded JSON in HTML."""
        ct = resp.headers.get('Content-Type', '')
        if 'application/json' in ct:
            return resp.json()
        # Authenticated responses return HTML with embedded JSON
        m = self._EMBEDDED_JSON_RE.search(resp.text)
        if m:
            return json.loads(unquote(m.group(1)))
        raise ValueError(f"Cannot parse Luogu response (Content-Type: {ct})")

    def _check_auth_response(self, response_json: dict):
        """Raise LuoguSessionExpired if the response is a login redirect."""
        if response_json.get('instance') == 'auth':
            raise LuoguSessionExpired(
                "Cookie 已过期或未设置，请更新洛谷 Cookie"
            )

    def _extract_data(self, response_json: dict) -> dict:
        """Extract the main data payload from Luogu API response.

        Handles both the new ('data') and legacy ('currentData') response structures.
        """
        if 'data' in response_json:
            return response_json['data']
        if 'currentData' in response_json:
            return response_json['currentData']
        return {}

    def _get_tag_map(self) -> dict[int, str]:
        """Fetch and cache the Luogu tag ID-to-name mapping from /_lfe/tags/zh-CN."""
        if self._tag_cache is not None:
            return self._tag_cache

        try:
            url = f"{self.BASE_URL}/_lfe/tags/zh-CN"
            resp = self._rate_limited_get(url)
            tags_list = resp.json().get('tags', [])
            self._tag_cache = {
                t['id']: t['name']
                for t in tags_list
                if isinstance(t, dict) and 'id' in t and 'name' in t
            }
            self.logger.info(f"Loaded {len(self._tag_cache)} Luogu tags")
        except Exception as e:
            self.logger.error(f"Failed to fetch Luogu tag mapping: {e}")
            self._tag_cache = {}

        return self._tag_cache

    def validate_account(self, platform_uid: str) -> bool:
        """Validate that a Luogu user account exists and cookies are valid."""
        # If cookies are provided, validate via authenticated record list endpoint.
        # This also implicitly proves the user exists.
        if self.auth_cookie:
            rec_url = f"{self.BASE_URL}/record/list?user={platform_uid}&page=1"
            rec_resp = self._rate_limited_get(rec_url)
            rec_data = self._parse_response(rec_resp)
            if rec_data.get('instance') == 'auth':
                self.logger.warning("Luogu cookie validation failed — session expired")
                return False
            return True

        # No cookies — verify UID via public user profile
        url = f"{self.BASE_URL}/user/{platform_uid}"
        resp = self._rate_limited_get(url)
        data = self._parse_response(resp)
        current_data = self._extract_data(data)
        user = current_data.get('user', None)
        return bool(user and user.get('uid'))

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None,
        problem_id: str = None,
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions for a Luogu user, paginated."""
        page = 1
        reached_end = False
        MAX_PAGES = 100

        while not reached_end and page <= MAX_PAGES:
            try:
                url = f"{self.BASE_URL}/record/list?user={platform_uid}&page={page}"
                resp = self._rate_limited_get(url)
                data = self._parse_response(resp)
                self._check_auth_response(data)

                current_data = self._extract_data(data)
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

                    # Refine: Luogu status 14 ("Unaccepted") with score 0 is WA, not PA
                    if status == SubmissionStatus.PA.value and score == 0:
                        status = SubmissionStatus.WA.value

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

            except LuoguSessionExpired:
                raise
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

            current_data = self._extract_data(data)
            problem = current_data.get('problem', {})

            if not problem:
                self.logger.warning(f"Problem {problem_id} not found on Luogu")
                return None

            title = problem.get('title', '')
            difficulty_raw_code = problem.get('difficulty', 0)
            difficulty_label = _DIFFICULTY_LABELS.get(difficulty_raw_code, '暂无评定')

            # Tags: resolve integer IDs to names via /_lfe/tags endpoint
            raw_tags = problem.get('tags', [])
            tag_names = []
            if raw_tags and all(isinstance(t, int) for t in raw_tags):
                tag_map = self._get_tag_map()
                tag_names = [tag_map.get(t, str(t)) for t in raw_tags]
            elif raw_tags and all(isinstance(t, dict) for t in raw_tags):
                tag_names = [t.get('name', str(t.get('id', ''))) for t in raw_tags]
            else:
                tag_names = [str(t) for t in raw_tags]

            # Source
            source = problem.get('provider', {}).get('name', '') if isinstance(problem.get('provider'), dict) else None

            # Content fields: new API nests them in problem['content'] dict
            # with renamed keys (inputFormat→formatI, outputFormat→formatO).
            # Fall back to old top-level fields for backward compat.
            content_dict = problem.get('content', {})
            if isinstance(content_dict, dict) and content_dict.get('description'):
                background = content_dict.get('background', '') or ''
                desc_text = content_dict.get('description', '') or ''
                input_desc = content_dict.get('formatI', None)
                output_desc = content_dict.get('formatO', None)
                hint = content_dict.get('hint', None)
            else:
                background = problem.get('background', '') or ''
                desc_text = problem.get('description', '') or ''
                input_desc = problem.get('inputFormat', None)
                output_desc = problem.get('outputFormat', None)
                hint = problem.get('hint', None)

            description = background
            if desc_text:
                if description:
                    description += '\n\n'
                description += desc_text

            # Examples
            samples = problem.get('samples', [])
            examples_parts = []
            for i, sample in enumerate(samples):
                if isinstance(sample, (list, tuple)) and len(sample) >= 2:
                    examples_parts.append(f"输入样例 {i + 1}:\n{sample[0]}\n输出样例 {i + 1}:\n{sample[1]}")
            examples = '\n\n'.join(examples_parts) if examples_parts else None

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
            data = self._parse_response(resp)
            self._check_auth_response(data)

            current_data = self._extract_data(data)
            record = current_data.get('record', {})
            source_code = record.get('sourceCode', None)

            return source_code

        except LuoguSessionExpired:
            raise
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
        return (
            "洛谷使用 Cookie 认证，请按以下步骤获取：\n"
            "1. 在浏览器打开 www.luogu.com.cn 并登录\n"
            "2. 按 F12 打开开发者工具\n"
            "3. 切换到 Application（应用）标签 → Cookies → "
            "www.luogu.com.cn\n"
            "4. 找到 __client_id 和 _uid，分别复制其 Value 值\n"
            "5. 在下方 Cookie 栏粘贴，格式：__client_id=xxx; _uid=xxx"
        )

    # ── Password login with CAPTCHA ──────────────────────────────

    @staticmethod
    def get_login_captcha() -> dict:
        """Fetch a CAPTCHA image from Luogu and return it with the login state.

        Returns:
            {
                'captcha_image_b64': str,  # base64-encoded JPEG
                'login_state': {
                    'csrf_token': str,
                    'cookies': dict,       # serialized cookie jar
                }
            }
        """
        import base64
        from bs4 import BeautifulSoup

        sess = requests.Session()
        sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
        })

        # Step 1: GET login page → CSRF token + C3VK cookie
        # Luogu's CDN sets C3VK via redirect; requests follows automatically.
        resp = sess.get('https://www.luogu.com.cn/auth/login', timeout=15)
        resp.raise_for_status()

        # Extract CSRF token from <meta> or embedded JSON
        csrf_token = None
        soup = BeautifulSoup(resp.text, 'html.parser')
        meta = soup.find('meta', attrs={'name': 'csrf-token'})
        if meta and meta.get('content'):
            csrf_token = meta['content']

        if not csrf_token:
            # Try embedded JSON (Luogu sometimes puts it in decodeURIComponent)
            m = re.search(r'decodeURIComponent\("([^"]+)"\)', resp.text)
            if m:
                from urllib.parse import unquote as url_unquote
                data = json.loads(url_unquote(m.group(1)))
                csrf_token = data.get('csrfToken') or data.get('csrf_token')

        if not csrf_token:
            raise RuntimeError('无法从洛谷登录页提取 CSRF token')

        # Step 2: GET CAPTCHA image
        captcha_url = f'https://www.luogu.com.cn/lg4/captcha?_t={int(time.time() * 1000)}'
        captcha_resp = sess.get(captcha_url, timeout=15)
        captcha_resp.raise_for_status()

        captcha_b64 = base64.b64encode(captcha_resp.content).decode('ascii')

        # Serialize cookies
        cookies_dict = {c.name: c.value for c in sess.cookies}

        return {
            'captcha_image_b64': captcha_b64,
            'login_state': {
                'csrf_token': csrf_token,
                'cookies': cookies_dict,
            },
        }

    @staticmethod
    def do_password_login(username: str, password: str, captcha_text: str,
                          login_state: dict) -> dict:
        """Perform Luogu password login using previously obtained CAPTCHA state.

        Returns:
            On success: {'success': True, 'cookie': '__client_id=xxx; _uid=yyy', 'uid': 'yyy'}
            On failure: {'success': False, 'message': '...'}
        """
        sess = requests.Session()
        sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://www.luogu.com.cn/auth/login',
            'x-csrf-token': login_state['csrf_token'],
            'Content-Type': 'application/json',
        })

        # Restore cookies from login_state
        for name, value in login_state['cookies'].items():
            sess.cookies.set(name, value, domain='.luogu.com.cn')

        try:
            resp = sess.post(
                'https://www.luogu.com.cn/do-auth/password',
                json={'username': username, 'password': password, 'captcha': captcha_text},
                timeout=15,
                allow_redirects=False,
            )
        except requests.RequestException as e:
            return {'success': False, 'message': f'网络错误: {e}'}

        # Parse response
        try:
            data = resp.json() if resp.headers.get('Content-Type', '').startswith('application/json') else {}
        except (ValueError, TypeError):
            data = {}

        if resp.status_code == 200:
            # Success — extract cookies
            client_id = sess.cookies.get('__client_id', domain='.luogu.com.cn')
            uid = sess.cookies.get('_uid', domain='.luogu.com.cn')

            if not client_id or not uid:
                # Try without domain filter
                client_id = client_id or sess.cookies.get('__client_id')
                uid = uid or sess.cookies.get('_uid')

            if client_id and uid:
                cookie_str = f'__client_id={client_id}; _uid={uid}'
                return {'success': True, 'cookie': cookie_str, 'uid': uid}
            else:
                return {'success': False, 'message': '登录似乎成功但未获取到有效 Cookie，请重试'}

        # Error responses
        error_msg = data.get('errorMessage') or data.get('message') or data.get('error') or ''
        if resp.status_code == 403:
            return {'success': False, 'message': error_msg or 'CSRF 验证失败，请重新加载验证码'}
        if '验证码' in error_msg:
            return {'success': False, 'message': error_msg}
        if error_msg:
            return {'success': False, 'message': error_msg}
        return {'success': False, 'message': f'登录失败 (HTTP {resp.status_code})'}
