"""Sync blueprint: content sync + AI backfill routes."""
from __future__ import annotations

import threading
import logging
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request, current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import (
    Student, PlatformAccount, Submission, Problem, AnalysisResult,
    UserSetting, SyncJob,
)
from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')


def _get_user_student_ids():
    """Return list of student IDs belonging to current user."""
    return [s.id for s in Student.query.filter_by(parent_id=current_user.id).all()]


def _get_user_account_ids():
    """Return list of platform account IDs belonging to current user."""
    student_ids = _get_user_student_ids()
    if not student_ids:
        return []
    return [
        a.id for a in PlatformAccount.query.filter(
            PlatformAccount.student_id.in_(student_ids)
        ).all()
    ]


def _check_running_job():
    """Return a running SyncJob for current user, or None."""
    return SyncJob.query.filter_by(
        user_id=current_user.id, status='running'
    ).first()


def _check_account_ownership(account_id):
    """Verify account belongs to current user. Returns (account, error_response)."""
    account = db.session.get(PlatformAccount, account_id)
    if not account or account.student.parent_id != current_user.id:
        return None, jsonify({'success': False, 'message': '无权操作'}), 403
    return account, None


def _create_sync_job(job_type, platform_account_id=None):
    """Create a SyncJob record."""
    job = SyncJob(
        user_id=current_user.id,
        job_type=job_type,
        status='pending',
        platform_account_id=platform_account_id,
    )
    db.session.add(job)
    db.session.commit()
    return job


def _start_ai_thread(job_id, user_id, platform=None, account_id=None):
    """Launch AIBackfillService in a background thread."""
    from app.services.ai_backfill_service import AIBackfillService
    app = current_app._get_current_object()
    service = AIBackfillService(app)
    t = threading.Thread(
        target=service.run,
        args=(job_id, user_id),
        kwargs={'platform': platform, 'account_id': account_id},
        daemon=True,
    )
    t.start()


@sync_bp.route('/log')
@login_required
def log_page():
    """Display sync job history."""
    jobs = (
        SyncJob.query
        .filter_by(user_id=current_user.id)
        .order_by(SyncJob.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template('sync/log.html', jobs=jobs)


@sync_bp.route('/content/<int:account_id>', methods=['POST'])
@login_required
def sync_content(account_id):
    """Sync content for a single account (synchronous)."""
    account, err = _check_account_ownership(account_id)
    if err:
        return err

    running = _check_running_job()
    if running:
        return jsonify({
            'success': False,
            'message': '已有任务在运行中',
            'job_id': running.id,
        })

    job = _create_sync_job('content_sync', platform_account_id=account_id)
    job.status = 'running'
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        service = SyncService()
        stats = service.sync_account(account_id)

        if 'error' in stats:
            job.status = 'failed'
            job.error_message = stats['error']
        else:
            job.status = 'completed'
            job.stats = stats

        job.finished_at = datetime.utcnow()
        db.session.commit()

        if 'error' in stats:
            return jsonify({
                'success': False,
                'message': f'同步失败: {stats["error"]}',
                'stats': stats,
            })

        return jsonify({
            'success': True,
            'message': f'同步完成: 新增 {stats["new_submissions"]} 条提交, {stats["new_problems"]} 道题目',
            'stats': stats,
            'job_id': job.id,
        })

    except Exception as e:
        job.status = 'failed'
        job.error_message = str(e)
        job.finished_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': False, 'message': f'同步失败: {e}'})


@sync_bp.route('/content-all', methods=['POST'])
@login_required
def sync_content_all():
    """Sync content for all active accounts (synchronous)."""
    running = _check_running_job()
    if running:
        return jsonify({
            'success': False,
            'message': '已有任务在运行中',
            'job_id': running.id,
        })

    job = _create_sync_job('content_sync')
    job.status = 'running'
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        service = SyncService()
        stats = service.sync_all_accounts(user_id=current_user.id)

        job.status = 'completed'
        job.stats = stats
        job.finished_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': (
                f'同步完成: {stats["accounts_synced"]} 个账号, '
                f'新增 {stats["total_new_submissions"]} 条提交, '
                f'{stats["total_new_problems"]} 道题目'
            ),
            'stats': stats,
            'job_id': job.id,
        })

    except Exception as e:
        job.status = 'failed'
        job.error_message = str(e)
        job.finished_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': False, 'message': f'同步失败: {e}'})


