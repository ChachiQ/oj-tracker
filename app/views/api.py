import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, Response, stream_with_context, current_app
from flask_login import login_required, current_user
from app.models import Student, Problem, Submission, PlatformAccount, Tag, AnalysisResult
from app.services.stats_service import StatsService
from app.analysis.engine import AnalysisEngine

logger = logging.getLogger(__name__)

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
                current_app.to_display_tz(sub.submitted_at).strftime('%Y-%m-%d %H:%M:%S')
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
        latest_report_time = current_app.to_display_tz(
            latest_log.created_at
        ).strftime('%Y-%m-%d %H:%M')
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


def _safe_parse_result(result, comprehensive_done=False):
    """Safely parse analysis result into API response dict."""
    analysis = None
    if result.result_json:
        try:
            analysis = json.loads(result.result_json)
        except (json.JSONDecodeError, TypeError):
            analysis = {'raw': result.result_json}
    analyzed_at_str = None
    if result.analyzed_at and isinstance(result.analyzed_at, datetime):
        display_dt = current_app.to_display_tz(result.analyzed_at)
        analyzed_at_str = display_dt.strftime('%Y-%m-%d %H:%M')
    resp = {
        'success': True,
        'analysis': analysis,
        'analyzed_at': analyzed_at_str,
        'ai_model': result.ai_model,
    }
    if comprehensive_done:
        resp['comprehensive_done'] = True
    return resp


@api_bp.route('/problem/<int:problem_id>/classify', methods=['POST'])
@login_required
def problem_classify(problem_id):
    """Trigger AI classification for a problem and return interaction details."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    from app.extensions import db
    from app.analysis.problem_classifier import ProblemClassifier
    from app.analysis.prompts.problem_classify import build_classify_prompt

    # Build prompt (for display in interaction log)
    platform_tags = None
    if problem.platform_tags:
        try:
            platform_tags = json.loads(problem.platform_tags)
        except (json.JSONDecodeError, TypeError):
            pass

    prompt_messages = build_classify_prompt(
        title=problem.title or problem.problem_id,
        platform=problem.platform,
        difficulty_raw=problem.difficulty_raw,
        description=problem.description,
        input_desc=problem.input_desc,
        output_desc=problem.output_desc,
        examples=problem.examples,
        hint=problem.hint,
        platform_tags=platform_tags,
    )

    # Reset skip flags so manual retry works
    problem.ai_skip_backfill = False
    problem.ai_retry_count = 0
    problem.ai_analysis_error = None
    db.session.commit()

    # Execute classification with force=True
    classifier = ProblemClassifier(app=current_app._get_current_object())
    success = classifier.classify_problem(problem_id, user_id=current_user.id, force=True)

    # Read back results
    db.session.refresh(problem)
    ar = AnalysisResult.query.filter_by(
        problem_id_ref=problem_id, analysis_type="problem_classify",
    ).first()

    # Parse knowledge_points
    ai_tags = []
    if problem.ai_tags:
        try:
            ai_tags = json.loads(problem.ai_tags)
        except (json.JSONDecodeError, TypeError):
            pass

    analyzed_at_str = ''
    if ar and ar.analyzed_at:
        display_dt = current_app.to_display_tz(ar.analyzed_at)
        analyzed_at_str = display_dt.strftime('%Y-%m-%d %H:%M')

    return jsonify({
        'success': success,
        'difficulty': problem.difficulty,
        'problem_type': problem.ai_problem_type or '',
        'knowledge_points': ai_tags,
        'prompt': prompt_messages[0]['content'] if prompt_messages else '',
        'raw_response': ar.result_json if ar else '',
        'ai_model': ar.ai_model if ar else '',
        'analyzed_at': analyzed_at_str,
        'cost_usd': round(ar.cost_usd, 6) if ar and ar.cost_usd else 0,
        'token_cost': ar.token_cost if ar else 0,
        'error': problem.ai_analysis_error or '',
    })


@api_bp.route('/problem/<int:problem_id>/comprehensive', methods=['POST'])
@login_required
def problem_comprehensive(problem_id):
    """Trigger comprehensive AI analysis: classify + solution + full solution."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    from app.analysis.ai_analyzer import AIAnalyzer
    from app.extensions import db

    # Reset skip flags so manual retry works
    problem.ai_skip_backfill = False
    problem.ai_retry_count = 0
    problem.ai_analysis_error = None
    db.session.commit()

    analyzer = AIAnalyzer()
    results = analyzer.analyze_problem_comprehensive(
        problem_id, force=True, user_id=current_user.id,
    )

    if not results:
        return jsonify({'success': False, 'error': 'AI 分析失败，请检查 AI 配置或预算'})

    db.session.refresh(problem)

    ai_tags = []
    if problem.ai_tags:
        try:
            ai_tags = json.loads(problem.ai_tags)
        except (json.JSONDecodeError, TypeError):
            pass

    response = {
        'success': True,
        'classify': {
            'difficulty': problem.difficulty,
            'problem_type': problem.ai_problem_type or '',
            'knowledge_points': ai_tags,
        },
    }
    if 'solution' in results:
        response['solution'] = _safe_parse_result(results['solution'])
    if 'full_solution' in results:
        response['full_solution'] = _safe_parse_result(results['full_solution'])

    return jsonify(response)


