"""
一次性脚本：修复 AI 分析失败导致的难度残留问题，并重新触发 AI 回填。

问题：bbcoj 爬虫将 difficulty_raw 直接 clamp 到 0-7，部分题目 difficulty=7（省选-），
但 AI 分析失败后没有重置 difficulty，导致题目显示错误的高难度。

用法：
    python fix_difficulty_and_rebackfill.py          # 仅清理数据（dry-run 预览）
    python fix_difficulty_and_rebackfill.py --apply   # 执行清理
    python fix_difficulty_and_rebackfill.py --apply --backfill  # 清理 + 触发 AI 回填
"""

import argparse
import json
import sys

from app import create_app
from app.extensions import db
from app.models import Problem, AnalysisResult


def find_broken_problems():
    """查找需要修复的题目，返回 (problems_to_reset, broken_ar_ids)。"""
    problems_to_reset = []
    broken_ar_ids = []

    # 1. 有 ai_analysis_error 的题目
    with_error = Problem.query.filter(
        Problem.ai_analysis_error.isnot(None),
    ).all()
    for p in with_error:
        problems_to_reset.append(p)

    # 2. ai_analyzed=True 但没有 ai_problem_type 的题目（分类失败残留）
    analyzed_no_type = Problem.query.filter(
        Problem.ai_analyzed.is_(True),
        db.or_(
            Problem.ai_problem_type.is_(None),
            Problem.ai_problem_type == "",
        ),
        Problem.ai_analysis_error.is_(None),  # 排除已在上面处理的
    ).all()
    for p in analyzed_no_type:
        problems_to_reset.append(p)

    # 去重
    seen_ids = set()
    unique = []
    for p in problems_to_reset:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            unique.append(p)
    problems_to_reset = unique

    # 3. 找到对应的损坏 AnalysisResult（problem_classify 类型，无效 JSON 或空 summary）
    for p in problems_to_reset:
        ars = AnalysisResult.query.filter_by(
            problem_id_ref=p.id,
            analysis_type="problem_classify",
        ).all()
        for ar in ars:
            if not ar.result_json or not ar.summary:
                broken_ar_ids.append(ar.id)
                continue
            try:
                json.loads(ar.result_json)
            except (json.JSONDecodeError, TypeError):
                broken_ar_ids.append(ar.id)

    return problems_to_reset, list(set(broken_ar_ids))


def main():
    parser = argparse.ArgumentParser(description="修复 AI 分析失败导致的难度残留")
    parser.add_argument("--apply", action="store_true", help="实际执行修改（默认仅预览）")
    parser.add_argument("--backfill", action="store_true", help="清理后触发 AI 回填")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        problems, broken_ar_ids = find_broken_problems()

        # 统计
        high_diff = [p for p in problems if p.difficulty and p.difficulty >= 7]
        print(f"=== 诊断结果 ===")
        print(f"需要重置的题目总数: {len(problems)}")
        print(f"  其中 difficulty >= 7 的: {len(high_diff)}")
        print(f"需要删除的损坏 AnalysisResult: {len(broken_ar_ids)}")
        print()

        # 按平台分组打印
        by_platform = {}
        for p in problems:
            by_platform.setdefault(p.platform, []).append(p)
        for platform, ps in sorted(by_platform.items()):
            print(f"  [{platform}] {len(ps)} 题")
            for p in ps[:5]:
                print(f"    - {p.problem_id} ({p.title or '无标题'}) "
                      f"difficulty={p.difficulty} ai_analyzed={p.ai_analyzed} "
                      f"error={p.ai_analysis_error[:60] if p.ai_analysis_error else 'None'}")
            if len(ps) > 5:
                print(f"    ... 和另外 {len(ps) - 5} 题")
        print()

        if not args.apply:
            print(">>> 预览模式，未做任何修改。添加 --apply 执行修改。")
            return

        # 执行清理
        print("=== 执行清理 ===")
        for p in problems:
            p.difficulty = 0
            p.ai_analyzed = False
            p.ai_analysis_error = None
        print(f"  已重置 {len(problems)} 道题目 (difficulty→0, ai_analyzed→False)")

        if broken_ar_ids:
            deleted = AnalysisResult.query.filter(
                AnalysisResult.id.in_(broken_ar_ids),
            ).delete(synchronize_session='fetch')
            print(f"  已删除 {deleted} 条损坏的 AnalysisResult")

        db.session.commit()
        print("  数据库已提交。")
        print()

        if args.backfill:
            print("=== 触发 AI 回填 ===")
            print("提示：请通过 Web 界面的「设置 → AI 回填」按钮触发，")
            print("或在后台运行 AIBackfillService.run()。")
            print("清理完成后，这些题目的 ai_analyzed=False，会被自动纳入回填队列。")
        else:
            print(">>> 清理完成。可通过 Web 界面触发 AI 回填来重新分析这些题目。")


if __name__ == "__main__":
    main()
