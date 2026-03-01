from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Generator

from .base import BaseScraper
from .common import ScrapedSubmission, ScrapedProblem, SubmissionStatus
from . import register_scraper

logger = logging.getLogger(__name__)

# Coderlands judgeResultSlug → SubmissionStatus
_STATUS_MAP: dict[str, SubmissionStatus] = {
    'AC': SubmissionStatus.AC,
    'WA': SubmissionStatus.WA,
    'TLE': SubmissionStatus.TLE,
    'MLE': SubmissionStatus.MLE,
    'RE': SubmissionStatus.RE,
    'CE': SubmissionStatus.CE,
    'PE': SubmissionStatus.WA,       # Presentation Error → WA
    'OLE': SubmissionStatus.RE,      # Output Limit Exceeded → RE
    'SE': SubmissionStatus.UNKNOWN,  # System Error
}

# Coderlands difficultLevel → project difficulty (1-8)
_DIFFICULTY_MAP: dict[str, int] = {
    '可视化': 1,
    '入门': 2,
    '普及-': 3,
    '普及/提高-': 4,
    '普及+/提高': 5,
    '提高+/省选-': 6,
    '省选/NOI-': 7,
    'NOI/NOI+/CTSC': 8,
}

# Coderlands languageId → language display name (best guess)
_LANG_MAP: dict[str, str] = {
    '0': 'C',
    '1': 'C++',
    '2': 'C++11',
    '3': 'C++14',
    '4': 'C++17',
    '5': 'Java',
    '6': 'Python 2',
    '7': 'Python 3',
}

# 32-hex-char UUID pattern
_UUID_RE = re.compile(r'^[0-9a-fA-F]{32}$')
# P{number} problem ID pattern
_PNO_RE = re.compile(r'^P(\d+)$', re.IGNORECASE)


class CoderlandsSessionExpired(Exception):
    """Raised when the JSESSIONID session has expired."""
    pass