@api_bp.route('/problem/<int:problem_id>/solution', methods=['POST'])
@login_required
def problem_solution(problem_id):
    """Trigger AI solution approach analysis for a problem."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    force = request.args.get('force', '0') == '1'

    # Check for existing result first
    if not force:
        existing = AnalysisResult.query.filter_by(
            problem_id_ref=problem_id, analysis_type="problem_solution",
        ).first()
        if existing and existing.result_json:
            try:
                json.loads(existing.result_json)
                return jsonify(_safe_parse_result(existing))
            except (json.JSONDecodeError, TypeError):
                pass

    # Use comprehensive method — generates all 3 types at once
    from app.analysis.ai_analyzer import AIAnalyzer
    analyzer = AIAnalyzer()
    results = analyzer.analyze_problem_comprehensive(
        problem_id, force=force, user_id=current_user.id,
    )

    if not results or 'solution' not in results:
        return jsonify({'error': 'AI 分析失败，请检查 AI 配置或预算'}), 500

    return jsonify(_safe_parse_result(results['solution'], comprehensive_done=True))


@api_bp.route('/problem/<int:problem_id>/full-solution', methods=['POST'])
@login_required
def problem_full_solution(problem_id):
    """Trigger AI full solution generation for a problem."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    force = request.args.get('force', '0') == '1'

    # Check for existing result first
    if not force:
        existing = AnalysisResult.query.filter_by(
            problem_id_ref=problem_id, analysis_type="problem_full_solution",
        ).first()
        if existing and existing.result_json:
            try:
                json.loads(existing.result_json)
                return jsonify(_safe_parse_result(existing))
            except (json.JSONDecodeError, TypeError):
                pass

    # Use comprehensive method — generates all 3 types at once
    from app.analysis.ai_analyzer import AIAnalyzer
    analyzer = AIAnalyzer()
    results = analyzer.analyze_problem_comprehensive(
        problem_id, force=force, user_id=current_user.id,
    )

    if not results or 'full_solution' not in results:
        return jsonify({'error': 'AI 分析失败，请检查 AI 配置或预算'}), 500

    return jsonify(_safe_parse_result(results['full_solution'], comprehensive_done=True))


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

    return jsonify(_safe_parse_result(result))


@api_bp.route('/problem/<int:problem_id>/resync', methods=['POST'])
@login_required
def problem_resync(problem_id):
    """Re-fetch problem content from the OJ platform."""
    problem = _user_owns_problem(problem_id)
    if not problem:
        return jsonify({'error': 'Unauthorized'}), 403

    from app.scrapers import get_scraper_instance
    from app.services.tag_mapper import TagMapper
    from app.extensions import db

    # Build scraper kwargs — find credentials from user's accounts on same platform
    scraper_kwargs = {}
    students = Student.query.filter_by(parent_id=current_user.id).all()
    for s in students:
        for acct in s.platform_accounts:
            if acct.platform == problem.platform:
                if acct.auth_cookie:
                    scraper_kwargs['auth_cookie'] = acct.auth_cookie
                if acct.auth_password:
                    scraper_kwargs['auth_password'] = acct.auth_password
                break
        if scraper_kwargs:
            break

    try:
        scraper = get_scraper_instance(problem.platform, **scraper_kwargs)
    except ValueError:
        return jsonify({'success': False, 'error': f'不支持的平台: {problem.platform}'}), 400

    try:
        scraped = scraper.fetch_problem(problem.problem_id)
    except Exception as e:
        logger.error(f"Resync fetch failed for {problem.platform}:{problem.problem_id}: {e}")
        return jsonify({'success': False, 'error': f'抓取失败: {e}'}), 500

    if not scraped:
        return jsonify({'success': False, 'error': '平台未返回题目数据'}), 404

    # Force-overwrite all content fields
    try:
        problem.title = scraped.title or problem.title
        problem.description = scraped.description
        problem.input_desc = scraped.input_desc
        problem.output_desc = scraped.output_desc
        problem.examples = scraped.examples
        problem.hint = scraped.hint
        problem.url = scraped.url or scraper.get_problem_url(problem.problem_id)
        problem.source = scraped.source
        problem.difficulty_raw = scraped.difficulty_raw
        if scraped.difficulty_raw:
            problem.difficulty = scraper.map_difficulty(scraped.difficulty_raw)
        if scraped.tags:
            problem.platform_tags = json.dumps(scraped.tags, ensure_ascii=False)
            mapper = TagMapper(problem.platform)
            mapped = mapper.map_tags(scraped.tags)
            for tag in mapped:
                if tag not in problem.tags:
                    problem.tags.append(tag)
        problem.last_scanned_at = datetime.utcnow()
        db.session.commit()
        logger.info(
            f"Resync OK for {problem.platform}:{problem.problem_id} — "
            f"title={scraped.title!r}, tags={scraped.tags}"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Resync update failed for {problem.platform}:{problem.problem_id}: {e}")
        return jsonify({'success': False, 'error': f'更新题目数据失败: {e}'}), 500

    return jsonify({'success': True, 'message': '题目内容已更新'})
