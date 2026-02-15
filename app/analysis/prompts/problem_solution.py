"""
Prompt template for analyzing a problem's solution approach (no code).
"""
from __future__ import annotations


def build_problem_solution_prompt(
    problem_title: str,
    problem_description: str | None,
    input_desc: str | None = None,
    output_desc: str | None = None,
    examples: str | None = None,
    hint: str | None = None,
    difficulty: int = 0,
    problem_type: str | None = None,
) -> list[dict]:
    """Build prompt messages for problem solution approach analysis.

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
            "content": f"""你是一位资深信息学竞赛教练，请分析以下题目的解题思路。注意：只分析思路，不要给出代码。

{problem_text}

请严格按以下 JSON 格式返回（不要包含任何 JSON 以外的文字）：
{{
  "approach": "解题思路概述（2-3句话）",
  "algorithm": "核心算法/数据结构名称",
  "complexity": {{"time": "O(...)", "space": "O(...)"}},
  "key_points": ["关键实现要点1", "关键实现要点2"],
  "common_pitfalls": ["常见错误1", "常见错误2"],
  "thinking_steps": ["第一步：分析题意...", "第二步：设计算法...", "第三步：处理边界..."]
}}""",
        }
    ]
