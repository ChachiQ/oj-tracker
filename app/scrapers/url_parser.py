"""Parse OJ problem URLs into (platform_name, problem_id) tuples."""
from __future__ import annotations

import re


_PATTERNS = [
    # Luogu: luogu.com.cn/problem/P1001
    (re.compile(r'luogu\.com\.cn/problem/([A-Za-z0-9_]+)'), 'luogu'),
    # BBCOJ: bbcoj.cn/problem/BA405  or  bbcoj.cn/training/53/problem/BA405(/full-screen)
    (re.compile(r'bbcoj\.cn/(?:training/\d+/)?problem/([A-Za-z0-9_]+)'), 'bbcoj'),
    # YBT: ybt.ssoier.cn:8088/problem_show.php?pid=1234
    (re.compile(r'ybt\.ssoier\.cn(?::\d+)?/problem_show\.php\?pid=(\d+)'), 'ybt'),
    # CTOJ: ctoj.ac/d/{domain}/p/{pid}
    (re.compile(r'ctoj\.ac/d/([^/]+)/p/([^/?\s]+)'), 'ctoj'),
]


def parse_problem_url(url: str) -> tuple[str, str] | None:
    """Parse an OJ problem URL, returning (platform_name, problem_id) or None."""
    if not url:
        return None

    for pattern, platform in _PATTERNS:
        m = pattern.search(url)
        if m:
            if platform == 'ctoj':
                # problem_id = "domain/pid"
                return (platform, f"{m.group(1)}/{m.group(2)}")
            return (platform, m.group(1))

    return None
