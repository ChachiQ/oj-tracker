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
from app.models import (
    Student,
    PlatformAccount,
    AnalysisResult,
    Submission,
    UserSetting,
)
from app.scrapers import get_all_scrapers
from app.services.sync_service import SyncService
from app.analysis.llm.config import MODEL_CONFIG

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
@login_required
def index():
    students = Student.query.filter_by(parent_id=current_user.id).all()
    student_ids = [s.id for s in students]

    # ── Platform info (dynamic from scraper registry) ──
    scrapers = get_all_scrapers()
    platform_info = []
    for name, cls in scrapers.items():
        platform_info.append({
            'name': name,
            'display': getattr(cls, 'PLATFORM_DISPLAY', name),
            'instructions': cls().get_auth_instructions(),
            'requires_login': getattr(cls, 'REQUIRES_LOGIN', False),
        })

    requires_login_platforms = [
        name for name, cls in scrapers.items()
        if getattr(cls, 'REQUIRES_LOGIN', False)
    ]

    # ── Accounts for the user's students ──
    accounts = (
        PlatformAccount.query.filter(
            PlatformAccount.student_id.in_(student_ids)
        ).all()
        if student_ids
        else []
    )

    # ── AI analysis stats ──
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

    # Analyzed count
    analyzed_count = (
        AnalysisResult.query.join(Submission)
        .join(PlatformAccount)
        .filter(PlatformAccount.student_id.in_(student_ids))
        .count()
        if student_ids
        else 0
    )

    # Usage by model this month
    usage_by_model = (
        db.session.query(
            AnalysisResult.ai_model,
            func.count(AnalysisResult.id),
            func.sum(AnalysisResult.token_cost),
            func.sum(AnalysisResult.cost_usd),
        )
        .filter(AnalysisResult.analyzed_at >= month_start)
        .group_by(AnalysisResult.ai_model)
        .all()
    )

    # ── User AI configuration ──
    user_ai_provider = (
        UserSetting.get(current_user.id, 'ai_provider')
        or current_app.config.get('AI_PROVIDER', 'zhipu')
    )
    user_has_key = {}
    for p in ['claude', 'openai', 'zhipu']:
        key = UserSetting.get(current_user.id, f'api_key_{p}')
        user_has_key[p] = bool(key)

    user_monthly_budget = UserSetting.get(
        current_user.id, 'ai_monthly_budget'
    )

    return render_template(
        'settings/index.html',
        students=students,
        platforms=scrapers,
        platform_info=platform_info,
        requires_login_platforms=requires_login_platforms,
        accounts=accounts,
        monthly_cost=round(monthly_cost, 4),
        monthly_budget=monthly_budget,
        analyzed_count=analyzed_count,
        usage_by_model=usage_by_model,
        ai_provider=user_ai_provider,
        user_ai_provider=user_ai_provider,
        user_has_key=user_has_key,
        user_monthly_budget=user_monthly_budget,
        model_config=MODEL_CONFIG,
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


@settings_bp.route('/ai', methods=['POST'])
@login_required
def save_ai_config():
    """Save user-level AI provider configuration."""
    provider = request.form.get('ai_provider', '')
    if provider not in ('claude', 'openai', 'zhipu'):
        flash('无效的 AI 提供者', 'danger')
        return redirect(url_for('settings.index'))

    UserSetting.set(current_user.id, 'ai_provider', provider)

    # Only overwrite a key when the user submits a non-empty value
    for p in ['claude', 'openai', 'zhipu']:
        key_val = request.form.get(f'api_key_{p}', '').strip()
        if key_val:
            UserSetting.set(current_user.id, f'api_key_{p}', key_val)

    budget = request.form.get('ai_monthly_budget', '').strip()
    if budget:
        UserSetting.set(current_user.id, 'ai_monthly_budget', budget)

    db.session.commit()
    flash('AI 配置已保存', 'success')
    return redirect(url_for('settings.index'))
