import json

from app.models import Student, PlatformAccount, Submission, Problem, Tag
from app.analysis.engine import AnalysisEngine
from app.analysis.weakness import WeaknessDetector
from app.analysis.trend import TrendAnalyzer


class StatsService:
    @staticmethod
    def get_dashboard_data(student_id: int) -> dict:
        engine = AnalysisEngine(student_id)
        return {
            'basic': engine.get_basic_stats(),
            'weekly': engine.get_weekly_stats(1),
            'streak': engine.get_streak_days(),
            'status_dist': engine.get_status_distribution(),
            'difficulty_dist': engine.get_difficulty_distribution(),
            'heatmap': engine.get_heatmap_data(),
            'tag_scores': engine.get_tag_scores(),
            'first_ac_rate': engine.get_first_ac_rate(),
        }

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
            stages[stage_num] = {
                'total': len(stage_tags),
                'involved': len(involved),
                'mastered': len(mastered),
                'coverage': (
                    round(len(involved) / len(stage_tags) * 100)
                    if stage_tags
                    else 0
                ),
                'mastery': (
                    round(len(mastered) / len(involved) * 100)
                    if involved
                    else 0
                ),
            }

        return {'nodes': nodes, 'links': links, 'stages': stages}

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
