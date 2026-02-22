import logging
import os
import re

from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, redirect, url_for

from app.config import config_map
from app.extensions import db, login_manager, migrate, csrf

__version__ = '0.6.0'

# Matches valid HTML tags (opening, closing, self-closing, comments).
# Used to find and preserve real HTML while escaping stray < and > in text
# (e.g. math expressions like 1<n<100000000 from OJ platforms).
_VALID_HTML_TAG_RE = re.compile(
    r'(</?(?:p|br|b|i|em|strong|code|pre|ul|ol|li|table|thead|tbody'
    r'|tr|td|th|h[1-6]|a|img|div|span|sup|sub|blockquote|hr|center'
    r'|font|u|s|del|ins|small|mark|nobr)\b[^>]*/?>|<!--[\s\S]*?-->)',
    re.IGNORECASE,
)


def _escape_stray_angle_brackets(text):
    """Escape < and > that aren't part of valid HTML tags.

    Splits text by recognised HTML tags, then escapes bare < and > in the
    text fragments between those tags.  This fixes OJ descriptions that
    contain un-escaped math operators (e.g. ``1<n<100000000``) which
    browsers would otherwise swallow as broken HTML tags.
    """
    parts = _VALID_HTML_TAG_RE.split(text)
    for i in range(0, len(parts), 2):   # even indices = text between tags
        parts[i] = parts[i].replace('<', '&lt;').replace('>', '&gt;')
    return ''.join(parts)


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

    # Configure file logging
    _configure_logging(app)

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

        if delta_days < 0:
            return display_dt.strftime('%H:%M')
        elif delta_days == 0:
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
    def md2html_filter(text, escape=True, base_url=None):
        """Convert basic Markdown to HTML without external dependencies.

        Args:
            escape: If True (default), escape HTML entities first — safe for
                    AI-generated pure-Markdown content. If False, preserve
                    existing HTML tags — suitable for OJ problem content that
                    mixes Markdown and HTML.
            base_url: If set, prepend to relative image URLs (starting with /).
        """
        if not text:
            return ''
        from markupsafe import Markup
        text = str(text)

        # Normalize line endings so regex patterns match consistently
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Extract fenced code blocks before any escaping/processing
        code_blocks = []

        def _replace_code_block(m):
            lang = m.group(1) or ''
            code = m.group(2)
            # Always HTML-escape code block content independently
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            lang_class = f'language-{lang}' if lang.strip() else 'plaintext'
            html = f'<pre class="code-viewer"><code class="{lang_class}">{code}</code></pre>'
            idx = len(code_blocks)
            code_blocks.append(html)
            return f'\x00CODEBLOCK_{idx}\x00'

        text = re.sub(
            r'^```(\w*)\n(.*?)^```',
            _replace_code_block,
            text,
            flags=re.MULTILINE | re.DOTALL,
        )

        if escape:
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        else:
            # Convert Markdown images to <img> tags before escaping stray brackets
            def _img_replace(m):
                alt, src = m.group(1), m.group(2)
                if base_url and src.startswith('/'):
                    src = base_url.rstrip('/') + src
                return f'<img src="{src}" alt="{alt}" class="img-fluid">'

            text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _img_replace, text)
            # Rewrite relative URLs in existing HTML <img> tags
            if base_url:
                def _html_img_replace(m):
                    prefix, src, suffix = m.group(1), m.group(2), m.group(3)
                    if src.startswith('/'):
                        src = base_url.rstrip('/') + src
                    return f'{prefix}{src}{suffix}'
                text = re.sub(
                    r'(<img\s[^>]*src=["\'])(/[^"\']+)(["\'])',
                    _html_img_replace, text, flags=re.IGNORECASE,
                )
            text = _escape_stray_angle_brackets(text)
        # Headings: #### h6, ### h5, ## h4, # h3
        text = re.sub(r'^#### (.+)$', r'<h6>\1</h6>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.+)$', r'<h5>\1</h5>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        # Horizontal rules: --- or more dashes on their own line
        text = re.sub(r'^-{3,}\s*$', '<hr>', text, flags=re.MULTILINE)
        # Bold **text**
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Italic *text* (but not inside strong tags)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
        # Unordered list items: - item or * item → use <uli> placeholder
        text = re.sub(r'^[-*] (.+)$', r'<uli>\1</uli>', text, flags=re.MULTILINE)
        # Ordered list items: 1. item → use <oli> placeholder
        text = re.sub(r'^\d+\. (.+)$', r'<oli>\1</oli>', text, flags=re.MULTILINE)
        # Wrap consecutive <uli> in <ul>
        text = re.sub(
            r'((?:<uli>.*?</uli>\n?)+)',
            lambda m: '<ul>' + m.group(1).replace('<uli>', '<li>').replace('</uli>', '</li>') + '</ul>',
            text,
        )
        # Wrap consecutive <oli> in <ol>
        text = re.sub(
            r'((?:<oli>.*?</oli>\n?)+)',
            lambda m: '<ol>' + m.group(1).replace('<oli>', '<li>').replace('</oli>', '</li>') + '</ol>',
            text,
        )
        # Paragraphs: split on double newlines
        parts = re.split(r'\n{2,}', text)
        result = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.startswith(('<h', '<ul', '<ol', '<hr')):
                result.append(part)
            else:
                # Convert single newlines to <br> (without keeping \n)
                part = part.replace('\n', '<br>')
                result.append(f'<p>{part}</p>')
        text = '\n'.join(result)

        # Restore code block placeholders
        if code_blocks:
            # Unwrap <p> tags around placeholders
            for idx in range(len(code_blocks)):
                placeholder = f'\x00CODEBLOCK_{idx}\x00'
                text = text.replace(f'<p>{placeholder}</p>', placeholder)
                text = text.replace(placeholder, code_blocks[idx])

        return Markup(text)

    @app.template_test('has_markdown')
    def has_markdown_test(text):
        """Detect CTOJ-style Markdown in examples (fenced code blocks or ### headings)."""
        if not text:
            return False
        return bool(re.search(r'```|^###\s', str(text), re.MULTILINE))

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
        _cleanup_stale_jobs(app)

    return app


def _configure_logging(app):
    """Set up RotatingFileHandler on the root logger."""
    max_bytes = app.config.get('LOG_FILE_MAX_BYTES', 0)
    if not max_bytes:
        return

    log_dir = os.path.join(app.instance_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'app.log')
    handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=app.config.get('LOG_FILE_BACKUP_COUNT', 3),
    )
    handler.setFormatter(logging.Formatter(
        app.config.get('LOG_FORMAT', '%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    ))
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.WARNING:
        root.setLevel(logging.DEBUG)


def _cleanup_stale_jobs(app):
    """Mark stale running SyncJobs as failed on startup."""
    from app.models import SyncJob
    try:
        count = SyncJob.cleanup_stale_running()
        if count:
            app.logger.info(f'Cleaned up {count} stale running SyncJob(s)')
    except Exception:
        db.session.rollback()


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
    from app.views.sync import sync_bp
    from app.views.logs import logs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(student_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(problem_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(logs_bp)


def _init_scheduler(app):
    """Initialize and start APScheduler for background tasks."""
    from app.tasks.scheduler import init_scheduler
    init_scheduler(app)
