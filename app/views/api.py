import json

from flask import Blueprint, jsonify, request, Response, stream_with_context
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


@api_bp.route('/knowledge/<int:student_id>/analyze', methods=['POST'])
@login_required
def knowledge_analyze(student_id):
    """Trigger AI knowledge assessment, streaming progress via SSE."""
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403

    from app.analysis.knowledge_analyzer import KnowledgeAnalyzer

    def generate():
        try:
            analyzer = KnowledgeAnalyzer(student_id)
            for progress in analyzer.analyze_with_progress():
                payload = {
                    "step": progress["step"],
                    "message": progress["message"],
                }
                if "detail" in progress:
                    payload["detail"] = progress["detail"]
                if "assessment" in progress:
                    payload["assessment"] = progress["assessment"]
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@api_bp.route('/knowledge/<int:student_id>/assessment')
@login_required
def knowledge_assessment(student_id):
    """Get all knowledge assessment history for a student."""
    if not _verify_student(student_id):
        return jsonify({'error': 'Unauthorized'}), 403

    from app.analysis.knowledge_analyzer import KnowledgeAnalyzer
    analyzer = KnowledgeAnalyzer(student_id)
    items = analyzer.get_all()
    return jsonify({
        'has_assessment': len(items) > 0,
        'items': items,
    })


@api_bp.route('/knowledge/<int:student_id>/assessment/<int:log_id>', methods=['DELETE'])
@login_required
def knowledge_assessment_delete(student_id, log_id):
    """Delete a specific knowledge assessment report."""
    student = _verify_student(student_id)
    if not student:
        return jsonify({'error': 'Unauthorized'}), 403

    from app.models import AnalysisLog
    log = AnalysisLog.query.get(log_id)
    if not log or log.student_id != student_id or log.log_type != 'knowledge':
        return jsonify({'error': '报告不存在'}), 404

    from app.analysis.knowledge_analyzer import KnowledgeAnalyzer
    KnowledgeAnalyzer.delete(log_id)
    return jsonify({'success': True})


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
