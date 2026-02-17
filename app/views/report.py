import calendar
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
)
from markupsafe import Markup
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Student, Report
from app.analysis.report_generator import ReportGenerator

report_bp = Blueprint('report', __name__, url_prefix='/report')


@report_bp.route('/')
@login_required
def list_reports():
    student_id = request.args.get('student_id', type=int)
    report_type = request.args.get('report_type', '')
    students = Student.query.filter_by(parent_id=current_user.id).all()

    if student_id:
        current_student = Student.query.get(student_id)
    elif students:
        current_student = students[0]
    else:
        current_student = None

    if current_student:
        query = Report.query.filter_by(student_id=current_student.id)
        if report_type:
            query = query.filter_by(report_type=report_type)
        reports = query.order_by(Report.created_at.desc()).all()
    else:
        reports = []

    # Build existing reports map for dropdown markers: {student_id: {type: [period_value, ...]}}
    existing_reports_map = {}
    all_student_ids = [s.id for s in students]
    if all_student_ids:
        all_reports = Report.query.filter(
            Report.student_id.in_(all_student_ids)
        ).all()
        for r in all_reports:
            sid = str(r.student_id)
            rt = r.report_type
            if sid not in existing_reports_map:
                existing_reports_map[sid] = {}
            if rt not in existing_reports_map[sid]:
                existing_reports_map[sid][rt] = []
            if rt == 'weekly' and r.period_end:
                val = r.period_end.strftime('%Y-%m-%d')
            elif rt == 'monthly' and r.period_start:
                val = r.period_start.strftime('%Y-%m')
            elif rt == 'quarterly' and r.period_start:
                q = (r.period_start.month - 1) // 3 + 1
                val = f'{r.period_start.year}-{q}'
            else:
                continue
            existing_reports_map[sid][rt].append(val)

    return render_template(
        'report/list.html',
        reports=reports,
        students=students,
        current_student=current_student,
        selected_student_id=current_student.id if current_student else None,
        current_report_type=report_type,
        existing_reports_map=existing_reports_map,
    )


@report_bp.route('/<int:report_id>')
@login_required
def detail(report_id):
    report = Report.query.get_or_404(report_id)
    student = Student.query.get(report.student_id)
    if student.parent_id != current_user.id:
        flash('无权访问', 'danger')
        return redirect(url_for('report.list_reports'))
    return render_template(
        'report/detail.html', report=report, student=student
    )


