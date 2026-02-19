"""
Prompt template for comprehensive problem analysis.

Merges classification, solution approach, and full solution into a single
LLM call to reduce latency from 3 serial requests to 1.
"""
from __future__ import annotations

from .problem_classify import _build_tag_reference


def build_problem_comprehensive_prompt(
    title: str,
    platform: str,
    difficulty_raw: str | None,
    description: str | None,
    input_desc: str | None = None,
    output_desc: str | None = None,
    examples: str | None = None,
    hint: str | None = None,
    platform_tags: list[str] | None = None,
) -> list[dict]:
    """Build prompt that combines classify + solution + full_solution.

    Args:
        title: Problem title.
        platform: OJ platform name.
        difficulty_raw: Raw difficulty from the platform (if any).
        description: Problem description text.
        input_desc: Input specification.
        output_desc: Output specification.
        examples: Sample input/output.
        hint: Hints or data range constraints.
        platform_tags: Original tags from the OJ platform.

    Returns:
        List of message dicts for LLM chat API.
    """
    tag_reference = _build_tag_reference()

    platform_tags_str = ''
    if platform_tags:
        platform_tags_str = f"\n平台原始标签：{', '.join(platform_tags)}"

    return [
        {
            "role": "user",
            "content": f"""你是信息学竞赛题目分类专家兼资深教练。请对以下题目进行完整分析，包括分类、解题思路和完整代码。

## 题目信息
标题：{title}
平台：{platform}
平台难度：{difficulty_raw or '未知'}{platform_tags_str}

题目描述：
{description or '(无描述)'}

输入说明：{input_desc or '(无)'}
输出说明：{output_desc or '(无)'}
样例：{examples or '(无)'}
提示/数据范围：{hint or '(无)'}

## 标签参考列表（classify 部分的 tag_name 必须从以下列表中选择）
{tag_reference}

## 要求
请先仔细分析题目，然后一次性输出以下三部分。

**classify 部分要求**：
1. 从标签参考列表中选择 1-5 个最相关的 tag_name（必须精确匹配列表中的 tag_name）
2. 对每个选中的标签说明其重要性（核心/辅助）
3. 给出综合难度评分 1-10（1=入门，3=普及，5=提高，7=省选，9=NOI）

**solution 部分要求**：
- approach 限 2-3 句话
- thinking_steps 清晰分步

**full_solution 部分要求**：
- code 为可直接提交的完整 C++ 代码，只保留必要注释
- 代码风格：使用 #include <bits/stdc++.h> 和 using namespace std;，不要用 ios::sync_with_stdio / cin.tie
- explanation 限 3-5 句关键说明
- alternative_approaches 最多 2 个，每个一句话

请严格返回以下 JSON 格式（不要包含任何 JSON 以外的文字）：
{{
  "classify": {{
    "problem_type": "题型简述",
    "knowledge_points": [
      {{"tag_name": "标签名", "importance": "核心/辅助"}}
    ],
    "difficulty_assessment": {{
      "thinking": 3,
      "coding": 2,
      "math": 1,
      "overall": 3
    }}
  }},
  "solution": {{
    "approach": "解题思路概述（2-3句话）",
    "algorithm": "核心算法/数据结构名称",
    "complexity": {{"time": "O(...)", "space": "O(...)"}},
    "key_points": ["关键实现要点1", "关键实现要点2"],
    "common_pitfalls": ["常见错误1", "常见错误2"],
    "thinking_steps": ["第一步：分析题意...", "第二步：设计算法...", "第三步：处理边界..."]
  }},
  "full_solution": {{
    "approach": "解题思路概述",
    "code": "完整的 C++ 代码",
    "explanation": "关键说明",
    "complexity": {{"time": "O(...)", "space": "O(...)"}},
    "alternative_approaches": [
      {{"name": "替代方法名称", "brief": "简要说明"}}
    ]
  }}
}}""",
        }
    ]
