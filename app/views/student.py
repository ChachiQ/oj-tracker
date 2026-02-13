from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Student, PlatformAccount, Submission

student_bp = Blueprint('student', __name__, url_prefix='/student')


@student_bp.route('/')
@login_required
def list_students():
    students = Student.query.filter_by(parent_id=current_user.id).all()
    return render_template('student/list.html', students=students)


@student_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        birthday_str = request.form.get('birthday', '')
        grade = request.form.get('grade', '')
        level = request.form.get('level', '提高')
        school_math_level = request.form.get('school_math_level', '').strip()
        notes = request.form.get('notes', '').strip()

        if not name:
            flash('请填写学生姓名', 'danger')
        else:
            birthday = None
            if birthday_str:
                try:
                    birthday = datetime.strptime(
                        birthday_str, '%Y-%m-%d'
                    ).date()
                except ValueError:
                    pass

            student = Student(
                parent_id=current_user.id,
                name=name,
                birthday=birthday,
                grade=grade,
                level=level,
                school_math_level=(
                    school_math_level if school_math_level else None
                ),
                notes=notes if notes else None,
            )
            db.session.add(student)
            db.session.commit()
            flash(f'已添加学生 {name}', 'success')
            return redirect(url_for('student.list_students'))

    return render_template('student/form.html', student=None)


@student_bp.route('/<int:student_id>')
@login_required
def detail(student_id):
    student = Student.query.get_or_404(student_id)
    if student.parent_id != current_user.id:
        flash('无权访问', 'danger')
        return redirect(url_for('student.list_students'))

    accounts = PlatformAccount.query.filter_by(student_id=student_id).all()
    # Get recent submissions
    account_ids = [a.id for a in accounts]
    recent_subs = (
        Submission.query.filter(
            Submission.platform_account_id.in_(account_ids)
        )
        .order_by(Submission.submitted_at.desc())
        .limit(20)
        .all()
        if account_ids
        else []
    )

    return render_template(
        'student/detail.html',
        student=student,
        accounts=accounts,
        recent_submissions=recent_subs,
    )


@student_bp.route('/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if student.parent_id != current_user.id:
        flash('无权访问', 'danger')
        return redirect(url_for('student.list_students'))

    if request.method == 'POST':
        student.name = (
            request.form.get('name', '').strip() or student.name
        )
        birthday_str = request.form.get('birthday', '')
        if birthday_str:
            try:
                student.birthday = datetime.strptime(
                    birthday_str, '%Y-%m-%d'
                ).date()
            except ValueError:
                pass
        student.grade = request.form.get('grade', student.grade)
        student.level = request.form.get('level', student.level)
        student.school_math_level = (
            request.form.get('school_math_level', '').strip() or None
        )
        student.notes = request.form.get('notes', '').strip() or None
        db.session.commit()
        flash('学生信息已更新', 'success')
        return redirect(url_for('student.detail', student_id=student.id))

    return render_template('student/form.html', student=student)
