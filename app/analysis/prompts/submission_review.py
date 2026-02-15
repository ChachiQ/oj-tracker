"""
Prompt template for reviewing a student's code submission.
"""
from __future__ import annotations


def build_submission_review_prompt(
    problem_title: str,
    problem_description: str | None,
    source_code: str,
    status: str,
    score: int | None = None,
    language: str | None = None,
    student_age: int | None = None,
    student_grade: str | None = None,
) -> list[dict]:
    """Build prompt messages for reviewing a student's code submission.

    Args:
        problem_title: Title of the problem.
        problem_description: Full problem description text.
        source_code: Student's submitted source code.
        status: Judge result status (e.g. 'AC', 'WA', 'TLE').
        score: Numeric score if available.
        language: Programming language used.
        student_age: Student's age for age-appropriate feedback.
        student_grade: Student's grade level.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    age_context = ""
    if student_age and student_grade:
        age_context = (
            f"\n学生信息：{student_age}岁，{student_grade}，"
            f"请结合该年龄段的认知水平进行评价。\n"
        )

    lang_label = language or "C++"

    return [
        {
            "role": "user",
            "content": f"""你是一位资深信息学竞赛教练，请对以下学生的代码提交进行详细审查和评价。
{age_context}
## 题目：{problem_title}
{problem_description or '(题目描述未获取)'}

## 学生代码：
```{lang_label}
{source_code}
```

## 判题结果：{status}，得分：{score or '未知'}

请严格按以下 JSON 格式返回（不要包含任何 JSON 以外的文字）：
{{
  "approach_analysis": "学生的解题思路分析（2-3句话描述学生采用了什么方法）",
  "code_quality": "优秀/良好/一般/需改进",
  "strengths": ["优点1", "优点2"],
  "issues": [
    {{"type": "错误类型(如逻辑错误/边界处理/代码风格)", "description": "具体描述", "location": "代码位置或行号"}}
  ],
  "suggestions": ["改进建议1", "改进建议2"],
  "knowledge_demonstrated": ["体现的知识点1", "体现的知识点2"],
  "mastery_level": "熟练/掌握/了解/不足"
}}""",
        }
    ]