@register_scraper
class CoderlandsScraper(BaseScraper):
    PLATFORM_NAME = "coderlands"
    PLATFORM_DISPLAY = "代码部落"
    BASE_URL = "https://course.coderlands.com"
    REQUIRES_LOGIN = True
    SUPPORT_CODE_FETCH = True
    AUTH_METHOD = 'cookie'

    def __init__(self, auth_cookie: str = None, auth_password: str = None,
                 rate_limit: float = 2.0, platform_uid: str = None):
        if auth_cookie:
            auth_cookie = auth_cookie.strip()
            # Strip "Cookie:" prefix if user copied from DevTools request headers
            if auth_cookie.lower().startswith('cookie:'):
                auth_cookie = auth_cookie[len('cookie:'):].strip()
            # Auto-prepend JSESSIONID= if user only pasted the value
            if '=' not in auth_cookie:
                auth_cookie = f'JSESSIONID={auth_cookie}'
        super().__init__(auth_cookie=auth_cookie, auth_password=auth_password,
                         rate_limit=rate_limit, platform_uid=platform_uid)
        self._uuid_cache: dict[str, str] = {}  # problemNo → UUID
        self._lesson_cache: list[dict] | None = None

    # ── Session management ──

    def _api_get(self, path: str, **kwargs) -> dict:
        """GET a Coderlands API endpoint, return parsed JSON result."""
        url = f"{self.BASE_URL}{path}"
        resp = self._rate_limited_get(url, **kwargs)
        resp.encoding = 'utf-8'
        data = resp.json()
        if not isinstance(data, dict) or data.get('code') != 1:
            msg = data.get('msg', '') if isinstance(data, dict) else str(data)
            if '登录' in msg or '未登录' in msg or data.get('code') == -1:
                raise CoderlandsSessionExpired(
                    "Session 已过期，请重新复制 JSESSIONID Cookie"
                )
            raise ValueError(f"API error ({path}): code={data.get('code')}, msg={msg}")
        return data.get('result', data)

    def _api_post(self, path: str, **kwargs) -> dict:
        """POST a Coderlands API endpoint, return parsed JSON result."""
        url = f"{self.BASE_URL}{path}"
        resp = self._request_with_retry(url, method='POST', **kwargs)
        resp.encoding = 'utf-8'
        data = resp.json()
        if not isinstance(data, dict) or data.get('code') != 1:
            msg = data.get('msg', '') if isinstance(data, dict) else str(data)
            if '登录' in msg or '未登录' in msg or data.get('code') == -1:
                raise CoderlandsSessionExpired(
                    "Session 已过期，请重新复制 JSESSIONID Cookie"
                )
            raise ValueError(f"API error ({path}): code={data.get('code')}, msg={msg}")
        return data.get('result', data)

    # ── BaseScraper contract ──

    def validate_account(self, platform_uid: str) -> bool:
        """Validate session by calling baseInfo."""
        try:
            result = self._api_get('/server/student/person/center/baseInfo')
            login_name = result.get('loginName', '')
            if login_name:
                self.logger.info(f"Coderlands session valid for user: {login_name}")
                return True
            self.logger.warning("Coderlands baseInfo returned no loginName")
            return False
        except CoderlandsSessionExpired:
            self.logger.warning("Coderlands session expired")
            return False
        except Exception as e:
            self.logger.error(f"Coderlands validate_account error: {e}")
            return False

    def fetch_submissions(
        self, platform_uid: str, since: datetime = None, cursor: str = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch submissions with incremental sync optimisation.

        Strategy:
        1. Get all problem IDs via exercise API (acStr + unAcStr)
        2. Filter out problems that already have AC in DB (skip entirely)
        3. Hash-based change detection via cursor to minimise API calls
        4. Map problem IDs → UUIDs → fetch submissions per problem
        """
        try:
            # Step 1: Get exercise data
            exercise_data = self._fetch_exercise_data()
            if exercise_data is None:
                return

            all_ac_ids, all_unac_ids = exercise_data
            all_problem_ids = all_ac_ids | all_unac_ids

            if not all_problem_ids:
                self.logger.info("Coderlands: no problems found in exercise")
                return

            # Step 2: Filter out locally-AC'd problems
            from app.models import Submission, PlatformAccount, Problem
            locally_ac_ids = self._get_locally_ac_problem_ids(platform_uid)

            # Step 3: Hash-based change detection
            exercise_hash = self._compute_exercise_hash(all_ac_ids, all_unac_ids)
            hash_changed = (cursor != exercise_hash) if cursor else True

            # Determine which problems to sync
            problems_to_sync: set[str] = set()

            # Always sync problems never seen in DB
            db_known_ids = self._get_db_known_problem_ids(platform_uid)
            new_problems = all_problem_ids - db_known_ids
            problems_to_sync |= new_problems

            if hash_changed:
                # Hash changed: also sync all un-AC'd problems (not locally AC'd)
                problems_to_sync |= (all_unac_ids - locally_ac_ids)
                # Also sync problems that became AC remotely but aren't locally AC'd
                problems_to_sync |= (all_ac_ids - locally_ac_ids)

            # Remove locally AC'd from sync set
            problems_to_sync -= locally_ac_ids

            self.logger.info(
                f"Coderlands sync: {len(all_problem_ids)} total, "
                f"{len(locally_ac_ids)} locally AC (skip), "
                f"{len(new_problems)} new, "
                f"hash_changed={hash_changed}, "
                f"{len(problems_to_sync)} to sync"
            )

            if not problems_to_sync:
                # Still need to update cursor to current hash
                # Yield a sentinel-less return; SyncService will keep old cursor
                # We store the hash as new_cursor via a special attribute
                self._new_cursor = exercise_hash
                return

            # Step 4: Map problem numbers to UUIDs
            uuid_map = self._resolve_uuids(problems_to_sync)

            # Step 5: Fetch submissions per problem
            # For new-to-DB problems, ignore `since` — we need their full history
            for problem_no, uuid in uuid_map.items():
                problem_id = f"P{problem_no}"
                effective_since = None if problem_no in new_problems else since
                try:
                    yield from self._fetch_problem_submissions(
                        problem_id, uuid, effective_since
                    )
                except CoderlandsSessionExpired:
                    raise
                except Exception as e:
                    self.logger.error(
                        f"Error fetching submissions for {problem_id}: {e}"
                    )

            # Store the new cursor hash
            self._new_cursor = exercise_hash

        except CoderlandsSessionExpired:
            raise Exception("Session 已过期，请重新复制 JSESSIONID Cookie")

    def fetch_problem(self, problem_id: str) -> ScrapedProblem | None:
        """Fetch problem details via getClassWorkOne.

        problem_id can be:
        - UUID (32 hex chars): used directly
        - P{number}: resolved to UUID via cache/lesson traversal
        """
        try:
            uuid_param = self._problem_id_to_uuid_param(problem_id)
            result = self._api_get(
                f'/server/student/stady/getClassWorkOne'
                f'?uuid={uuid_param}&lessonUuid=personalCenter'
            )
            data = result.get('data', result) if isinstance(result, dict) else result

            if not data or not isinstance(data, dict):
                self.logger.warning(f"Coderlands: empty data for problem {problem_id}")
                return None

            problem_no = str(data.get('problemNo', ''))
            canonical_id = f"P{problem_no}" if problem_no else problem_id

            # Cache UUID mapping if available and persist to DB
            if problem_no and data.get('uuid'):
                self._uuid_cache[problem_no] = data['uuid']
                self._persist_single_uuid(problem_no, data['uuid'])

            title = data.get('problemName', '')
            difficulty_raw = data.get('difficultLevel', '')
            tag_str = data.get('tagNameString', '')
            tags = [t.strip() for t in tag_str.split(',') if t.strip()] if tag_str else []

            # Parse description (HTML content)
            description = data.get('description', '')
            input_format = data.get('inputFormat', '')
            output_format = data.get('outputFormat', '')
            sample_input = data.get('sampleInput', '')
            sample_output = data.get('sampleOutput', '')

            # Build examples string
            examples = None
            if sample_input or sample_output:
                parts = []
                if sample_input:
                    parts.append(f"**输入样例**\n```\n{sample_input}\n```")
                if sample_output:
                    parts.append(f"**输出样例**\n```\n{sample_output}\n```")
                examples = '\n\n'.join(parts)

            return ScrapedProblem(
                problem_id=canonical_id,
                title=title,
                difficulty_raw=difficulty_raw,
                tags=tags,
                url=self.get_problem_url(canonical_id),
                description=description,
                input_desc=input_format,
                output_desc=output_format,
                examples=examples,
            )

        except Exception as e:
            self.logger.error(f"Error fetching Coderlands problem {problem_id}: {e}")
            return None

    def map_status(self, raw_status) -> str:
        """Map judgeResultSlug to SubmissionStatus."""
        if isinstance(raw_status, str):
            status = _STATUS_MAP.get(raw_status.upper(), SubmissionStatus.UNKNOWN)
            return status.value
        return SubmissionStatus.UNKNOWN.value

    def map_difficulty(self, raw_difficulty) -> int:
        """Map Coderlands difficulty label to project scale."""
        if isinstance(raw_difficulty, str):
            return _DIFFICULTY_MAP.get(raw_difficulty.strip(), 0)
        return 0

    def fetch_submission_code(self, record_id: str) -> str | None:
        """Fetch source code for a submission via mDetail.

        record_id format: P{no}/{submission_uuid}
        """
        try:
            parts = record_id.split('/', 1)
            if len(parts) != 2:
                return None
            submission_uuid = parts[1]

            result = self._api_get(
                f'/server/student/stady/mDetail?uuid={submission_uuid}'
            )
            data = result.get('data', result) if isinstance(result, dict) else result
            if not data or not isinstance(data, dict):
                return None

            return data.get('code')

        except Exception as e:
            self.logger.error(f"Error fetching code for {record_id}: {e}")
            return None

    def get_problem_url(self, problem_id: str) -> str:
        """Generate a URL for the problem.

        Since Coderlands uses hash-based routing with UUIDs,
        we return the personal center URL as a reasonable default.
        """
        return f"{self.BASE_URL}/web/#/person/center/exercise"

    def get_auth_instructions(self) -> str:
        return (
            "代码部落使用 Cookie 认证，请按以下步骤获取：\n"
            "1. 在浏览器打开 course.coderlands.com 并登录\n"
            "2. 按 F12 打开开发者工具\n"
            "3. 切换到 Application（应用）标签 → Cookies → "
            "course.coderlands.com\n"
            "4. 找到 JSESSIONID，复制其 Value 值\n"
            "5. 在下方 Cookie 栏粘贴（直接粘贴值即可，系统会自动补全格式）"
        )

    # ── Exercise data ──

    def _fetch_exercise_data(self) -> tuple[set[str], set[str]] | None:
        """Fetch exercise API and return (ac_ids, unac_ids) as sets of problem number strings."""
        try:
            result = self._api_post(
                '/server/student/person/center/exercise',
                json={},
            )

            data_list = result.get('dataList', []) if isinstance(result, dict) else []
            ac_ids: set[str] = set()
            unac_ids: set[str] = set()

            for item in data_list:
                ac_str = item.get('acStr', '')
                unac_str = item.get('unAcStr', '')
                if ac_str:
                    for pid in re.split(r'[,\s]+', ac_str):
                        pid = pid.strip()
                        if pid:
                            # Strip P/p prefix if present
                            m = _PNO_RE.match(pid)
                            ac_ids.add(m.group(1) if m else pid)
                if unac_str:
                    for pid in re.split(r'[,\s]+', unac_str):
                        pid = pid.strip()
                        if pid:
                            m = _PNO_RE.match(pid)
                            unac_ids.add(m.group(1) if m else pid)

            return ac_ids, unac_ids

        except CoderlandsSessionExpired:
            raise
        except Exception as e:
            self.logger.error(f"Error fetching exercise data: {e}")
            return None

    def _compute_exercise_hash(self, ac_ids: set[str], unac_ids: set[str]) -> str:
        """Compute a stable hash of the exercise data for change detection."""
        content = (
            ','.join(sorted(ac_ids)) + '|' + ','.join(sorted(unac_ids))
        )
        return hashlib.md5(content.encode()).hexdigest()[:16]

    # ── DB queries for incremental sync ──

    def _get_locally_ac_problem_ids(self, platform_uid: str) -> set[str]:
        """Return set of problem numbers (without P prefix) that have AC submissions locally."""
        from app.models import Submission, PlatformAccount, Problem

        account = PlatformAccount.query.filter_by(
            platform=self.PLATFORM_NAME, platform_uid=platform_uid
        ).first()
        if not account:
            return set()

        # Find problems with AC submissions for this account
        ac_problems = (
            Problem.query
            .join(Submission, Submission.problem_id_ref == Problem.id)
            .filter(
                Submission.platform_account_id == account.id,
                Submission.status == SubmissionStatus.AC.value,
                Problem.platform == self.PLATFORM_NAME,
            )
            .with_entities(Problem.problem_id)
            .distinct()
            .all()
        )

        # Extract number from P{number}
        result = set()
        for (pid,) in ac_problems:
            m = _PNO_RE.match(pid)
            if m:
                result.add(m.group(1))
        return result

    def _get_db_known_problem_ids(self, platform_uid: str) -> set[str]:
        """Return set of problem numbers that exist in DB for this platform."""
        from app.models import Problem

        problems = (
            Problem.query
            .filter_by(platform=self.PLATFORM_NAME)
            .with_entities(Problem.problem_id)
            .all()
        )

        result = set()
        for (pid,) in problems:
            m = _PNO_RE.match(pid)
            if m:
                result.add(m.group(1))
        return result

    # ── UUID resolution ──

    def _problem_id_to_uuid_param(self, problem_id: str) -> str:
        """Convert a problem_id to the UUID needed by getClassWorkOne.

        - 32 hex UUID → use directly
        - P{no} → check UUID cache → getProbelmUuid API → lesson traversal
        - bare number → same resolution chain

        NOTE: getClassWorkOne ONLY accepts 32-hex UUIDs.  Passing a bare
        number returns HTTP 500.
        """
        if _UUID_RE.match(problem_id):
            return problem_id
        m = _PNO_RE.match(problem_id)
        no = m.group(1) if m else problem_id
        # Try cache
        if no in self._uuid_cache:
            return self._uuid_cache[no]
        # Try getProbelmUuid API (fast, 100% hit rate)
        uuid = self._fetch_problem_uuid(no)
        if uuid:
            self._uuid_cache[no] = uuid
            return uuid
        # Fall back to lesson traversal (for edge cases)
        self._build_uuid_map_from_lessons()
        if no in self._uuid_cache:
            return self._uuid_cache[no]
        self.logger.warning(
            f"Coderlands: could not resolve UUID for problem {problem_id}, "
            f"getClassWorkOne will likely fail"
        )
        return problem_id

    def _resolve_uuids(self, problem_nos: set[str]) -> dict[str, str]:
        """Map problem numbers to UUIDs.

        Strategy:
        0. Load persisted UUIDs from DB (survives class changes)
        1. Check in-memory cache
        2. Call getProbelmUuid API for each remaining problem (100% hit rate)
        """
        result: dict[str, str] = {}
        remaining: set[str] = set()

        # Stage 0: DB lookup — load persisted UUIDs for problems we need
        self._load_uuids_from_db(problem_nos)

        # Stage 1: cache hits (now includes DB-loaded UUIDs)
        for no in problem_nos:
            if no in self._uuid_cache:
                result[no] = self._uuid_cache[no]
            else:
                remaining.add(no)

        if not remaining:
            return result

        # Stage 2: getProbelmUuid API for each remaining problem
        self.logger.info(
            f"Coderlands: {len(remaining)} problems need UUID via getProbelmUuid"
        )
        for no in sorted(remaining):
            uuid = self._fetch_problem_uuid(no)
            if uuid:
                self._uuid_cache[no] = uuid
                result[no] = uuid

        # Persist all newly discovered UUIDs to DB
        self._persist_uuids_to_db()

        unresolved = [no for no in problem_nos if no not in result]
        if unresolved:
            self.logger.warning(
                f"Coderlands: {len(unresolved)} problems unresolvable: "
                f"{', '.join(sorted(unresolved)[:10])}"
                + (f" ... and {len(unresolved) - 10} more" if len(unresolved) > 10 else "")
            )

        self.logger.info(
            f"Coderlands UUID resolution: {len(result)} resolved, "
            f"{len(unresolved)} unresolved out of {len(problem_nos)} requested"
        )

        return result

    def _load_uuids_from_db(self, problem_nos: set[str]) -> None:
        """Load persisted platform_uuid values from DB into _uuid_cache."""
        try:
            from app.models import Problem
            pid_list = [f'P{no}' for no in problem_nos if no not in self._uuid_cache]
            if not pid_list:
                return
            db_problems = Problem.query.filter(
                Problem.platform == self.PLATFORM_NAME,
                Problem.problem_id.in_(pid_list),
                Problem.platform_uuid.isnot(None),
            ).all()
            loaded = 0
            for p in db_problems:
                m = _PNO_RE.match(p.problem_id)
                if m:
                    self._uuid_cache[m.group(1)] = p.platform_uuid
                    loaded += 1
            if loaded:
                self.logger.info(f"Coderlands: loaded {loaded} UUIDs from DB")
        except Exception as e:
            self.logger.debug(f"Coderlands: DB UUID load failed (ok outside app ctx): {e}")

    def _persist_uuids_to_db(self) -> None:
        """Write newly discovered UUIDs back to Problem.platform_uuid."""
        try:
            from app.models import Problem
            from app.extensions import db
            updated = 0
            for pno, puuid in self._uuid_cache.items():
                problem = Problem.query.filter_by(
                    platform=self.PLATFORM_NAME, problem_id=f'P{pno}'
                ).first()
                if problem and not problem.platform_uuid:
                    problem.platform_uuid = puuid
                    updated += 1
            if updated:
                db.session.flush()
                self.logger.info(f"Coderlands: persisted {updated} UUIDs to DB")
        except Exception as e:
            self.logger.debug(f"Coderlands: DB UUID persist failed (ok outside app ctx): {e}")

    def _persist_single_uuid(self, problem_no: str, uuid: str) -> None:
        """Write a single UUID back to Problem.platform_uuid if not already set."""
        try:
            from app.models import Problem
            from app.extensions import db
            problem = Problem.query.filter_by(
                platform=self.PLATFORM_NAME, problem_id=f'P{problem_no}'
            ).first()
            if problem and not problem.platform_uuid:
                problem.platform_uuid = uuid
                db.session.flush()
        except Exception:
            pass  # Best-effort; bulk persist handles the rest

    def _fetch_problem_uuid(self, problem_no: str) -> str | None:
        """Resolve a single problem number to UUID via getProbelmUuid API.

        POST /server/student/person/center/getProbelmUuid
        with form-encoded body: problemNo=P{no}

        Returns the UUID string on success, None on failure.
        """
        try:
            url = f"{self.BASE_URL}/server/student/person/center/getProbelmUuid"
            resp = self._request_with_retry(
                url, method='POST',
                data=f'problemNo=P{problem_no}',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            resp.encoding = 'utf-8'
            data = resp.json()
            if isinstance(data, dict) and data.get('isSuccess') == '1':
                uuid = data.get('data', '')
                if uuid and _UUID_RE.match(uuid):
                    return uuid
            return None
        except Exception as e:
            self.logger.debug(f"getProbelmUuid failed for {problem_no}: {e}")
            return None

    def _build_uuid_map_from_lessons(self) -> None:
        """Populate _uuid_cache by traversing all lessons via getlesconNew.

        myls API returns:
            result.classInfo.uuid → classUuid
            result.lessonInfo[] → [{uuid, lessonName, ...}, ...]

        For each lesson, getlesconNew returns:
            result.dataList[] → [{uuid, name: "P{no} title", ...}, ...]

        The problem number is extracted from the name field prefix.
        """
        if self._lesson_cache is not None:
            # Already traversed in this session
            return

        self._lesson_cache = []

        try:
            myls_result = self._api_get('/server/student/stady/myls')
            if not isinstance(myls_result, dict):
                self.logger.warning("Coderlands myls: unexpected response type")
                return

            # Extract classUuid and lessonInfo
            class_info = myls_result.get('classInfo', {})
            class_uuid = class_info.get('uuid', '') if isinstance(class_info, dict) else ''
            lesson_infos = myls_result.get('lessonInfo', [])

            if not isinstance(lesson_infos, list):
                self.logger.warning(
                    f"Coderlands myls: lessonInfo is {type(lesson_infos).__name__}, "
                    f"expected list. Keys in result: {list(myls_result.keys())}"
                )
                return

            self.logger.info(
                f"Coderlands: found {len(lesson_infos)} lessons, "
                f"classUuid={class_uuid[:8]}..."
            )

            # Traverse each lesson to discover problems
            problems_found = 0
            for lesson in lesson_infos:
                if not isinstance(lesson, dict):
                    continue
                lesson_uuid = lesson.get('uuid', '')
                lesson_name = lesson.get('lessonName', '')
                if not lesson_uuid:
                    continue

                try:
                    params = f'uuid={lesson_uuid}'
                    if class_uuid:
                        params += f'&classUuid={class_uuid}'
                    lesson_result = self._api_get(
                        f'/server/student/stady/getlesconNew?{params}'
                    )
                    data_list = (
                        lesson_result.get('dataList', [])
                        if isinstance(lesson_result, dict) else []
                    )
                    for item in data_list:
                        if not isinstance(item, dict):
                            continue
                        puuid = item.get('uuid', '')
                        name = item.get('name', '')
                        if not puuid or not name:
                            continue
                        # Extract problem number from name like "P11311 digit函数"
                        m = re.match(r'^P(\d+)\s', name)
                        if m:
                            pno = m.group(1)
                            self._uuid_cache[pno] = puuid
                            problems_found += 1

                except CoderlandsSessionExpired:
                    raise
                except Exception as e:
                    self.logger.debug(
                        f"Error traversing lesson '{lesson_name}': {e}"
                    )

            self.logger.info(
                f"Coderlands: lesson traversal complete — "
                f"{problems_found} problems mapped from "
                f"{len(lesson_infos)} lessons"
            )

            # Persist newly discovered UUIDs to DB
            self._persist_uuids_to_db()

        except CoderlandsSessionExpired:
            raise
        except Exception as e:
            self.logger.error(f"Error building UUID map from lessons: {e}")

    # ── Per-problem submission fetching ──

    def _fetch_problem_submissions(
        self, problem_id: str, problem_uuid: str, since: datetime = None
    ) -> Generator[ScrapedSubmission, None, None]:
        """Fetch all submissions for a single problem via listSubNew."""
        try:
            result = self._api_get(
                f'/server/student/stady/listSubNew?problemUuid={problem_uuid}'
            )
            data_list = result.get('dataList', []) if isinstance(result, dict) else []
            if isinstance(result, list):
                data_list = result

            for item in data_list:
                if not isinstance(item, dict):
                    continue

                sub_uuid = item.get('uuid', '')
                if not sub_uuid:
                    continue

                # Parse submission time
                submit_time_str = item.get('submitTime', '')
                submitted_at = self._parse_time(submit_time_str)

                if since and submitted_at and submitted_at < since:
                    continue

                # Status
                raw_status = item.get('judgeResultSlug', '')
                status = self.map_status(raw_status)

                # Score
                score = item.get('judgeScore')
                if score is not None:
                    try:
                        score = int(score)
                    except (ValueError, TypeError):
                        score = None

                # Time and memory
                time_ms = item.get('usedTime')
                if time_ms is not None:
                    try:
                        time_ms = int(time_ms)
                    except (ValueError, TypeError):
                        time_ms = None

                memory_kb = item.get('usedMemory')
                if memory_kb is not None:
                    try:
                        memory_kb = int(memory_kb)
                    except (ValueError, TypeError):
                        memory_kb = None

                # Language
                lang_id = str(item.get('languageId', ''))
                language = _LANG_MAP.get(lang_id, f'Language {lang_id}' if lang_id else None)

                record_id = f"{problem_id}/{sub_uuid}"

                yield ScrapedSubmission(
                    platform_record_id=record_id,
                    problem_id=problem_id,
                    status=status,
                    score=score,
                    language=language,
                    time_ms=time_ms,
                    memory_kb=memory_kb,
                    submitted_at=submitted_at or datetime.utcnow(),
                )

        except CoderlandsSessionExpired:
            raise
        except Exception as e:
            self.logger.error(
                f"Error fetching submissions for problem {problem_id}: {e}"
            )

    def fetch_problem_submissions_by_uuid(
        self, problem_uuid: str
    ) -> list[ScrapedSubmission]:
        """Public method for manual resync: fetch all submissions for a problem UUID.

        Returns a list (not generator) since this is used by the API endpoint.
        """
        # First resolve the problem number from mDetail of any submission,
        # or from getClassWorkOne
        try:
            result = self._api_get(
                f'/server/student/stady/getClassWorkOne'
                f'?uuid={problem_uuid}&lessonUuid=personalCenter'
            )
            data = result.get('data', result) if isinstance(result, dict) else result
            problem_no = str(data.get('problemNo', '')) if isinstance(data, dict) else ''
            problem_id = f"P{problem_no}" if problem_no else problem_uuid
        except Exception:
            problem_id = problem_uuid

        return list(self._fetch_problem_submissions(problem_id, problem_uuid))

    # ── Helpers ──

    @staticmethod
    def _parse_time(time_str: str) -> datetime | None:
        """Parse Coderlands time strings (e.g. '2024-01-15 14:30:00')."""
        if not time_str:
            return None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return None
