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
from app.models import Student, Report
from app.analysis.report_generator import ReportGenerator

report_bp = Blueprint('report', __name__, url_prefix='/report')


@report_bp.route('/')
@login_required
def list_reports():
    student_id = request.args.get('student_id', type=int)
    students = Student.query.filter_by(parent_id=current_user.id).all()

    if student_id:
        reports = Report.query.filter_by(student_id=student_id).order_by(
            Report.created_at.desc()
        ).all()
        current_student = Student.query.get(student_id)
    elif students:
        current_student = students[0]
        reports = Report.query.filter_by(
            student_id=current_student.id
        ).order_by(Report.created_at.desc()).all()
    else:
        current_student = None
        reports = []

    return render_template(
        'report/list.html',
        reports=reports,
        students=students,
        current_student=current_student,
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

    generator = ReportGenerator(
        student_id, current_app._get_current_object()
    )
    try:
        if report_type == 'monthly':
            report = generator.generate_monthly_report()
        else:
            report = generator.generate_weekly_report()

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
