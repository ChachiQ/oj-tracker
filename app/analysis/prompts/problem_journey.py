"""
Prompt template for analyzing a student's journey from WA to AC on a problem.
"""
from __future__ import annotations


def build_problem_journey_prompt(
    problem_title: str,
    problem_description: str | None,
    submissions_timeline: list[dict],
    student_age: int | None = None,
    student_grade: str | None = None,
) -> list[dict]:
    """Build the prompt messages for problem journey analysis.

    Args:
        problem_title: Title of the problem.
        problem_description: Full problem description text, or None.
        submissions_timeline: List of dicts with keys:
            - attempt_number (int)
            - status (str)
            - score (int or None)
            - source_code (str or None)
            - submitted_at (str)
        student_age: Student's age for age-appropriate feedback.
        student_grade: Student's grade level.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    age_context = ""
    if student_age and student_grade:
        age_context = f"\n学生信息：{student_age}岁，{student_grade}\n"

    timeline_text = ""
    for sub in submissions_timeline:
        timeline_text += (
            f"\n### 第{sub['attempt_number']}次提交 "
            f"({sub['submitted_at']}) - {sub['status']} "
            f"(得分:{sub.get('score', '?')})\n"
            f"```cpp\n{sub['source_code'] or '(代码未获取)'}\n```\n"
        )

    return [
        {
            "role": "user",
            "content": f"""你是一位信息学竞赛教练，请分析学生攻克以下题目的全过程。
{age_context}
## 题目：{problem_title}
{problem_description or '(题目描述未获取)'}

## 提交时间线：
{timeline_text}

请以JSON格式返回分析结果：
{{
  "total_attempts": 总尝试次数,
  "journey_summary": "攻克过程总结",
  "key_breakthroughs": ["每次关键修改的描述"],
  "ineffective_attempts": ["无效尝试的描述(如有)"],
  "final_solution_quality": "最终解法质量评价(优秀/良好/及格/需改进)",
  "algorithm_understanding": "学生对算法的理解程度评价",
  "suggestions": ["后续改进建议"],
  "learned_knowledge": ["通过此题掌握的知识点"]
}}""",
        }
    ]
