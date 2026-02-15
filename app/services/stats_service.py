import json

from app.models import Student, PlatformAccount, Submission, Problem, Tag
from app.analysis.engine import AnalysisEngine
from app.analysis.weakness import WeaknessDetector
from app.analysis.trend import TrendAnalyzer


class StatsService:
    @staticmethod
    def get_dashboard_data(student_id: int) -> dict:
        # Check if student has any platform accounts
        account_ids = [a.id for a in PlatformAccount.query.filter_by(student_id=student_id).all()]
        if not account_ids:
            return {
                'stats': {'total_problems': 0, 'ac_count': 0, 'week_submissions': 0, 'streak_days': 0},
                'tag_scores': {}, 'heatmap': [], 'difficulty_dist': {},
                'recent_submissions': [], 'weaknesses': [],
                'status_dist': {}, 'first_ac_rate': 0,
                'basic': {}, 'weekly': {}, 'streak': 0,
                'weekly_trend': [], 'platform_stats': [],
            }

        engine = AnalysisEngine(student_id)
        basic = engine.get_basic_stats()
        weekly = engine.get_weekly_stats(1)

        recent_submissions = StatsService._get_recent_submissions(student_id, limit=15)
        weaknesses = StatsService.get_weakness_data(student_id)
        trend_analyzer = TrendAnalyzer(student_id)

        return {
            'stats': {
                'total_problems': basic.get('unique_attempted', 0),
                'ac_count': basic.get('ac_submissions', 0),
                'week_submissions': weekly.get('submissions', 0) if isinstance(weekly, dict) else 0,
                'streak_days': engine.get_streak_days(),
            },
            'tag_scores': engine.get_tag_scores(),
            'heatmap': engine.get_heatmap_data(),
            'difficulty_dist': engine.get_difficulty_distribution(),
            'recent_submissions': recent_submissions,
            'weaknesses': weaknesses,
            # Preserve original fields for backward compat
            'basic': basic,
            'weekly': weekly,
            'streak': engine.get_streak_days(),
            'status_dist': engine.get_status_distribution(),
            'first_ac_rate': engine.get_first_ac_rate(),
            'weekly_trend': trend_analyzer.get_weekly_trend(12),
            'platform_stats': StatsService._get_platform_stats(account_ids),
        }

    @staticmethod
    def _get_recent_submissions(student_id: int, limit: int = 15) -> list:
        account_ids = [a.id for a in PlatformAccount.query.filter_by(student_id=student_id).all()]
        if not account_ids:
            return []
        submissions = (
            Submission.query
            .filter(Submission.platform_account_id.in_(account_ids))
            .order_by(Submission.submitted_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for sub in submissions:
            problem = Problem.query.get(sub.problem_id_ref) if sub.problem_id_ref else None
            account = PlatformAccount.query.get(sub.platform_account_id)
            result.append({
                'platform': account.platform if account else '-',
                'problem_title': problem.title if problem else '-',
                'problem_id': problem.id if problem else None,
                'platform_pid': problem.problem_id if problem else sub.platform_record_id,
                'status': sub.status,
                'submitted_at': sub.submitted_at.strftime('%Y-%m-%d %H:%M') if sub.submitted_at else '-',
            })
        return result

    @staticmethod
    def get_knowledge_graph_data(student_id: int) -> dict:
        """Get data for knowledge graph visualization."""
        engine = AnalysisEngine(student_id)
        tag_scores = engine.get_tag_scores()

        # Build nodes and links
        all_tags = Tag.query.order_by(Tag.stage, Tag.name).all()
        nodes = []
        for tag in all_tags:
            score_info = tag_scores.get(tag.name)
            if score_info:
                if score_info['pass_rate'] >= 50 and score_info['solved'] >= 3:
                    status = 'mastered'  # green
                elif score_info['pass_rate'] < 30:
                    status = 'weak'  # red
                else:
                    status = 'learning'  # yellow
                size = min(30, 10 + score_info['solved'] * 2)
            else:
                status = 'untouched'  # gray
                size = 10

            # Fetch recommended problems for this tag
            problems = Problem.query.filter(Problem.tags.any(Tag.name == tag.name)).limit(5).all()
            recommended = [
                {'id': p.id, 'title': p.title, 'platform': p.platform}
                for p in problems
            ]

            nodes.append({
                'id': tag.name,
                'name': tag.display_name,
                'stage': tag.stage,
                'category': tag.category,
                'status': status,
                'size': size,
                'score': score_info['score'] if score_info else 0,
                'solved': score_info['solved'] if score_info else 0,
                'attempted': score_info['attempted'] if score_info else 0,
                'pass_rate': score_info['pass_rate'] if score_info else 0,
                'first_ac_rate': score_info['first_ac_rate'] if score_info else 0,
                'avg_attempts': score_info['avg_attempts'] if score_info else 0,
                'recommended_problems': recommended,
            })

        # Build links from prerequisite_tags
        links = []
        for tag in all_tags:
            if tag.prerequisite_tags:
                try:
                    prereqs = json.loads(tag.prerequisite_tags)
                    for prereq in prereqs:
                        links.append({'source': prereq, 'target': tag.name})
                except (json.JSONDecodeError, TypeError):
                    pass

        # Stage summaries
        stages = {}
        for stage_num in range(1, 7):
            stage_tags = [t for t in all_tags if t.stage == stage_num]
            stage_nodes = [n for n in nodes if n['stage'] == stage_num]
            involved = [
                n for n in stage_nodes if n['status'] != 'untouched'
            ]
            mastered = [
                n for n in stage_nodes if n['status'] == 'mastered'
            ]
            learning = [
                n for n in stage_nodes if n['status'] == 'learning'
            ]
            weak = [
                n for n in stage_nodes if n['status'] == 'weak'
            ]
            stages[stage_num] = {
                'total': len(stage_tags),
                'involved': len(involved),
                'mastered': len(mastered),
                'learning': len(learning),
                'weak': len(weak),
                'coverage': (
                    round(len(involved) / len(stage_tags) * 100)
                    if stage_tags
                    else 0
                ),
                'mastery': (
                    round(len(mastered) / len(stage_tags) * 100)
                    if stage_tags
                    else 0
                ),
                'tags': [
                    {
                        'name': n['id'],
                        'display_name': n['name'],
                        'status': n['status'],
                        'score': n['score'],
                        'solved': n['solved'],
                        'attempted': n['attempted'],
                        'pass_rate': n['pass_rate'],
                    }
                    for n in stage_nodes
                ],
            }

        return {'nodes': nodes, 'links': links, 'stages': stages}

    @staticmethod
    def _get_platform_stats(account_ids: list) -> list:
        """Get per-platform submission and AC counts."""
        from collections import defaultdict
        accounts = PlatformAccount.query.filter(PlatformAccount.id.in_(account_ids)).all()
        account_platform = {a.id: a.platform for a in accounts}

        platform_data = defaultdict(lambda: {'submissions': 0, 'ac_count': 0})
        submissions = Submission.query.filter(
            Submission.platform_account_id.in_(account_ids)
        ).all()
        for s in submissions:
            platform = account_platform.get(s.platform_account_id, 'unknown')
            platform_data[platform]['submissions'] += 1
            if s.status == 'AC':
                platform_data[platform]['ac_count'] += 1

        result = []
        for platform, stats in sorted(platform_data.items()):
            total = stats['submissions']
            ac = stats['ac_count']
            result.append({
                'platform': platform,
                'submissions': total,
                'ac_count': ac,
                'pass_rate': round(ac / total * 100, 1) if total > 0 else 0,
            })
        return result

    @staticmethod
    def get_weakness_data(student_id: int) -> list:
        detector = WeaknessDetector(student_id)
        return detector.detect()

    @staticmethod
    def get_trend_data(student_id: int) -> dict:
        analyzer = TrendAnalyzer(student_id)
        return {
            'weekly': analyzer.get_weekly_trend(12),
            'monthly': analyzer.get_monthly_trend(6),
        }
