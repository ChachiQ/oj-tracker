from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import Student, Problem, Submission, PlatformAccount, Tag
from app.services.stats_service import StatsService
from app.analysis.engine import AnalysisEngine

api_bp = Blueprint('api', __name__, url_prefix='/api')


def _verify_student(student_id):
    """Verify that the current user owns this student."""
    student = Student.query.get(student_id)
    if not student or student.parent_id != current_user.id:
        return None
    return student


@api_bp.route('/dashboard/<int:student_id>')
@login_required
def dashboard_data(student_id):
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = StatsService.get_dashboard_data(student_id)
    return jsonify(data)


@api_bp.route('/knowledge/<int:student_id>')
@login_required
def knowledge_data(student_id):
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = StatsService.get_knowledge_graph_data(student_id)
    return jsonify(data)


@api_bp.route('/weakness/<int:student_id>')
@login_required
def weakness_data(student_id):
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = StatsService.get_weakness_data(student_id)
    return jsonify(data)


@api_bp.route('/trend/<int:student_id>')
@login_required
def trend_data(student_id):
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = StatsService.get_trend_data(student_id)
    return jsonify(data)


@api_bp.route('/submissions/<int:student_id>')
@login_required
def submissions(student_id):
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    account_ids = [
        a.id
        for a in PlatformAccount.query.filter_by(
            student_id=student_id
        ).all()
    ]
    query = Submission.query.filter(
        Submission.platform_account_id.in_(account_ids)
    )

    # Optional filters
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(
        Submission.submitted_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for sub in pagination.items:
        problem = sub.problem
        items.append({
            'id': sub.id,
            'platform_record_id': sub.platform_record_id,
            'problem_title': (
                problem.title if problem else sub.problem_id_ref
            ),
            'problem_id': problem.problem_id if problem else '',
            'platform': (
                sub.platform_account.platform
                if sub.platform_account
                else ''
            ),
            'status': sub.status,
            'score': sub.score,
            'language': sub.language,
            'time_ms': sub.time_ms,
            'memory_kb': sub.memory_kb,
            'submitted_at': (
                sub.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
                if sub.submitted_at
                else ''
            ),
        })

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    })


@api_bp.route('/problems')
@login_required
def problem_list():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    platform = request.args.get('platform')
    tag_name = request.args.get('tag')
    difficulty = request.args.get('difficulty', type=int)

    query = Problem.query
    if platform:
        query = query.filter_by(platform=platform)
    if tag_name:
        query = query.filter(Problem.tags.any(Tag.name == tag_name))
    if difficulty:
        query = query.filter_by(difficulty=difficulty)

    pagination = query.order_by(
        Problem.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for p in pagination.items:
        items.append({
            'id': p.id,
            'platform': p.platform,
            'problem_id': p.problem_id,
            'title': p.title,
            'difficulty': p.difficulty,
            'url': p.url,
            'tags': [t.display_name for t in p.tags],
            'ai_problem_type': p.ai_problem_type,
        })

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    })
