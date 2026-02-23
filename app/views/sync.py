"""Sync blueprint: content sync + AI backfill routes."""
from __future__ import annotations

import json
import threading
import logging
from datetime import datetime, timedelta

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

# Registry of active AIBackfillService instances, keyed by job_id.
# Used by cancel_job() to signal the background thread via _cancel_event.
_active_ai_services = {}
_active_ai_services_lock = threading.Lock()


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
    """Return a pending/running SyncJob for current user, or None.

    Checks both 'pending' and 'running' statuses to prevent duplicate
    jobs created during the window between job creation and thread start.
    Stale jobs are automatically marked as failed.
    """
    job = SyncJob.query.filter(
        SyncJob.user_id == current_user.id,
        SyncJob.status.in_(['pending', 'running']),
    ).first()
    if not job:
        return None
    # Running job stuck > 2 hours
    if job.status == 'running' and job.started_at:
        cutoff = datetime.utcnow() - timedelta(hours=2)
        if job.started_at < cutoff:
            job.status = 'failed'
            job.error_message = '任务超时，已自动标记为失败（进程可能被终止）'
            job.finished_at = datetime.utcnow()
            db.session.commit()
            logger.warning(f'Marked stale SyncJob {job.id} as failed')
            return None
    # Pending job stuck > 10 minutes (thread never started)
    if job.status == 'pending' and job.created_at:
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        if job.created_at < cutoff:
            job.status = 'failed'
            job.error_message = '任务启动超时，已自动标记为失败'
            job.finished_at = datetime.utcnow()
            db.session.commit()
            logger.warning(f'Marked stale pending SyncJob {job.id} as failed')
            return None
    return job


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

    with _active_ai_services_lock:
        _active_ai_services[job_id] = service

    def _run_and_cleanup():
        try:
            service.run(job_id, user_id, platform=platform, account_id=account_id)
        finally:
            with _active_ai_services_lock:
                _active_ai_services.pop(job_id, None)

    t = threading.Thread(target=_run_and_cleanup, daemon=True)
    t.start()


def _start_content_sync_thread(job_id, user_id):
    """Run content sync for all active accounts in a background thread."""
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            job = db.session.get(SyncJob, job_id)
            if not job:
                return

            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()

            try:
                # Get active accounts for this user
                student_ids = [
                    s.id for s in Student.query.filter_by(parent_id=user_id).all()
                ]
                accounts = []
                if student_ids:
                    accounts = PlatformAccount.query.filter(
                        PlatformAccount.student_id.in_(student_ids),
                        PlatformAccount.is_active == True,  # noqa: E712
                    ).all()

                if not accounts:
                    job.status = 'completed'
                    job.stats = {
                        'accounts_synced': 0,
                        'total_new_submissions': 0,
                        'total_new_problems': 0,
                    }
                    job.finished_at = datetime.utcnow()
                    db.session.commit()
                    return

                job.progress_total = len(accounts)
                job.progress_current = 0
                db.session.commit()

                service = SyncService()
                total_subs = 0
                total_probs = 0
                synced = 0
                errors = []
                account_details = []

                for i, account in enumerate(accounts):
                    job.current_phase = account.platform
                    job.progress_current = i
                    db.session.commit()

                    detail = {
                        'platform': account.platform,
                        'platform_uid': account.platform_uid,
                        'student_name': account.student.name,
                    }

                    try:
                        stats = service.sync_account(account.id)
                        if 'error' not in stats:
                            synced += 1
                            total_subs += stats.get('new_submissions', 0)
                            total_probs += stats.get('new_problems', 0)
                            detail.update(
                                status='ok',
                                new_submissions=stats.get('new_submissions', 0),
                                new_problems=stats.get('new_problems', 0),
                            )
                        else:
                            errors.append(f'{account.platform}: {stats["error"]}')
                            detail.update(status='error', error=stats['error'])
                    except Exception as e:
                        logger.error(
                            f'Content sync failed for account {account.id}: {e}'
                        )
                        errors.append(f'{account.platform}: {e}')
                        detail.update(status='error', error=str(e))

                    account_details.append(detail)

                job.progress_current = len(accounts)
                job.current_phase = None
                job.status = 'completed'
                job.stats = {
                    'accounts_synced': synced,
                    'total_new_submissions': total_subs,
                    'total_new_problems': total_probs,
                    'errors': errors,
                    'account_details': account_details,
                }
                job.finished_at = datetime.utcnow()
                db.session.commit()

            except Exception as e:
                logger.error(f'Content sync all thread failed: {e}')
                job.status = 'failed'
                job.error_message = str(e)
                job.finished_at = datetime.utcnow()
                db.session.commit()

    t = threading.Thread(target=_run, daemon=True)
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
            # Enrich stats with platform/account info for detail view
            stats['account_details'] = [{
                'platform': account.platform,
                'platform_uid': account.platform_uid,
                'student_name': account.student.name,
                'status': 'ok',
                'new_submissions': stats.get('new_submissions', 0),
                'new_problems': stats.get('new_problems', 0),
            }]
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
    """Sync content for all active accounts (async background thread)."""
    running = _check_running_job()
    if running:
        return jsonify({
            'success': False,
            'message': '已有任务在运行中',
            'job_id': running.id,
        })

    job = _create_sync_job('content_sync')
    _start_content_sync_thread(job.id, current_user.id)

    return jsonify({
        'success': True,
        'message': '同步已启动',
        'job_id': job.id,
    })


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