@sync_bp.route('/content-and-ai/<int:account_id>', methods=['POST'])
@login_required
def sync_content_and_ai(account_id):
    """Sync content then start AI backfill in background."""
    account, err = _check_account_ownership(account_id)
    if err:
        return err

    running = _check_running_job()
    if running:
        return jsonify({
            'success': False,
            'message': '已有任务在运行中',
            'job_id': running.id,
        })

    # Phase 1: synchronous content sync
    sync_job = _create_sync_job('content_sync', platform_account_id=account_id)
    sync_job.status = 'running'
    sync_job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        service = SyncService()
        stats = service.sync_account(account_id)

        if 'error' in stats:
            sync_job.status = 'failed'
            sync_job.error_message = stats['error']
            sync_job.finished_at = datetime.utcnow()
            db.session.commit()
            return jsonify({
                'success': False,
                'message': f'同步失败: {stats["error"]}',
                'stats': stats,
            })

        sync_job.status = 'completed'
        sync_job.stats = stats
        sync_job.finished_at = datetime.utcnow()
        db.session.commit()

    except Exception as e:
        sync_job.status = 'failed'
        sync_job.error_message = str(e)
        sync_job.finished_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': False, 'message': f'同步失败: {e}'})

    # Phase 2: background AI backfill
    ai_job = _create_sync_job('ai_backfill', platform_account_id=account_id)
    _start_ai_thread(
        ai_job.id, current_user.id,
        platform=account.platform, account_id=account_id,
    )

    return jsonify({
        'success': True,
        'message': (
            f'同步完成: 新增 {stats["new_submissions"]} 条提交, '
            f'{stats["new_problems"]} 道题目。AI 分析已在后台启动。'
        ),
        'stats': stats,
        'ai_job_id': ai_job.id,
    })


@sync_bp.route('/ai-backfill', methods=['POST'])
@login_required
def start_ai_backfill():
    """Start AI backfill as a background task."""
    running = _check_running_job()
    if running:
        return jsonify({
            'success': False,
            'message': '已有任务在运行中',
            'job_id': running.id,
        })

    account_id = request.json.get('account_id') if request.is_json else None
    platform = None

    if account_id:
        account, err = _check_account_ownership(int(account_id))
        if err:
            return err
        platform = account.platform

    job = _create_sync_job('ai_backfill',
                           platform_account_id=account_id)
    _start_ai_thread(
        job.id, current_user.id,
        platform=platform, account_id=account_id,
    )

    return jsonify({
        'success': True,
        'message': 'AI 分析已在后台启动',
        'job_id': job.id,
    })


@sync_bp.route('/job/<int:job_id>/status')
@login_required
def job_status(job_id):
    """Poll job progress (JSON)."""
    job = db.session.get(SyncJob, job_id)
    if not job or job.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404

    phase_labels = {
        'classify': '分类',
        'solution': '思路分析',
        'full_solution': 'AI 解题',
        'review': '代码审查',
    }

    return jsonify({
        'id': job.id,
        'job_type': job.job_type,
        'status': job.status,
        'current_phase': job.current_phase,
        'phase_label': phase_labels.get(job.current_phase, job.current_phase),
        'progress_current': job.progress_current,
        'progress_total': job.progress_total,
        'stats': job.stats,
        'error_message': job.error_message,
        'duration_seconds': job.duration_seconds,
    })


@sync_bp.route('/running-job')
@login_required
def running_job():
    """Check if current user has a running job."""
    job = _check_running_job()
    if not job:
        return jsonify({'running': False})

    phase_labels = {
        'classify': '分类',
        'solution': '思路分析',
        'full_solution': 'AI 解题',
        'review': '代码审查',
    }

    return jsonify({
        'running': True,
        'job_id': job.id,
        'job_type': job.job_type,
        'current_phase': job.current_phase,
        'phase_label': phase_labels.get(job.current_phase, job.current_phase),
        'progress_current': job.progress_current,
        'progress_total': job.progress_total,
    })


@sync_bp.route('/ai-cost-info')
@login_required
def ai_cost_info():
    """Return monthly AI cost info for confirmation dialog."""
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    monthly_cost = (
        db.session.query(func.sum(AnalysisResult.cost_usd))
        .filter(AnalysisResult.analyzed_at >= month_start)
        .scalar() or 0
    )

    monthly_budget = current_app.config.get('AI_MONTHLY_BUDGET', 5.0)
    user_budget = UserSetting.get(current_user.id, 'ai_monthly_budget')
    if user_budget:
        monthly_budget = float(user_budget)

    # Count pending items
    unclassified = Problem.query.filter(
        db.or_(Problem.ai_analyzed == False, Problem.difficulty == 0)  # noqa: E712
    ).count()

    no_solution = Problem.query.filter(
        Problem.description.isnot(None),
        ~Problem.id.in_(
            db.session.query(AnalysisResult.problem_id_ref)
            .filter_by(analysis_type="problem_solution")
        ),
    ).count()

    no_full_solution = Problem.query.filter(
        Problem.description.isnot(None),
        ~Problem.id.in_(
            db.session.query(AnalysisResult.problem_id_ref)
            .filter_by(analysis_type="problem_full_solution")
        ),
    ).count()

    reviewed_ids = (
        db.session.query(AnalysisResult.submission_id)
        .filter_by(analysis_type="submission_review")
    )
    no_review = Submission.query.filter(
        Submission.source_code.isnot(None),
        Submission.source_code != '',
        ~Submission.id.in_(reviewed_ids),
    ).count()

    return jsonify({
        'monthly_cost': round(monthly_cost, 4),
        'monthly_budget': monthly_budget,
        'pending': {
            'classify': unclassified,
            'solution': no_solution,
            'full_solution': no_full_solution,
            'review': no_review,
        },
    })