@report_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    student_id = request.form.get('student_id', type=int)
    report_type = request.form.get('report_type', 'weekly')

    student = Student.query.get_or_404(student_id)
    if student.parent_id != current_user.id:
        if is_ajax:
            return jsonify(success=False, error='无权操作')
        flash('无权操作', 'danger')
        return redirect(url_for('report.list_reports'))

    period = request.form.get('period', '')
    start_date = None
    end_date = None

    try:
        if report_type == 'quarterly' and period:
            year, q = period.split('-')
            quarter_start_month = (int(q) - 1) * 3 + 1
            start_date = datetime(int(year), quarter_start_month, 1)
            end_month = int(q) * 3
            last_day = calendar.monthrange(int(year), end_month)[1]
            end_date = datetime(int(year), end_month, last_day, 23, 59, 59)
        elif report_type == 'monthly' and period:
            year, month = period.split('-')
            start_date = datetime(int(year), int(month), 1)
            last_day = calendar.monthrange(int(year), int(month))[1]
            end_date = datetime(int(year), int(month), last_day, 23, 59, 59)
        elif report_type == 'weekly' and period:
            end_date = datetime.strptime(period, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            )
            start_date = end_date - timedelta(days=6)
            start_date = start_date.replace(hour=0, minute=0, second=0)
    except (ValueError, TypeError):
        if is_ajax:
            return jsonify(success=False, error='周期参数无效')
        flash('周期参数无效', 'danger')
        return redirect(
            url_for('report.list_reports', student_id=student_id)
        )

    # Duplicate report detection
    if start_date and end_date:
        existing = Report.query.filter_by(
            student_id=student_id,
            report_type=report_type,
            period_start=start_date,
            period_end=end_date,
        ).first()
        if existing:
            if is_ajax:
                return jsonify(
                    success=False,
                    error=f'该时段的报告已于 {existing.created_at.strftime("%m/%d %H:%M")} 生成，如需更新请在详情页点击"重新生成"。',
                    report_id=existing.id,
                )
            flash(
                Markup(
                    f'该时段的报告已于 {existing.created_at.strftime("%m/%d %H:%M")} 生成。'
                    f'<a href="{url_for("report.detail", report_id=existing.id)}">查看报告</a>'
                    f'，如需更新请在详情页点击"重新生成"。'
                ),
                'warning',
            )
            return redirect(
                url_for('report.list_reports', student_id=student_id)
            )

    generator = ReportGenerator(
        student_id, current_app._get_current_object()
    )
    try:
        if report_type == 'quarterly':
            report = generator.generate_quarterly_report(
                end_date=end_date, start_date=start_date
            )
        elif report_type == 'monthly':
            report = generator.generate_monthly_report(
                end_date=end_date, start_date=start_date
            )
        else:
            report = generator.generate_weekly_report(
                end_date=end_date, start_date=start_date
            )

        if report:
            if is_ajax:
                return jsonify(
                    success=True,
                    report_id=report.id,
                )
            flash('报告生成成功', 'success')
            return redirect(url_for('report.detail', report_id=report.id))
        else:
            if is_ajax:
                return jsonify(success=False, error='报告生成失败')
            flash('报告生成失败', 'danger')
    except Exception as e:
        if is_ajax:
            return jsonify(success=False, error=f'报告生成出错: {str(e)}')
        flash(f'报告生成出错: {str(e)}', 'danger')

    return redirect(
        url_for('report.list_reports', student_id=student_id)
    )


@report_bp.route('/<int:report_id>/delete', methods=['POST'])
@login_required
def delete(report_id):
    report = Report.query.get_or_404(report_id)
    student = Student.query.get(report.student_id)
    if student.parent_id != current_user.id:
        flash('无权操作', 'danger')
        return redirect(url_for('report.list_reports'))

    student_id = report.student_id
    db.session.delete(report)
    db.session.commit()
    flash('报告已删除', 'success')
    return redirect(url_for('report.list_reports', student_id=student_id))


@report_bp.route('/<int:report_id>/regenerate', methods=['POST'])
@login_required
def regenerate(report_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    report = Report.query.get_or_404(report_id)
    student = Student.query.get(report.student_id)
    if student.parent_id != current_user.id:
        if is_ajax:
            return jsonify(success=False, error='无权操作')
        flash('无权操作', 'danger')
        return redirect(url_for('report.list_reports'))

    student_id = report.student_id
    report_type = report.report_type
    period_end = report.period_end

    db.session.delete(report)
    db.session.commit()

    generator = ReportGenerator(
        student_id, current_app._get_current_object()
    )
    try:
        if report_type == 'quarterly':
            new_report = generator.generate_quarterly_report(
                end_date=period_end
            )
        elif report_type == 'monthly':
            new_report = generator.generate_monthly_report(
                end_date=period_end
            )
        else:
            new_report = generator.generate_weekly_report(
                end_date=period_end
            )

        if new_report:
            if is_ajax:
                return jsonify(success=True, report_id=new_report.id)
            flash('报告已重新生成', 'success')
            return redirect(
                url_for('report.detail', report_id=new_report.id)
            )
        else:
            if is_ajax:
                return jsonify(success=False, error='报告重新生成失败')
            flash('报告重新生成失败', 'danger')
    except Exception as e:
        if is_ajax:
            return jsonify(success=False, error=f'报告重新生成出错: {str(e)}')
        flash(f'报告重新生成出错: {str(e)}', 'danger')

    return redirect(url_for('report.list_reports', student_id=student_id))
