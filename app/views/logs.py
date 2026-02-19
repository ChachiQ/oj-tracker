"""Logs blueprint: web-based application log viewer."""
from __future__ import annotations

import os
import re

from flask import Blueprint, render_template, current_app, request
from flask_login import login_required

logs_bp = Blueprint('logs', __name__, url_prefix='/logs')

# Regex to match the start of a log line produced by our LOG_FORMAT:
#   2026-02-19 10:30:45,123 [INFO] app.services.sync: message
_LOG_LINE_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+)\s+'
    r'\[(\w+)]\s+'
    r'([\w.]+):\s+'
    r'(.*)',
)

_LEVEL_ORDER = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}


def _read_log_lines(max_lines=500, level=None, keyword=None):
    """Read and parse the log file, returning structured entries newest-first.

    Handles multi-line entries (e.g. tracebacks) by appending continuation
    lines to the previous entry's message.
    """
    log_path = os.path.join(current_app.instance_path, 'logs', 'app.log')
    if not os.path.isfile(log_path):
        return []

    level_threshold = _LEVEL_ORDER.get(level.upper(), 0) if level else 0
    keyword_lower = keyword.strip().lower() if keyword else None

    entries = []
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return []

    current_entry = None
    for line in lines:
        m = _LOG_LINE_RE.match(line)
        if m:
            # Save previous entry
            if current_entry is not None:
                entries.append(current_entry)
            current_entry = {
                'time': m.group(1),
                'level': m.group(2),
                'source': m.group(3),
                'message': m.group(4),
            }
        elif current_entry is not None:
            # Continuation line (traceback etc.)
            current_entry['message'] += '\n' + line.rstrip('\n')

    # Don't forget the last entry
    if current_entry is not None:
        entries.append(current_entry)

    # Filter by level
    if level_threshold > 0:
        entries = [
            e for e in entries
            if _LEVEL_ORDER.get(e['level'], 0) >= level_threshold
        ]

    # Filter by keyword
    if keyword_lower:
        entries = [
            e for e in entries
            if keyword_lower in e['message'].lower()
            or keyword_lower in e['source'].lower()
        ]

    # Newest first, limited
    entries.reverse()
    return entries[:max_lines]


@logs_bp.route('/')
@login_required
def index():
    """Render the log viewer page."""
    level = request.args.get('level', '')
    keyword = request.args.get('keyword', '')
    max_lines = min(int(request.args.get('lines', 500)), 5000)

    entries = _read_log_lines(max_lines=max_lines, level=level, keyword=keyword)

    return render_template(
        'logs/index.html',
        entries=entries,
        current_level=level,
        current_keyword=keyword,
        current_lines=max_lines,
    )
