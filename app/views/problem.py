import json

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, case
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


def _is_valid_analysis(result):
    """Check if an AnalysisResult has valid, non-empty JSON in result_json."""
    if not result or not result.result_json:
        return False
    try:
        parsed = json.loads(result.result_json)
        return isinstance(parsed, dict) and len(parsed) > 0
    except (json.JSONDecodeError, TypeError):
        return False


@problem_bp.route('/')
@login_required
def list_problems():
    page = request.args.get('page', 1, type=int)
    platform = request.args.get('platform', '')
    tag_name = request.args.get('tag', '')
    difficulty = request.args.get('difficulty', 0, type=int)
    search = request.args.get('q', '')

    # Gather account IDs for current user's students
    students = Student.query.filter_by(parent_id=current_user.id).all()
    account_ids = []
    for s in students:
        for a in s.platform_accounts:
            account_ids.append(a.id)

    query = Problem.query
    if platform:
        query = query.filter_by(platform=platform)
    if tag_name:
        query = query.filter(Problem.tags.any(Tag.name == tag_name))
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    if search:
        query = query.filter(Problem.title.contains(search))

    # Subquery: latest submission time per problem for this user's accounts
    if account_ids:
        latest_sub = (
            db.session.query(
                Submission.problem_id_ref.label('problem_id'),
                func.max(Submission.submitted_at).label('latest_at'),
            )
            .filter(Submission.platform_account_id.in_(account_ids))
            .group_by(Submission.problem_id_ref)
            .subquery()
        )
        query = query.outerjoin(
            latest_sub, Problem.id == latest_sub.c.problem_id
        ).order_by(
            case((latest_sub.c.latest_at.is_(None), 1), else_=0),
            latest_sub.c.latest_at.desc(),
        )
    else:
        query = query.order_by(Problem.created_at.desc())

    pagination = query.paginate(page=page, per_page=20, error_out=False)
    tags = Tag.query.order_by(Tag.stage, Tag.name).all()
    platforms = db.session.query(Problem.platform).distinct().all()

    # Batch-fetch latest submission (time + status) for current page's problems
    latest_submissions = {}
    problem_ids = [p.id for p in pagination.items]
    if account_ids and problem_ids:
        # Subquery to get max submitted_at per problem
        max_time = (
            db.session.query(
                Submission.problem_id_ref,
                func.max(Submission.submitted_at).label('max_at'),
            )
            .filter(
                Submission.platform_account_id.in_(account_ids),
                Submission.problem_id_ref.in_(problem_ids),
            )
            .group_by(Submission.problem_id_ref)
            .subquery()
        )
        rows = (
            db.session.query(
                Submission.problem_id_ref,
                Submission.submitted_at,
                Submission.status,
            )
            .join(
                max_time,
                db.and_(
                    Submission.problem_id_ref == max_time.c.problem_id_ref,
                    Submission.submitted_at == max_time.c.max_at,
                ),
            )
            .filter(Submission.platform_account_id.in_(account_ids))
            .all()
        )
        for row in rows:
            latest_submissions[row.problem_id_ref] = {
                'submitted_at': row.submitted_at,
                'status': row.status,
            }

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
        latest_submissions=latest_submissions,
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

    # Get AI analysis results for submissions (exclude submission_review, shown separately)
    analysis_results = {}
    for sub in submissions:
        results = AnalysisResult.query.filter(
            AnalysisResult.submission_id == sub.id,
            AnalysisResult.analysis_type != "submission_review",
        ).all()
        if results:
            analysis_results[sub.id] = results

    # Get problem-level AI analyses (filter out bad records with invalid JSON)
    solution_analysis = AnalysisResult.query.filter_by(
        problem_id_ref=problem.id, analysis_type="problem_solution",
    ).first()
    if solution_analysis and not _is_valid_analysis(solution_analysis):
        solution_analysis = None
    full_solution = AnalysisResult.query.filter_by(
        problem_id_ref=problem.id, analysis_type="problem_full_solution",
    ).first()
    if full_solution and not _is_valid_analysis(full_solution):
        full_solution = None

    # Get submission review results
    submission_reviews = {}
    for sub in submissions:
        review = AnalysisResult.query.filter_by(
            submission_id=sub.id, analysis_type="submission_review",
        ).first()
        if review:
            submission_reviews[sub.id] = review

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
        solution_analysis=solution_analysis,
        full_solution=full_solution,
        submission_reviews=submission_reviews,
        ai_tags=ai_tags,
    )
