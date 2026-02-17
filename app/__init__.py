import os
import re

from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from flask import Flask, redirect, url_for

from app.config import config_map
from app.extensions import db, login_manager, migrate, csrf

__version__ = '0.5.0'


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

    # Timezone helper
    def to_display_tz(dt, _app=None):
        """Convert a naive UTC datetime to the configured display timezone."""
        target = _app or app
        offset = target.config.get('DISPLAY_TIMEZONE_OFFSET', 8)
        tz = timezone(timedelta(hours=offset))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)

    app.to_display_tz = to_display_tz

    # Register custom Jinja2 filters
    @app.template_filter('smarttime')
    def smarttime_filter(dt):
        """将 datetime 格式化为微信风格的智能相对时间（时区感知）。"""
        if not dt:
            return '-'
        display_dt = to_display_tz(dt)
        now = to_display_tz(datetime.utcnow())
        today = now.date()
        dt_date = display_dt.date()
        delta_days = (today - dt_date).days

        if delta_days == 0:
            return display_dt.strftime('%H:%M')
        elif delta_days == 1:
            return '昨天'
        elif delta_days == 2:
            return '前天'
        elif delta_days <= 7:
            return f'{delta_days}天前'
        elif display_dt.year == now.year:
            return display_dt.strftime('%m-%d')
        else:
            return display_dt.strftime('%Y-%m-%d')

    @app.template_filter('datefmt')
    def datefmt_filter(dt, fmt='%Y-%m-%d %H:%M'):
        """Format a UTC datetime in display timezone."""
        if not dt:
            return '-'
        return to_display_tz(dt).strftime(fmt)

    @app.template_filter('md2html')
    def md2html_filter(text):
        """Convert basic Markdown to HTML without external dependencies."""
        if not text:
            return ''
        from markupsafe import Markup
        text = str(text)
        # Escape HTML entities first
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # Headings: ### h3, ## h2, # h1
        text = re.sub(r'^### (.+)$', r'<h5>\1</h5>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        # Bold **text**
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Italic *text* (but not inside strong tags)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
        # Unordered list items: - item
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        # Wrap consecutive <li> in <ul>
        text = re.sub(
            r'((?:<li>.*?</li>\n?)+)',
            r'<ul>\1</ul>',
            text,
        )
        # Paragraphs: split on double newlines
        parts = re.split(r'\n{2,}', text)
        result = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.startswith(('<h', '<ul', '<ol')):
                result.append(part)
            else:
                # Convert single newlines to <br> within paragraphs
                part = part.replace('\n', '<br>\n')
                result.append(f'<p>{part}</p>')
        return Markup('\n'.join(result))

    # Inject version into all templates
    @app.context_processor
    def inject_version():
        return dict(app_version=__version__)

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
        _fix_difficulty_data(app)

    return app


def _fix_difficulty_data(app):
    """One-time fix: clamp problem difficulty values >7 down to 7."""
    from app.models import Problem
    try:
        count = Problem.query.filter(Problem.difficulty > 7).update(
            {Problem.difficulty: 7}
        )
        if count:
            db.session.commit()
            app.logger.info(f'Fixed {count} problems with difficulty > 7')
    except Exception:
        db.session.rollback()


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
