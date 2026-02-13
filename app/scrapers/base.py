from __future__ import annotations

import requests
import logging
import time
from abc import ABC, abstractmethod
from typing import Generator
from datetime import datetime
from .common import ScrapedSubmission, ScrapedProblem
from .rate_limiter import RateLimiter


class BaseScraper(ABC):
    PLATFORM_NAME: str = ""
    PLATFORM_DISPLAY: str = ""
    BASE_URL: str = ""
    SUPPORT_CODE_FETCH: bool = False

    def __init__(self, auth_cookie: str = None, auth_password: str = None, rate_limit: float = 2.0):
        self.auth_cookie = auth_cookie
        self.auth_password = auth_password
        self.rate_limiter = RateLimiter(rate_limit)
        self.logger = logging.getLogger(f'scraper.{self.PLATFORM_NAME}')
        self.session = self._create_session()

    @abstractmethod
    def validate_account(self, platform_uid: str) -> bool:
        ...

    @abstractmethod
    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        ...

    @abstractmethod
    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        ...

    @abstractmethod
    def map_status(self, raw_status) -> str:
        ...

    @abstractmethod
    def map_difficulty(self, raw_difficulty) -> int:
        ...

    def fetch_submission_code(self, record_id: str) -> str | None:
        return None

    def get_problem_url(self, problem_id: str) -> str:
        return f"{self.BASE_URL}/problem/{problem_id}"

    def get_auth_instructions(self) -> str:
        return "请在浏览器登录后，F12获取Cookie"

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        if self.auth_cookie:
            session.headers['Cookie'] = self.auth_cookie
        return session

    def _request_with_retry(self, url, method='GET', max_retries=3, **kwargs):
        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait()
                resp = self.session.request(method, url, timeout=30, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                self.logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def _rate_limited_get(self, url, **kwargs):
        return self._request_with_retry(url, method='GET', **kwargs)
