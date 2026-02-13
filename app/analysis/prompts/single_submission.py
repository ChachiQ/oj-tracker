"""
Prompt template for analyzing a single student submission.
"""
from __future__ import annotations


def build_single_submission_prompt(
    problem_title: str,
    problem_description: str | None,
    source_code: str,
    status: str,
    score: int | None = None,
    student_age: int | None = None,
    student_grade: str | None = None,
) -> list[dict]:
    """Build the prompt messages for single submission analysis.

    Args:
        problem_title: Title of the problem.
        problem_description: Full problem description text, or None.
        source_code: Student's submitted source code.
        status: Judge result status (e.g. 'AC', 'WA', 'TLE').
        score: Numeric score if available.
        student_age: Student's age for age-appropriate feedback.
        student_grade: Student's grade level.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    age_context = ""
    if student_age and student_grade:
        age_context = (
            f"\n学生信息：{student_age}岁，{student_grade}，"
            f"请用适合该年龄段的语言给出建议。\n"
        )

    return [
        {
            "role": "user",
            "content": f"""你是一位信息学竞赛教练，请分析以下学生的代码提交。
{age_context}
## 题目：{problem_title}
{problem_description or '(题目描述未获取)'}

## 学生代码：
```cpp
{source_code}
```

## 判题结果：{status}，得分：{score or '未知'}

请以JSON格式返回分析结果：
{{
  "error_type": "错误类型(如：边界条件、算法复杂度、数据类型溢出、逻辑错误等)",
  "error_description": "具体错误描述",
  "error_location": "错误代码位置(行号或代码片段)",
  "correct_approach": "正确的做法",
  "suggestion": "给学生的改进建议",
  "knowledge_points": ["涉及的知识点列表"],
  "difficulty_for_student": "对该学生而言的难度评估(简单/适中/困难)"
}}""",
        }
    ]
