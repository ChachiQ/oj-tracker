import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for

from app.config import config_map
from app.extensions import db, login_manager, migrate, csrf


def create_app(config_name=None):
    """Application factory for creating the Flask app instance.

    Args:
        config_name: Configuration name ('development' or 'production').
                     Defaults to FLASK_ENV environment variable or 'development'.

    Returns:
        Configured Flask application instance.
    """
    # Load environment variables from the appropriate .env file
    env = config_name or os.environ.get('FLASK_ENV', 'development')
    env_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        f'.env.{env}',
    )
    if os.path.exists(env_file):
        load_dotenv(env_file)

    # Also load a local .env if it exists (overrides the environment-specific one)
    dotenv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '.env',
    )
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path, override=True)

    # Determine final config name after env files are loaded
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    # Create Flask app
    app = Flask(__name__)

    # Load configuration
    config_class = config_map.get(config_name, config_map['development'])
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Register user loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return db.session.get(User, int(user_id))

    # Register blueprints
    _register_blueprints(app)

    # Root URL redirect to dashboard
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    # Initialize scheduler if enabled
    if app.config.get('SCHEDULER_ENABLED'):
        _init_scheduler(app)

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app


def _register_blueprints(app):
    """Register all application blueprints."""
    from app.views.auth import auth_bp
    from app.views.dashboard import dashboard_bp
    from app.views.student import student_bp
    from app.views.report import report_bp
    from app.views.knowledge import knowledge_bp
    from app.views.settings import settings_bp
    from app.views.api import api_bp
    from app.views.problem import problem_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(student_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(problem_bp)


def _init_scheduler(app):
    """Initialize and start APScheduler for background tasks."""
    from app.tasks.scheduler import init_scheduler
    init_scheduler(app)
