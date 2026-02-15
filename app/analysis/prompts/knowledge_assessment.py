"""
Prompt template for knowledge graph AI assessment.

Generates a comprehensive knowledge mastery evaluation based on a student's
tag scores, stage progress, and weakness data.
"""
from __future__ import annotations


def build_knowledge_assessment_prompt(
    student_name: str,
    student_age: int | None,
    student_grade: str | None,
    stage_stats: dict,
    top_tags: list[dict],
    weak_tags: list[dict],
    basic_stats: dict,
    previous_findings: list | None = None,
    previous_assessment: dict | None = None,
    recent_stats: dict | None = None,
    upcoming_contests: list[dict] | None = None,
    submission_insights: list[dict] | None = None,
) -> list[dict]:
    """Build prompt messages for knowledge assessment.

    Args:
        student_name: Student's display name.
        student_age: Student's age, or None.
        student_grade: Student's grade level, or None.
        stage_stats: Dict mapping stage number to {total, involved, mastered, coverage, mastery}.
        top_tags: List of dicts with tag score info, sorted by score desc (top 20).
        weak_tags: List of weakness dicts from WeaknessDetector.
        basic_stats: Basic stats dict from AnalysisEngine.
        previous_findings: Key findings from the last knowledge assessment, or None.
        previous_assessment: Full assessment dict from the last report, or None.
        recent_stats: Recent activity stats since last report, or None.
        upcoming_contests: List of upcoming contest dicts, or None.
        submission_insights: List of per-tag code review insights, or None.

    Returns:
        List of message dicts suitable for LLM chat API.
    """
    age_part = f"，{student_age}岁" if student_age else ""
    grade_part = f"，{student_grade}" if student_grade else ""

    stage_names = {
        1: "语法基础", 2: "基础算法", 3: "CSP-J",
        4: "CSP-S", 5: "省选", 6: "NOI",
    }

    # Format stage progress
    stage_lines = []
    for sid in range(1, 7):
        s = stage_stats.get(sid, stage_stats.get(str(sid), {}))
        if not s:
            continue
        stage_lines.append(
            f"- {stage_names.get(sid, f'阶段{sid}')}: "
            f"覆盖率 {s.get('coverage', 0)}%, "
            f"掌握率 {s.get('mastery', 0)}%, "
            f"涉及 {s.get('involved', 0)}/{s.get('total', 0)} 个知识点, "
            f"掌握 {s.get('mastered', 0)} 个"
        )
    stage_text = "\n".join(stage_lines) if stage_lines else "(无阶段数据)"

    # Format top knowledge points
    top_lines = []
    for t in top_tags[:20]:
        top_lines.append(
            f"- {t['display_name']} (阶段{t['stage']}): "
            f"评分 {t['score']}, 通过率 {t['pass_rate']}%, "
            f"已解 {t['solved']}/{t['attempted']} 题"
        )
    top_text = "\n".join(top_lines) if top_lines else "(无知识点数据)"

    # Format weaknesses
    weak_lines = []
    for w in weak_tags[:15]:
        weak_lines.append(
            f"- [{w['severity']}] {w['display_name']} (阶段{w['stage']}): "
            f"{w['reason']}"
        )
    weak_text = "\n".join(weak_lines) if weak_lines else "(无明显薄弱点)"

    # Format basic stats
    stats_text = (
        f"总提交 {basic_stats.get('total_submissions', 0)} 次, "
        f"AC {basic_stats.get('ac_submissions', 0)} 次, "
        f"尝试 {basic_stats.get('unique_attempted', 0)} 题, "
        f"解决 {basic_stats.get('unique_solved', 0)} 题, "
        f"通过率 {basic_stats.get('pass_rate', 0)}%"
    )

    # Format previous assessment (full context, not just findings)
    prev_section = ""
    if previous_assessment:
        prev_level = previous_assessment.get("overall_level", "")
        prev_summary = previous_assessment.get("summary", "")
        prev_plan_lines = []
        for item in (previous_assessment.get("training_plan") or [])[:3]:
            tag_display = item.get("tag_display", item.get("tag", ""))
            suggestion = item.get("suggestion", "")
            prev_plan_lines.append(f"  - {tag_display}: {suggestion}")
        prev_plan_text = "\n".join(prev_plan_lines) if prev_plan_lines else "  (无)"

        prev_section = f"""
## 上次评估结果
- 整体水平: {prev_level}
- 总结: {prev_summary}
- 训练建议 (前3条):
{prev_plan_text}
"""
    elif previous_findings:
        prev_text = "\n".join(f"- {f}" for f in previous_findings)
        prev_section = f"""
## 上次分析的关键发现
{prev_text}
"""
    else:
        prev_section = """
## 上次分析的关键发现
(首次分析，无历史数据)
"""

    # Format recent stats
    recent_section = ""
    if recent_stats:
        recent_section = f"""
## 近期做题情况（自上次分析以来）
- 提交次数: {recent_stats.get('submissions', 0)}
- AC 次数: {recent_stats.get('ac_count', 0)}
- 新解决题目: {recent_stats.get('unique_solved', 0)}
- 活跃天数: {recent_stats.get('active_days', 0)}
- 通过率: {recent_stats.get('pass_rate', 0)}%
"""

    # Format submission insights
    insights_section = ""
    if submission_insights:
        insight_lines = []
        for ins in submission_insights:
            parts = [f"- {ins['tag_display']} (阶段{ins['stage']})"]
            if ins.get('strengths'):
                parts.append(f"  优点: {'; '.join(ins['strengths'][:3])}")
            if ins.get('issues'):
                parts.append(f"  问题: {'; '.join(ins['issues'][:3])}")
            if ins.get('mastery_level'):
                parts.append(f"  掌握度: {ins['mastery_level']}")
            insight_lines.append("\n".join(parts))
        insights_section = f"""
## AI 代码分析洞察（基于学生代码审查）
{chr(10).join(insight_lines)}
"""

    # Format upcoming contests
    contest_section = ""
    if upcoming_contests:
        contest_lines = []
        for c in upcoming_contests:
            contest_lines.append(
                f"- {c['name']} ({c['date']}, 距今 {c['days_until']} 天): {c['description']}"
            )
        contest_section = f"""
## 近期重要赛事
{chr(10).join(contest_lines)}
"""

    return [
        {
            "role": "user",
            "content": f"""你是一位资深信息学竞赛教练，请基于以下数据对学生的知识掌握情况进行综合评估。

学生：{student_name}{age_part}{grade_part}

## 总体统计
{stats_text}

## 各阶段进度
{stage_text}

## 知识点评分 TOP 20（按能力评分排序）
{top_text}

## 薄弱知识点
{weak_text}
{prev_section}{recent_section}{insights_section}{contest_section}
请严格按以下 JSON 格式返回评估结果（不要包含任何 JSON 以外的文字）：
```json
{{
  "overall_level": "当前整体水平的简短描述，如：CSP-J 入门阶段",
  "summary": "整体评价，2-3句话概括学生的学习状态和进度",
  "strengths": ["优势1", "优势2", "优势3"],
  "weaknesses": ["不足1", "不足2", "不足3"],
  "stage_assessments": {{
    "1": "对语法基础阶段的简短评价",
    "2": "对基础算法阶段的简短评价"
  }},
  "training_plan": [
    {{"priority": 1, "tag": "知识点英文名", "tag_display": "知识点中文名", "suggestion": "具体训练建议"}},
    {{"priority": 2, "tag": "知识点英文名", "tag_display": "知识点中文名", "suggestion": "具体训练建议"}}
  ],
  "next_milestone": "建议的下一个学习目标",
  "encouragement": "对学生近期学习的鼓励，1-2句话，要具体提到实际进步",
  "contest_preparation": [
    {{"contest": "赛事名称", "days_until": 天数, "advice": "针对性备赛建议"}}
  ]
}}
```

要求：
1. stage_assessments 只包含学生已有涉及的阶段
2. training_plan 按优先级排列，最多5条
3. 评价要结合学生年龄/年级，给出适龄的建议
4. 语气专业但鼓励，面向家长阅读
5. encouragement 要具体提到学生的实际进步，肯定努力
6. 如有近期赛事，结合当前水平给出针对性备赛建议；无赛事时 contest_preparation 返回空数组 []
7. 如有上次评估结果，对比分析进步和变化
8. 如有AI代码分析洞察，结合代码审查中发现的具体优缺点来评估知识掌握程度""",
        }
    ]
