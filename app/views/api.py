import json

from flask import Blueprint, jsonify, request, Response, stream_with_context
from flask_login import login_required, current_user
from app.models import Student, Problem, Submission, PlatformAccount, Tag, AnalysisResult
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

    from app.models import AnalysisLog
    from app.analysis.knowledge_analyzer import KnowledgeAnalyzer
    analyzer = KnowledgeAnalyzer(student_id)
    items = analyzer.get_all()

    # Nudge metadata: latest report time + new submissions since then
    latest_log = AnalysisLog.query.filter_by(
        student_id=student_id, log_type='knowledge'
    ).order_by(AnalysisLog.created_at.desc()).first()

    latest_report_time = None
    new_submissions_since_report = 0

    account_ids = [
        a.id
        for a in PlatformAccount.query.filter_by(
            student_id=student_id
        ).all()
    ]

    if latest_log:
        from datetime import timezone
        latest_report_time = latest_log.created_at.replace(
            tzinfo=timezone.utc
        ).astimezone().strftime('%Y-%m-%d %H:%M')
        if account_ids:
            new_submissions_since_report = Submission.query.filter(
                Submission.platform_account_id.in_(account_ids),
                Submission.submitted_at > latest_log.created_at
            ).count()
    else:
        # No report yet — count all submissions
        if account_ids:
            new_submissions_since_report = Submission.query.filter(
                Submission.platform_account_id.in_(account_ids)
            ).count()

    return jsonify({
        'has_assessment': len(items) > 0,
        'items': items,
        'latest_report_time': latest_report_time,
        'new_submissions_since_report': new_submissions_since_report,
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


def _user_owns_problem(problem_id):
    """Check that the current user has at least one submission for this problem."""
    problem = Problem.query.get(problem_id)
    if not problem:
        return None

    students = Student.query.filter_by(parent_id=current_user.id).all()
    account_ids = []
    for s in students:
        for a in s.platform_accounts:
            account_ids.append(a.id)

    if not account_ids:
        return None

    has_sub = Submission.query.filter(
        Submission.platform_account_id.in_(account_ids),
        Submission.problem_id_ref == problem.id,
    ).first()

    return problem if has_sub else None


@api_bp.route('/problem/<int:problem_id>/solution', methods=['POST'])
@login_required
def problem_solution(problem_id):
    """Trigger AI solution approach analysis for a problem."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    force = request.args.get('force', '0') == '1'

    from app.analysis.ai_analyzer import AIAnalyzer
    analyzer = AIAnalyzer()
    result = analyzer.analyze_problem_solution(
        problem_id, force=force, user_id=current_user.id,
    )

    if not result:
        return jsonify({'error': 'AI 分析失败，请检查 AI 配置或预算'}), 500

    return jsonify({
        'success': True,
        'analysis': json.loads(result.result_json) if result.result_json else None,
        'analyzed_at': result.analyzed_at.strftime('%Y-%m-%d %H:%M'),
        'ai_model': result.ai_model,
    })


@api_bp.route('/problem/<int:problem_id>/full-solution', methods=['POST'])
@login_required
def problem_full_solution(problem_id):
    """Trigger AI full solution generation for a problem."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    force = request.args.get('force', '0') == '1'

    from app.analysis.ai_analyzer import AIAnalyzer
    analyzer = AIAnalyzer()
    result = analyzer.analyze_problem_full_solution(
        problem_id, force=force, user_id=current_user.id,
    )

    if not result:
        return jsonify({'error': 'AI 分析失败，请检查 AI 配置或预算'}), 500

    return jsonify({
        'success': True,
        'analysis': json.loads(result.result_json) if result.result_json else None,
        'analyzed_at': result.analyzed_at.strftime('%Y-%m-%d %H:%M'),
        'ai_model': result.ai_model,
    })


@api_bp.route('/submission/<int:submission_id>/review', methods=['POST'])
@login_required
def submission_review(submission_id):
    """Trigger AI code review for a submission."""
    submission = Submission.query.get(submission_id)
    if not submission:
        return jsonify({'error': 'Not found'}), 404

    # Verify ownership: submission -> account -> student -> parent
    account = submission.platform_account
    if not account or not account.student:
        return jsonify({'error': 'Unauthorized'}), 403
    if account.student.parent_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if not submission.source_code:
        return jsonify({'error': '该提交没有源代码'}), 400

    force = request.args.get('force', '0') == '1'

    from app.analysis.ai_analyzer import AIAnalyzer
    analyzer = AIAnalyzer()
    result = analyzer.review_submission(
        submission_id, force=force, user_id=current_user.id,
    )

    if not result:
        return jsonify({'error': 'AI 分析失败，请检查 AI 配置或预算'}), 500

    return jsonify({
        'success': True,
        'analysis': json.loads(result.result_json) if result.result_json else None,
        'analyzed_at': result.analyzed_at.strftime('%Y-%m-%d %H:%M'),
        'ai_model': result.ai_model,
    })
