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

    return render_template(
        'report/list.html',
        reports=reports,
        students=students,
        current_student=current_student,
        selected_student_id=current_student.id if current_student else None,
        current_report_type=report_type,
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
    student_id = request.form.get('student_id', type=int)
    report_type = request.form.get('report_type', 'weekly')

    student = Student.query.get_or_404(student_id)
    if student.parent_id != current_user.id:
        flash('无权操作', 'danger')
        return redirect(url_for('report.list_reports'))

    end_date_str = request.form.get('end_date', '')
    end_date = (
        datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None
    )

    generator = ReportGenerator(
        student_id, current_app._get_current_object()
    )
    try:
        if report_type == 'quarterly':
            report = generator.generate_quarterly_report(end_date=end_date)
        elif report_type == 'monthly':
            report = generator.generate_monthly_report(end_date=end_date)
        else:
            report = generator.generate_weekly_report(end_date=end_date)

        if report:
            flash('报告生成成功', 'success')
            return redirect(url_for('report.detail', report_id=report.id))
        else:
            flash('报告生成失败', 'danger')
    except Exception as e:
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
    report = Report.query.get_or_404(report_id)
    student = Student.query.get(report.student_id)
    if student.parent_id != current_user.id:
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
            flash('报告已重新生成', 'success')
            return redirect(
                url_for('report.detail', report_id=new_report.id)
            )
        else:
            flash('报告重新生成失败', 'danger')
    except Exception as e:
        flash(f'报告重新生成出错: {str(e)}', 'danger')

    return redirect(url_for('report.list_reports', student_id=student_id))
