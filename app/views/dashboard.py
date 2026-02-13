from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models import Student
from app.services.stats_service import StatsService

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    students = Student.query.filter_by(parent_id=current_user.id).all()
    student_id = request.args.get('student_id', type=int)

    if not students:
        return render_template(
            'dashboard/index.html',
            students=students,
            data=None,
            current_student=None,
        )

    current_student = None
    if student_id:
        current_student = Student.query.get(student_id)
    if not current_student or current_student.parent_id != current_user.id:
        current_student = students[0]

    data = StatsService.get_dashboard_data(current_student.id)
    return render_template(
        'dashboard/index.html',
        students=students,
        data=data,
        current_student=current_student,
    )