@sync_bp.route('/job/<int:job_id>/cancel', methods=['POST'])
@login_required
def cancel_job(job_id):
    """Cancel a pending or running job."""
    job = db.session.get(SyncJob, job_id)
    if not job or job.user_id != current_user.id:
        return jsonify({'success': False, 'message': '未找到任务'}), 404
    if job.status not in ('pending', 'running'):
        return jsonify({'success': False, 'message': '任务已结束，无法取消'})
    # Signal the background thread to stop (if still running)
    with _active_ai_services_lock:
        service = _active_ai_services.get(job_id)
        if service:
            service.request_cancel()

    job.status = 'failed'
    job.error_message = '用户手动取消'
    job.finished_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': '任务已取消'})


@sync_bp.route('/job/<int:job_id>/status')
@login_required
def job_status(job_id):
    """Poll job progress (JSON)."""
    job = db.session.get(SyncJob, job_id)
    if not job or job.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404

    phase_labels = {
        'comprehensive': 'AI 综合分析',
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


@sync_bp.route('/job/<int:job_id>/detail')
@login_required
def job_detail(job_id):
    """Return detailed breakdown of a sync job."""
    job = db.session.get(SyncJob, job_id)
    if not job or job.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404

    result = {'job_type': job.job_type, 'status': job.status}

    if job.job_type == 'content_sync':
        stats = job.stats or {}
        result['account_details'] = stats.get('account_details', [])
        result['errors'] = stats.get('errors', [])
    elif job.job_type == 'ai_backfill':
        # Query AnalysisResult records created during this job's time window
        comprehensive = []
        reviews = []
        total_cost = 0.0

        if job.started_at:
            end_time = job.finished_at or datetime.utcnow()
            query = (
                AnalysisResult.query
                .filter(
                    AnalysisResult.analyzed_at >= job.started_at,
                    AnalysisResult.analyzed_at <= end_time,
                )
                .order_by(AnalysisResult.analyzed_at.desc())
                .limit(100)
                .all()
            )

            for ar in query:
                cost = float(ar.cost_usd or 0)
                total_cost += cost
                item = {
                    'analysis_type': ar.analysis_type,
                    'model': ar.ai_model,
                    'cost': round(cost, 6),
                    'analyzed_at': ar.analyzed_at.isoformat() if ar.analyzed_at else None,
                }
                if ar.problem:
                    item['problem_name'] = ar.problem.title or ar.problem.problem_id
                    item['platform'] = ar.problem.platform
                    item['problem_id'] = ar.problem.problem_id
                if ar.submission:
                    item['submission_status'] = ar.submission.status
                if ar.analysis_type == 'submission_review':
                    reviews.append(item)
                else:
                    comprehensive.append(item)

        result['comprehensive'] = comprehensive
        result['reviews'] = reviews
        result['total_cost'] = round(total_cost, 6)

    if job.error_message:
        result['error_message'] = job.error_message

    return jsonify(result)


@sync_bp.route('/running-job')
@login_required
def running_job():
    """Check if current user has a running job."""
    job = _check_running_job()
    if not job:
        return jsonify({'running': False})

    phase_labels = {
        'comprehensive': 'AI 综合分析',
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


@sync_bp.route('/check-new')
@login_required
def check_new():
    """Check if there are new submissions to sync.

    Uses a user-level lock (via UserSetting) so concurrent requests from
    multiple tabs/devices don't all fire network requests.  Results are
    cached for 30 minutes.
    """
    from app.scrapers import get_scraper_class, get_scraper_instance

    user_id = current_user.id
    now = datetime.utcnow()

    # ── Check lock ──
    lock_val = UserSetting.get(user_id, 'check_new_lock')
    if lock_val:
        try:
            lock_time = datetime.fromisoformat(lock_val)
            if (now - lock_time).total_seconds() < 60:
                # Another request is running — return cached result if any
                cached = _get_check_new_cache(user_id, now)
                if cached is not None:
                    return jsonify({'accounts_with_new': cached, 'locked': True})
                return jsonify({'accounts_with_new': [], 'locked': True})
        except (ValueError, TypeError):
            pass

    # ── Check cache (valid for 30 minutes) ──
    cached = _get_check_new_cache(user_id, now)
    if cached is not None:
        return jsonify({'accounts_with_new': cached, 'cached': True})

    # ── Set lock ──
    UserSetting.set(user_id, 'check_new_lock', now.isoformat())
    db.session.commit()

    try:
        # Get active accounts
        student_ids = [s.id for s in Student.query.filter_by(parent_id=user_id).all()]
        accounts = []
        if student_ids:
            accounts = PlatformAccount.query.filter(
                PlatformAccount.student_id.in_(student_ids),
                PlatformAccount.is_active == True,  # noqa: E712
            ).all()

        accounts_with_new = []
        for account in accounts:
            scraper_cls = get_scraper_class(account.platform)
            if not scraper_cls:
                continue

            if scraper_cls.REQUIRES_LOGIN:
                # Time-based check: flag if last sync > 24h ago
                if account.last_sync_at and (now - account.last_sync_at).total_seconds() > 86400:
                    accounts_with_new.append({
                        'account_id': account.id,
                        'platform': account.platform,
                        'platform_uid': account.platform_uid,
                        'student_name': account.student.name,
                        'check_method': 'time_based',
                    })
                elif not account.last_sync_at:
                    accounts_with_new.append({
                        'account_id': account.id,
                        'platform': account.platform,
                        'platform_uid': account.platform_uid,
                        'student_name': account.student.name,
                        'check_method': 'time_based',
                    })
                continue

            # For non-login platforms: try fetching one submission
            try:
                scraper = get_scraper_instance(
                    account.platform,
                    auth_cookie=account.auth_cookie,
                )
                gen = scraper.fetch_submissions(
                    platform_uid=account.platform_uid,
                    since=account.last_sync_at,
                    cursor=account.sync_cursor,
                )
                first = next(gen, None)
                if first is not None:
                    accounts_with_new.append({
                        'account_id': account.id,
                        'platform': account.platform,
                        'platform_uid': account.platform_uid,
                        'student_name': account.student.name,
                        'check_method': 'api_check',
                    })
            except Exception as e:
                logger.debug(f'check-new: error checking {account.platform}:{account.platform_uid}: {e}')

        # ── Write cache, clear lock ──
        UserSetting.set(user_id, 'check_new_result', json.dumps(accounts_with_new))
        UserSetting.set(user_id, 'check_new_result_at', now.isoformat())
        UserSetting.set(user_id, 'check_new_lock', '')
        db.session.commit()

        return jsonify({'accounts_with_new': accounts_with_new})

    except Exception as e:
        logger.error(f'check-new failed for user {user_id}: {e}')
        UserSetting.set(user_id, 'check_new_lock', '')
        db.session.commit()
        return jsonify({'accounts_with_new': [], 'error': str(e)})


def _get_check_new_cache(user_id, now):
    """Return cached check-new result if still valid (< 30 min), else None."""
    result_at = UserSetting.get(user_id, 'check_new_result_at')
    if not result_at:
        return None
    try:
        cache_time = datetime.fromisoformat(result_at)
        if (now - cache_time).total_seconds() < 1800:
            raw = UserSetting.get(user_id, 'check_new_result')
            if raw:
                return json.loads(raw)
    except (ValueError, TypeError):
        pass
    return None


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

    # Scope counts to current user's accounts
    account_ids = _get_user_account_ids()

    # Problem IDs linked to user's submissions
    user_problem_ids = (
        db.session.query(Submission.problem_id_ref)
        .filter(
            Submission.platform_account_id.in_(account_ids),
            Submission.problem_id_ref.isnot(None),
        )
    ) if account_ids else db.session.query(Problem.id).filter(db.literal(False))

    # Count pending items — comprehensive = problems missing any of the 3 types
    classified_ids = (
        db.session.query(AnalysisResult.problem_id_ref)
        .filter_by(analysis_type="problem_classify")
    )
    has_solution_ids = (
        db.session.query(AnalysisResult.problem_id_ref)
        .filter_by(analysis_type="problem_solution")
    )
    has_full_ids = (
        db.session.query(AnalysisResult.problem_id_ref)
        .filter_by(analysis_type="problem_full_solution")
    )

    comprehensive_pending = Problem.query.filter(
        Problem.id.in_(user_problem_ids),
        Problem.description.isnot(None),
        db.or_(
            Problem.ai_analyzed == False,  # noqa: E712
            Problem.difficulty == 0,
            ~Problem.id.in_(classified_ids),
            ~Problem.id.in_(has_solution_ids),
            ~Problem.id.in_(has_full_ids),
        ),
    ).count()

    # Review count: align with AIBackfillService._run_phase_review filters
    reviewed_ids = (
        db.session.query(AnalysisResult.submission_id)
        .filter_by(analysis_type="submission_review")
    )

    # Count existing reviews per (problem, account) for the 3-per-group cap
    reviewed_counts = {
        (pid, aid): cnt
        for pid, aid, cnt in db.session.query(
            Submission.problem_id_ref,
            Submission.platform_account_id,
            func.count(AnalysisResult.id),
        )
        .join(AnalysisResult, AnalysisResult.submission_id == Submission.id)
        .filter(AnalysisResult.analysis_type == "submission_review")
        .group_by(Submission.problem_id_ref, Submission.platform_account_id)
        .all()
    }

    # Count unreviewed submissions per (problem, account) with proper filters
    unreviewed_groups = (
        db.session.query(
            Submission.problem_id_ref,
            Submission.platform_account_id,
            func.count(Submission.id),
        )
        .join(
            PlatformAccount,
            Submission.platform_account_id == PlatformAccount.id,
        )
        .filter(
            PlatformAccount.is_active == True,  # noqa: E712
            Submission.problem_id_ref.isnot(None),
            Submission.source_code.isnot(None),
            Submission.source_code != '',
            ~Submission.id.in_(reviewed_ids),
            Submission.platform_account_id.in_(account_ids) if account_ids else db.literal(False),
        )
        .group_by(Submission.problem_id_ref, Submission.platform_account_id)
        .all()
    )

    # Apply per-(problem, account) cap: at most 3 reviews total
    no_review = 0
    for pid, aid, cnt in unreviewed_groups:
        existing = reviewed_counts.get((pid, aid), 0)
        if existing >= 3:
            continue
        no_review += min(cnt, 3 - existing)

    return jsonify({
        'monthly_cost': round(monthly_cost, 4),
        'monthly_budget': monthly_budget,
        'pending': {
            'comprehensive': comprehensive_pending,
            'review': no_review,
        },
    })
