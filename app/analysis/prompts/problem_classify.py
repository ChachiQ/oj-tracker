"""
Prompt template for AI-powered problem classification.

Builds a prompt that instructs the LLM to:
- Select knowledge point tags from the available Tag table
- Assess difficulty on a 1-10 scale
- Return structured JSON for M2M tag association
"""
from __future__ import annotations

import time

from app.models import Tag

# Simple TTL cache for tag reference text
_tag_ref_cache: dict[str, object] = {'text': '', 'expires_at': 0.0}
_TAG_REF_TTL = 300  # 5 minutes


def _build_tag_reference() -> str:
    """Build a tag reference list from the Tag table for the prompt.

    Results are cached in memory for 5 minutes to avoid repeated DB queries
    when classifying multiple problems in a batch.
    """
    now = time.monotonic()
    if _tag_ref_cache['text'] and now < _tag_ref_cache['expires_at']:
        return _tag_ref_cache['text']

    tags = Tag.query.order_by(Tag.stage, Tag.name).all()
    lines = []
    current_stage = None
    stage_names = {
        1: '语法基础', 2: '基础算法', 3: 'CSP-J',
        4: 'CSP-S', 5: '省选', 6: 'NOI',
    }
    for tag in tags:
        if tag.stage != current_stage:
            current_stage = tag.stage
            label = stage_names.get(current_stage, f'Stage {current_stage}')
            lines.append(f"\n## Stage {current_stage} - {label}")
        lines.append(f"- {tag.name}: {tag.display_name}")

    result = '\n'.join(lines)
    _tag_ref_cache['text'] = result
    _tag_ref_cache['expires_at'] = now + _TAG_REF_TTL
    return result


def build_classify_prompt(
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
    """Build prompt messages for problem classification.

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
            "content": f"""你是信息学竞赛题目分类专家。请分析以下题目，从标签参考列表中选择合适的知识点标签，并评估难度。

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

## 标签参考列表（必须从以下 tag_name 中选择）
{tag_reference}

## 要求
1. 从标签参考列表中选择 1-5 个最相关的 tag_name（必须精确匹配列表中的 tag_name）
2. 对每个选中的标签说明其重要性（核心/辅助）
3. 给出综合难度评分 1-10（1=入门，3=普及，5=提高，7=省选，9=NOI）
4. 如果平台有难度数据，作为参考但不完全依赖

请严格返回以下 JSON 格式（不要包含其他文字）：
{{
  "problem_type": "题型简述",
  "knowledge_points": [
    {{"tag_name": "标签名", "importance": "核心/辅助"}}
  ],
  "difficulty_assessment": {{
    "thinking": 3,
    "coding": 2,
    "math": 1,
    "overall": 3
  }},
  "brief_solution_idea": "简要解题思路(一句话)"
}}""",
        }
    ]
