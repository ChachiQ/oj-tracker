import json

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    Problem,
    Tag,
    Submission,
    PlatformAccount,
    Student,
    AnalysisResult,
)

problem_bp = Blueprint('problem', __name__, url_prefix='/problem')


@problem_bp.route('/')
@login_required
def list_problems():
    page = request.args.get('page', 1, type=int)
    platform = request.args.get('platform', '')
    tag_name = request.args.get('tag', '')
    difficulty = request.args.get('difficulty', 0, type=int)
    search = request.args.get('q', '')

    query = Problem.query
    if platform:
        query = query.filter_by(platform=platform)
    if tag_name:
        query = query.filter(Problem.tags.any(Tag.name == tag_name))
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    if search:
        query = query.filter(Problem.title.contains(search))

    pagination = query.order_by(Problem.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    tags = Tag.query.order_by(Tag.stage, Tag.name).all()
    platforms = db.session.query(Problem.platform).distinct().all()

    return render_template(
        'problem/list.html',
        problems=pagination.items,
        pagination=pagination,
        tags=tags,
        platforms=[p[0] for p in platforms],
        current_platform=platform,
        current_tag=tag_name,
        current_difficulty=difficulty,
        search=search,
    )


@problem_bp.route('/<int:problem_id>')
@login_required
def detail(problem_id):
    problem = Problem.query.get_or_404(problem_id)

    # Get student submissions for this problem
    students = Student.query.filter_by(parent_id=current_user.id).all()
    all_account_ids = []
    for s in students:
        for a in s.platform_accounts:
            all_account_ids.append(a.id)

    submissions = (
        Submission.query.filter(
            Submission.platform_account_id.in_(all_account_ids),
            Submission.problem_id_ref == problem.id,
        )
        .order_by(Submission.submitted_at.desc())
        .all()
        if all_account_ids
        else []
    )

    # Get AI analysis results for submissions
    analysis_results = {}
    for sub in submissions:
        results = AnalysisResult.query.filter_by(
            submission_id=sub.id
        ).all()
        if results:
            analysis_results[sub.id] = results

    # Parse AI tags
    ai_tags = []
    if problem.ai_tags:
        try:
            ai_tags = json.loads(problem.ai_tags)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template(
        'problem/detail.html',
        problem=problem,
        submissions=submissions,
        analysis_results=analysis_results,
        ai_tags=ai_tags,
    )
