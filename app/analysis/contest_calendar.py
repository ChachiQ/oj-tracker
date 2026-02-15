"""
Contest calendar for competitive programming events.

Provides upcoming contest information for AI assessment prompts,
enabling contest-aware preparation advice.
"""
from __future__ import annotations

from datetime import date, timedelta


CONTEST_SCHEDULE = [
    {
        "name": "CSP-J/S 第一轮",
        "month": 9,
        "day": 15,
        "description": "CSP-J/S 初赛（笔试）",
        "relevant_stages": [3, 4],
    },
    {
        "name": "CSP-J/S 第二轮",
        "month": 10,
        "day": 20,
        "description": "CSP-J/S 复赛（上机）",
        "relevant_stages": [3, 4],
    },
    {
        "name": "NOIP",
        "month": 11,
        "day": 25,
        "description": "全国青少年信息学奥林匹克联赛",
        "relevant_stages": [4, 5],
    },
    {
        "name": "NOI 冬令营",
        "month": 1,
        "day": 28,
        "description": "NOI 冬令营（Winter Camp）",
        "relevant_stages": [5, 6],
    },
    {
        "name": "APIO",
        "month": 5,
        "day": 15,
        "description": "亚太地区信息学奥林匹克",
        "relevant_stages": [5, 6],
    },
    {
        "name": "NOI",
        "month": 7,
        "day": 15,
        "description": "全国青少年信息学奥林匹克竞赛",
        "relevant_stages": [6],
    },
]


def get_upcoming_contests(months_ahead: int = 6) -> list[dict]:
    """Return contests happening within the next *months_ahead* months.

    Each returned dict contains the original contest fields plus:
        - ``date``: formatted date string (YYYY-MM-DD)
        - ``days_until``: integer days from today

    Results are sorted by ``days_until`` ascending.
    """
    today = date.today()
    cutoff = today + timedelta(days=months_ahead * 30)
    results: list[dict] = []

    for contest in CONTEST_SCHEDULE:
        # Check current year and next year to handle cross-year lookups
        for year in (today.year, today.year + 1):
            try:
                contest_date = date(year, contest["month"], contest["day"])
            except ValueError:
                # Handle months with fewer days
                contest_date = date(year, contest["month"], 28)

            if today <= contest_date <= cutoff:
                days_until = (contest_date - today).days
                results.append({
                    "name": contest["name"],
                    "date": contest_date.strftime("%Y-%m-%d"),
                    "days_until": days_until,
                    "description": contest["description"],
                    "relevant_stages": contest["relevant_stages"],
                })

    results.sort(key=lambda c: c["days_until"])
    return results
