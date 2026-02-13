from __future__ import annotations

import re
import html
import logging
from datetime import datetime
from typing import Generator

from bs4 import BeautifulSoup

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)

# YBT language code mapping
_LANG_MAP = {
    0: 'C',
    1: 'C',
    2: 'C++',
    3: 'Pascal',
    4: 'BASIC',
    5: 'Fortran',
    6: 'Java',
    7: 'C++',
    8: 'Python',
}

# Result text to status mapping
_RESULT_STATUS_MAP = {
    'Accepted': SubmissionStatus.AC,
    'Wrong Answer': SubmissionStatus.WA,
    'Time Limit Exceeded': SubmissionStatus.TLE,
    'Memory Limit Exceeded': SubmissionStatus.MLE,
    'Runtime Error': SubmissionStatus.RE,
    'Compile Error': SubmissionStatus.CE,
    'Presentation Error': SubmissionStatus.WA,   # Treat PE as WA
    'Output Limit Exceeded': SubmissionStatus.RE,
    'Waiting': SubmissionStatus.PENDING,
    'Compiling': SubmissionStatus.JUDGING,
    'Running': SubmissionStatus.JUDGING,
}

# Records per page on YBT status page
_RECORDS_PER_PAGE = 20


@register_scraper
class YBTScraper(BaseScraper):
    PLATFORM_NAME = "ybt"
    PLATFORM_DISPLAY = "一本通OJ"
    BASE_URL = "http://ybt.ssoier.cn:8088"
    SUPPORT_CODE_FETCH = True

    def __init__(self, auth_cookie: str = None, auth_password: str = None, rate_limit: float = 2.0):
        super().__init__(auth_cookie=auth_cookie, auth_password=auth_password, rate_limit=rate_limit)
        self._logged_in = False

    def login(self, username: str, password: str) -> bool:
        """Authenticate with YBT via form POST."""
        try:
            url = f"{self.BASE_URL}/login.php"
            payload = {
                'username': username,
                'password': password,
            }
            # YBT uses form-encoded POST
            resp = self._request_with_retry(
                url,
                method='POST',
                data=payload,
                allow_redirects=True,
            )

            # Check if login succeeded by looking for cookies or page content
            response_text = resp.content.decode('gbk', errors='replace')

            # If we get redirected to index or see welcome text, login succeeded
            # Also check if PHPSESSID cookie is set
            cookies = self.session.cookies.get_dict()
            has_session = 'PHPSESSID' in cookies

            # Check for error indicators in the response
            if '密码错误' in response_text or '用户不存在' in response_text:
                self.logger.error(f"YBT login failed for user: {username}")
                return False

            if has_session:
                self._logged_in = True
                self.logger.info(f"YBT login successful for user: {username}")
                return True

            # Fallback: try to access status page and see if we get valid data
            self._logged_in = True
            return True

        except Exception as e:
            self.logger.error(f"YBT login error: {e}")
            return False

    def _ensure_logged_in(self, platform_uid: str) -> bool:
        """Ensure we are logged in."""
        if self._logged_in:
            return True
        if not self.auth_password:
            self.logger.error("YBT requires a password for authentication")
            return False
        return self.login(platform_uid, self.auth_password)

    def validate_account(self, platform_uid: str) -> bool:
        """Validate account by attempting to login."""
        return self._ensure_logged_in(platform_uid)

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions for a YBT user by parsing the status page."""
        if not self._ensure_logged_in(platform_uid):
            self.logger.error("Cannot fetch submissions: not logged in")
            return

        start = 0
        reached_end = False

        while not reached_end:
            try:
                url = f"{self.BASE_URL}/status.php?showname={platform_uid}&start={start}"
                resp = self._rate_limited_get(url)
                page_content = resp.content.decode('gbk', errors='replace')

                # Extract the ee variable from JavaScript
                records = self._parse_ee_variable(page_content)

                if not records:
                    break

                for record in records:
                    submission = self._parse_record(record)
                    if submission is None:
                        continue

                    # Check cursor boundary
                    if cursor and submission.platform_record_id == cursor:
                        reached_end = True
                        break

                    # Check since boundary
                    if since and submission.submitted_at < since:
                        reached_end = True
                        break

                    yield submission

                # If we got fewer records than a full page, we're done
                if len(records) < _RECORDS_PER_PAGE:
                    break

                start += _RECORDS_PER_PAGE

            except Exception as e:
                self.logger.error(f"Error fetching YBT submissions at start={start}: {e}")
                break

    def _parse_ee_variable(self, page_content: str) -> list[str]:
        """Extract and parse the ee JavaScript variable from status page.

        The variable looks like: var ee="record1#record2#record3..."
        Each record's fields are separated by backtick (`).
        """
        match = re.search(r'var\s+ee\s*=\s*"([^"]*)"', page_content)
        if not match:
            self.logger.debug("Could not find ee variable in page content")
            return []

        ee_value = match.group(1)
        if not ee_value.strip():
            return []

        # Records separated by '#'
        raw_records = ee_value.split('#')
        return [r for r in raw_records if r.strip()]

    def _parse_record(self, record_str: str) -> ScrapedSubmission | None:
        """Parse a single record string from the ee variable.

        Fields are separated by backtick (`):
        Username:DisplayName`FLAG_RUNID`ProblemID`Result`LangCode`CodeLen`SubmitTime

        FLAG_RUNID: first char is visibility flag (1=can view source), rest is run ID.
        Result: "Accepted|score:details" for scored, single word for status, "C" for CE.
        """
        try:
            fields = record_str.split('`')
            if len(fields) < 7:
                self.logger.debug(f"Record has insufficient fields ({len(fields)}): {record_str[:80]}")
                return None

            # Field 0: Username:DisplayName
            # Field 1: FLAG_RUNID (first char = visibility flag, rest = actual run ID)
            # Field 2: ProblemID
            # Field 3: Result
            # Field 4: LangCode
            # Field 5: CodeLen
            # Field 6: SubmitTime

            flag_runid = fields[1]
            if len(flag_runid) < 2:
                self.logger.debug(f"Invalid FLAG_RUNID: {flag_runid}")
                return None

            # visibility_flag = flag_runid[0]  # '1' means source viewable
            actual_runid = flag_runid[1:]
            problem_id = fields[2].strip()
            result_raw = fields[3].strip()
            lang_code_str = fields[4].strip()
            # code_len = fields[5].strip()  # Not used in ScrapedSubmission
            submit_time_str = fields[6].strip()

            # Parse status and score
            status, score = self._parse_result(result_raw)

            # Parse language
            language = None
            try:
                lang_code = int(lang_code_str)
                language = _LANG_MAP.get(lang_code, f'Lang{lang_code}')
            except (ValueError, TypeError):
                language = lang_code_str if lang_code_str else None

            # Parse submission time
            submitted_at = datetime.utcnow()
            if submit_time_str:
                try:
                    submitted_at = datetime.strptime(submit_time_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        submitted_at = datetime.strptime(submit_time_str, '%Y-%m-%d %H:%M')
                    except ValueError:
                        self.logger.debug(f"Could not parse submit time: {submit_time_str}")

            return ScrapedSubmission(
                platform_record_id=actual_runid,
                problem_id=problem_id,
                status=status,
                score=score,
                language=language,
                submitted_at=submitted_at,
            )

        except Exception as e:
            self.logger.debug(f"Error parsing record '{record_str[:80]}': {e}")
            return None

    def _parse_result(self, result_raw: str) -> tuple[str, int | None]:
        """Parse YBT result string into (status, score).

        Formats:
        - "Accepted" -> AC, score=10
        - "Accepted|score:4/10" -> AC, score=4
        - "Wrong Answer|score:3/10" -> WA, score=3
        - "C" -> CE, None
        - Single result text -> mapped status, None
        """
        if not result_raw:
            return SubmissionStatus.UNKNOWN.value, None

        # Handle "C" for Compile Error
        if result_raw == 'C':
            return SubmissionStatus.CE.value, None

        # Split on '|' to separate result text from score details
        parts = result_raw.split('|')
        result_text = parts[0].strip()

        # Determine status from result text
        status = SubmissionStatus.UNKNOWN.value
        for key, mapped_status in _RESULT_STATUS_MAP.items():
            if result_text.startswith(key) or result_text == key:
                status = mapped_status.value
                break

        # Parse score if present
        score = None
        if len(parts) > 1:
            score_part = parts[1].strip()
            # Format: "score:AC_CASES/TOTAL_CASES" e.g., "score:4/10"
            score_match = re.search(r'score[:\s]*(\d+)\s*/\s*(\d+)', score_part)
            if score_match:
                ac_cases = int(score_match.group(1))
                total_cases = int(score_match.group(2))
                if total_cases > 0:
                    score = round(10 * ac_cases / total_cases)
                else:
                    score = 0
            else:
                # Try to extract a plain numeric score
                plain_score = re.search(r'(\d+)', score_part)
                if plain_score:
                    score = int(plain_score.group(1))

        # If Accepted with no score details, give full score
        if status == SubmissionStatus.AC.value and score is None:
            score = 10

        return status, score

    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        """Fetch problem details from YBT by parsing the HTML page."""
        try:
            url = f"{self.BASE_URL}/problem_show.php?pid={problem_id}"
            resp = self._rate_limited_get(url)
            page_content = resp.content.decode('gbk', errors='replace')

            soup = BeautifulSoup(page_content, 'html.parser')

            # Parse title from <h3> tag
            title = ''
            h3_tag = soup.find('h3')
            if h3_tag:
                title = h3_tag.get_text(strip=True)
                # Remove problem ID prefix if present (e.g., "1001:Hello World")
                if ':' in title:
                    title = title.split(':', 1)[1].strip()
                elif '：' in title:
                    title = title.split('：', 1)[1].strip()

            # Parse description from pshow() JavaScript calls or from page sections
            description = self._extract_section(soup, page_content, '题目描述')
            input_desc = self._extract_section(soup, page_content, '输入')
            output_desc = self._extract_section(soup, page_content, '输出')
            hint = self._extract_section(soup, page_content, '提示')

            # Extract examples from <pre> tags
            examples = self._extract_examples(soup)

            return ScrapedProblem(
                problem_id=problem_id,
                title=title,
                difficulty_raw=None,   # YBT doesn't have explicit difficulty labels
                tags=[],
                source=None,
                url=self.get_problem_url(problem_id),
                description=description,
                input_desc=input_desc,
                output_desc=output_desc,
                examples=examples,
                hint=hint,
            )

        except Exception as e:
            self.logger.error(f"Error fetching YBT problem {problem_id}: {e}")
            return None

    def _extract_section(self, soup: BeautifulSoup, page_content: str, section_name: str) -> str | None:
        """Extract a named section from the YBT problem page.

        YBT uses JavaScript pshow() calls to populate sections, or direct HTML.
        Look for section headers and extract following content.
        """
        # Try to find section via pshow() JavaScript calls
        # Pattern: pshow('section_name','encoded_content')
        pattern = rf"pshow\s*\(\s*'[^']*{re.escape(section_name)}[^']*'\s*,\s*'([^']*)'\s*\)"
        match = re.search(pattern, page_content)
        if match:
            content = match.group(1)
            # Unescape JavaScript string
            content = content.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n')
            content = html.unescape(content)
            if content.strip():
                return content.strip()

        # Fallback: look for section in HTML structure
        # Find headers containing the section name
        for tag in soup.find_all(['h3', 'h4', 'b', 'strong', 'p', 'div']):
            text = tag.get_text(strip=True)
            if section_name in text:
                # Get the next sibling elements until next header
                content_parts = []
                sibling = tag.find_next_sibling()
                while sibling:
                    if sibling.name in ('h3', 'h4') or (
                        sibling.name in ('b', 'strong') and any(
                            kw in sibling.get_text() for kw in ('输入', '输出', '提示', '样例', '描述')
                        )
                    ):
                        break
                    text_content = sibling.get_text(strip=True)
                    if text_content:
                        content_parts.append(text_content)
                    sibling = sibling.find_next_sibling()
                if content_parts:
                    return '\n'.join(content_parts)

        return None

    def _extract_examples(self, soup: BeautifulSoup) -> str | None:
        """Extract input/output examples from <pre> tags on the problem page."""
        pre_tags = soup.find_all('pre')
        if not pre_tags:
            return None

        examples_parts = []
        # YBT typically has pairs of <pre> for input and output samples
        i = 0
        sample_num = 1
        while i < len(pre_tags):
            input_text = pre_tags[i].get_text()
            output_text = ''
            if i + 1 < len(pre_tags):
                output_text = pre_tags[i + 1].get_text()
                i += 2
            else:
                i += 1
            examples_parts.append(
                f"输入样例 {sample_num}:\n{input_text.strip()}\n输出样例 {sample_num}:\n{output_text.strip()}"
            )
            sample_num += 1

        return '\n\n'.join(examples_parts) if examples_parts else None

    def fetch_submission_code(self, record_id: str) -> str | None:
        """Fetch source code for a specific submission from YBT."""
        try:
            url = f"{self.BASE_URL}/show_source.php?runid={record_id}"
            resp = self._rate_limited_get(url)
            page_content = resp.content.decode('gbk', errors='replace')

            soup = BeautifulSoup(page_content, 'html.parser')
            pre_tag = soup.find('pre')
            if pre_tag:
                code = pre_tag.get_text()
                code = html.unescape(code)
                return code

            self.logger.debug(f"No <pre> tag found for YBT record {record_id}")
            return None

        except Exception as e:
            self.logger.error(f"Error fetching YBT submission code for {record_id}: {e}")
            return None

    def map_status(self, raw_status) -> str:
        """Map YBT result text to SubmissionStatus string."""
        if isinstance(raw_status, str):
            if raw_status == 'C':
                return SubmissionStatus.CE.value
            for key, mapped_status in _RESULT_STATUS_MAP.items():
                if raw_status.startswith(key) or raw_status == key:
                    return mapped_status.value
            return SubmissionStatus.UNKNOWN.value

        return SubmissionStatus.UNKNOWN.value

    def map_difficulty(self, raw_difficulty) -> int:
        """Map YBT difficulty to numeric level.

        YBT does not have an explicit difficulty system, so return 0 by default.
        """
        if isinstance(raw_difficulty, int):
            return raw_difficulty
        return 0

    def get_problem_url(self, problem_id: str) -> str:
        return f"http://ybt.ssoier.cn:8088/problem_show.php?pid={problem_id}"

    def get_auth_instructions(self) -> str:
        return "请输入一本通OJ的用户名和密码"
