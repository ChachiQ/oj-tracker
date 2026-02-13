"""
Prompt template for generating human-readable periodic reports for parents.

Unlike periodic_summary (which returns JSON), this prompt produces a full
narrative report with sections, suitable for direct display to parents.
"""
from __future__ import annotations


def build_periodic_report_prompt(
    period_type: str,
    period_start: str,
    period_end: str,
    stats: str,
    previous_stats: str | None,
    error_analysis: str,
    knowledge_progress: str,
    student_name: str,
    student_age: int | None = None,
    student_grade: str | None = None,
) -> list[dict]:
    """Build prompt messages for generating a parent-facing report.

    Args:
        period_type: '周报' for weekly, '月报' for monthly.
        period_start: Start date string (e.g. '2025.01.01').
        period_end: End date string (e.g. '2025.01.07').
        stats: Formatted current period statistics.
        previous_stats: Previous period statistics for comparison, or None.
        error_analysis: Summary of error patterns and weaknesses.
        knowledge_progress: Knowledge point progress summary.
        student_name: Student's display name.
        student_age: Student's age, or None.
        student_grade: Student's grade level, or None.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    age_part = f"，{student_age}岁" if student_age else ""
    grade_part = f"，{student_grade}" if student_grade else ""

    return [
        {
            "role": "user",
            "content": f"""你是一位信息学竞赛教练，请为家长生成一份{period_type}学习报告。

学生：{student_name}{age_part}{grade_part}

## 本期统计 ({period_start} 至 {period_end})
{stats}

## 上期统计
{previous_stats or '(首次报告，无上期数据)'}

## 错误分析摘要
{error_analysis}

## 知识点进度
{knowledge_progress}

请生成一份结构清晰、语言温和专业的学习报告，包含以下部分：
1. 本期概况（做题数、通过率、活跃天数等关键数据）
2. 进步之处（具体的进步点，用数据支撑）
3. 不足之处（需改进的地方，语气温和不批评）
4. 典型错误分析（挑2-3个有代表性的错误简要分析）
5. 近期训练建议（3-5条具体可操作的建议）
6. 下阶段展望（学习路径建议）

注意：报告面向家长，语言要专业但易懂，对孩子以鼓励为主。""",
        }
    ]
