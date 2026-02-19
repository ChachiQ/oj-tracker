"""
Prompt template for generating a complete AI solution for a problem.
"""
from __future__ import annotations


def build_problem_full_solution_prompt(
    problem_title: str,
    problem_description: str | None,
    input_desc: str | None = None,
    output_desc: str | None = None,
    examples: str | None = None,
    hint: str | None = None,
    difficulty: int = 0,
    problem_type: str | None = None,
) -> list[dict]:
    """Build prompt messages for generating a full problem solution.

    Args:
        problem_title: Title of the problem.
        problem_description: Full problem description text.
        input_desc: Input format description.
        output_desc: Output format description.
        examples: Sample input/output.
        hint: Problem hints.
        difficulty: Numeric difficulty level.
        problem_type: AI-classified problem type, if available.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    sections = [f"## 题目：{problem_title}"]

    if problem_type:
        sections.append(f"题目类型：{problem_type}")
    if difficulty:
        sections.append(f"难度等级：{difficulty}")

    sections.append(f"\n### 题目描述\n{problem_description or '(未获取)'}")

    if input_desc:
        sections.append(f"\n### 输入格式\n{input_desc}")
    if output_desc:
        sections.append(f"\n### 输出格式\n{output_desc}")
    if examples:
        sections.append(f"\n### 样例\n{examples}")
    if hint:
        sections.append(f"\n### 提示\n{hint}")

    problem_text = "\n".join(sections)

    return [
        {
            "role": "user",
            "content": f"""你是一位资深信息学竞赛教练，请为以下题目提供完整的解法，包括思路分析和 C++ 代码。

{problem_text}

要求：
- approach 限 2-3 句话
- code 只保留必要注释，不写多余空行
- 代码风格：使用 #include <bits/stdc++.h> 和 using namespace std;，不要用 ios::sync_with_stdio / cin.tie
- explanation 限 3-5 句关键说明，不要逐行解释
- alternative_approaches 最多 2 个，每个一句话
- 控制总回复在 2000 字以内

请严格按以下 JSON 格式返回（不要包含任何 JSON 以外的文字）：
{{
  "approach": "解题思路概述",
  "code": "完整的 C++ 代码（可以直接提交的）",
  "explanation": "代码逐段解释，说明每个关键部分的作用",
  "complexity": {{"time": "O(...)", "space": "O(...)"}},
  "alternative_approaches": [
    {{"name": "替代方法名称", "brief": "简要说明为什么不选择这个方法"}}
  ]
}}""",
        }
    ]
