from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import Student, PlatformAccount, AnalysisResult
from app.scrapers import get_all_scrapers
from app.services.sync_service import SyncService

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
@login_required
def index():
    students = Student.query.filter_by(parent_id=current_user.id).all()
    available_platforms = get_all_scrapers()

    # Get AI analysis stats
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    monthly_cost = (
        db.session.query(func.sum(AnalysisResult.cost_usd))
        .filter(AnalysisResult.analyzed_at >= month_start)
        .scalar()
        or 0
    )
    monthly_budget = current_app.config.get('AI_MONTHLY_BUDGET', 5.0)

    return render_template(
        'settings/index.html',
        students=students,
        platforms=available_platforms,
        monthly_cost=round(monthly_cost, 4),
        monthly_budget=monthly_budget,
        ai_provider=current_app.config.get('AI_PROVIDER', 'unknown'),
    )


@settings_bp.route('/account/add', methods=['POST'])
@login_required
def add_account():
    student_id = request.form.get('student_id', type=int)
    platform = request.form.get('platform', '')
    platform_uid = request.form.get('platform_uid', '').strip()
    auth_cookie = request.form.get('auth_cookie', '').strip()
    auth_password = request.form.get('auth_password', '').strip()

    student = Student.query.get_or_404(student_id)
    if student.parent_id != current_user.id:
        flash('无权操作', 'danger')
        return redirect(url_for('settings.index'))

    if not platform or not platform_uid:
        flash('请填写平台和账号', 'danger')
        return redirect(url_for('settings.index'))

    # Check if already exists
    existing = PlatformAccount.query.filter_by(
        student_id=student_id, platform=platform, platform_uid=platform_uid
    ).first()
    if existing:
        flash('该平台账号已存在', 'warning')
        return redirect(url_for('settings.index'))

    account = PlatformAccount(
        student_id=student_id,
        platform=platform,
        platform_uid=platform_uid,
        auth_cookie=auth_cookie if auth_cookie else None,
        auth_password=auth_password if auth_password else None,
    )
    db.session.add(account)
    db.session.commit()
    flash(f'已添加 {platform} 平台账号', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/account/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    account = PlatformAccount.query.get_or_404(account_id)
    if account.student.parent_id != current_user.id:
        flash('无权操作', 'danger')
        return redirect(url_for('settings.index'))

    db.session.delete(account)
    db.session.commit()
    flash('平台账号已删除', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/sync/<int:account_id>', methods=['POST'])
@login_required
def sync_account(account_id):
    account = PlatformAccount.query.get_or_404(account_id)
    if account.student.parent_id != current_user.id:
        flash('无权操作', 'danger')
        return redirect(url_for('settings.index'))

    service = SyncService()
    stats = service.sync_account(account_id)

    if 'error' in stats:
        flash(f'同步失败: {stats["error"]}', 'danger')
    else:
        flash(
            f'同步完成: 新增 {stats["new_submissions"]} 条提交记录',
            'success',
        )

    return redirect(url_for('settings.index'))


@settings_bp.route('/sync-all', methods=['POST'])
@login_required
def sync_all():
    service = SyncService()
    stats = service.sync_all_accounts()
    flash(
        f'同步完成: {stats["accounts_synced"]} 个账号, '
        f'新增 {stats["total_new_submissions"]} 条提交',
        'success',
    )
    return redirect(url_for('settings.index'))
