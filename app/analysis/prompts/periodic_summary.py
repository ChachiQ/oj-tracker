"""
Prompt template for weekly/monthly summary analysis.

Generates a structured JSON summary of a student's performance over a period,
including comparisons with previous periods when available.
"""
from __future__ import annotations


def build_periodic_summary_prompt(
    period_type: str,
    period_start: str,
    period_end: str,
    stats_summary: str,
    error_patterns_top5: str,
    typical_errors: str,
    previous_summary: str | None = None,
    student_age: int | None = None,
    student_grade: str | None = None,
) -> list[dict]:
    """Build prompt messages for periodic summary analysis.

    Args:
        period_type: '周' for weekly, '月' for monthly.
        period_start: Start date string (e.g. '2025.01.01').
        period_end: End date string (e.g. '2025.01.07').
        stats_summary: Formatted text of key statistics for the period.
        error_patterns_top5: Top 5 most frequent error patterns as text.
        typical_errors: Representative error cases as text.
        previous_summary: Summary text from the previous period, or None.
        student_age: Student's age for context.
        student_grade: Student's grade level.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    prev_context = ""
    if previous_summary:
        prev_context = f"\n## 上期分析摘要\n{previous_summary}\n"

    age_context = ""
    if student_age and student_grade:
        age_context = f"\n学生信息：{student_age}岁，{student_grade}\n"

    return [
        {
            "role": "user",
            "content": f"""你是一位信息学竞赛教练，请对学生的{period_type}学习情况进行综合分析。
{age_context}
## 时间段：{period_start} 至 {period_end}

## 本期统计概要
{stats_summary}

## 本期高频错误模式 TOP5
{error_patterns_top5}

## 典型错误案例
{typical_errors}
{prev_context}
请以JSON格式返回：
{{
  "overall_assessment": "本期整体评价",
  "progress_vs_previous": "与上期对比的进步/退步项(如有上期数据)",
  "persistent_weaknesses": ["持续性弱点"],
  "improvements": ["进步之处"],
  "focus_areas": ["下期重点训练方向"],
  "specific_recommendations": ["具体练习建议"],
  "encouragement": "给学生的鼓励语"
}}""",
        }
    ]
