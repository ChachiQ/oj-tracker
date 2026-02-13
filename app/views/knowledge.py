from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models import Student
from app.services.stats_service import StatsService

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/knowledge')


@knowledge_bp.route('/')
@login_required
def graph():
    students = Student.query.filter_by(parent_id=current_user.id).all()
    student_id = request.args.get('student_id', type=int)

    current_student = None
    graph_data = None

    if students:
        if student_id:
            current_student = Student.query.get(student_id)
        if (
            not current_student
            or current_student.parent_id != current_user.id
        ):
            current_student = students[0]
        graph_data = StatsService.get_knowledge_graph_data(
            current_student.id
        )

    return render_template(
        'knowledge/graph.html',
        students=students,
        current_student=current_student,
        graph_data=graph_data,
    )
