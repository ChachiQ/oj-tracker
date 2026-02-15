"""Tests for mobile-responsive UI adaptations.

Verifies that templates render correct responsive CSS classes, macro outputs,
and structural patterns needed for mobile/tablet breakpoints.
"""

import re
from datetime import datetime, timedelta

import pytest
from bs4 import BeautifulSoup

from app.extensions import db
from app.models import Report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_soup(response):
    """Parse response HTML into BeautifulSoup."""
    return BeautifulSoup(response.data.decode('utf-8'), 'html.parser')


def has_classes(element, *classes):
    """Check that an element has all the specified CSS classes."""
    el_classes = element.get('class', [])
    return all(c in el_classes for c in classes)


# ===========================================================================
# Macro output tests: stat_card, page_header, chart_box, empty_state,
#                      table_col_class, student_selector
# ===========================================================================

class TestStatCardMacro:
    """stat_card macro should render responsive columns with correct structure."""

    def test_stat_cards_have_responsive_columns(self, app, logged_in_client):
        """Each stat card wrapper should have col-6 col-md-4 col-xl."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        stat_cards = soup.select('.stat-card')
        assert len(stat_cards) >= 5, 'Dashboard should have at least 5 stat cards'

        for card in stat_cards:
            wrapper = card.find_parent('div', class_='col-6')
            assert wrapper is not None, 'stat_card should be wrapped in col-6'
            assert has_classes(wrapper, 'col-6', 'col-md-4', 'col-xl'), \
                f'stat_card wrapper missing responsive classes, got: {wrapper.get("class")}'

    def test_stat_card_value_id(self, app, logged_in_client):
        """stat_card with value_id should render an id attribute."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        for vid in ['stat-total', 'stat-ac', 'stat-week', 'stat-streak', 'stat-first-ac']:
            el = soup.find(id=vid)
            assert el is not None, f'stat_card should render value_id={vid}'
            assert 'stat-value' in el.get('class', [])

    def test_first_ac_stat_card(self, app, logged_in_client):
        """Dashboard should have stat-first-ac card with stat-value class."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        el = soup.find(id='stat-first-ac')
        assert el is not None, 'Dashboard should have id="stat-first-ac"'
        assert 'stat-value' in el.get('class', []), \
            'stat-first-ac should have stat-value class'

    def test_report_detail_responsive_layout(self, app, logged_in_client):
        """Report detail page should have responsive col-12 col-lg-* layout."""
        client, data = logged_in_client
        with app.app_context():
            report = Report(
                student_id=data['student_id'],
                report_type='weekly',
                period_start=datetime.utcnow() - timedelta(days=7),
                period_end=datetime.utcnow(),
                stats_json='{}',
                ai_content='Test report content',
            )
            db.session.add(report)
            db.session.commit()
            rid = report.id

        resp = client.get(f'/report/{rid}')
        soup = get_soup(resp)

        # Radar and AI content columns should use col-12 + col-lg
        radar_col = soup.find('div', class_=lambda c: c and 'col-lg-5' in c and 'col-12' in c)
        assert radar_col is not None, 'Report detail should have col-12 col-lg-5 for radar'

        content_col = soup.find('div', class_=lambda c: c and 'col-lg-7' in c and 'col-12' in c)
        assert content_col is not None, 'Report detail should have col-12 col-lg-7 for AI content'


class TestPageHeaderMacro:
    """page_header macro should render flex-wrap header with optional actions."""

    def test_dashboard_page_header(self, app, logged_in_client):
        """Dashboard should have a page_header with flex-wrap."""
        client, data = logged_in_client
        resp = client.get('/dashboard/')
        soup = get_soup(resp)

        header = soup.find('h4', class_='fw-bold')
        assert header is not None
        header_wrapper = header.find_parent('div')
        assert has_classes(header_wrapper, 'd-flex', 'flex-wrap', 'gap-2')

    def test_student_list_page_header_with_action(self, app, logged_in_client):
        """Student list page_header should have action button in caller block."""
        client, data = logged_in_client
        resp = client.get('/student/')
        soup = get_soup(resp)

        header_wrapper = soup.find('div', class_='d-flex')
        assert header_wrapper is not None
        # Should contain the add student button
        add_btn = header_wrapper.find('a', class_='btn-primary')
        assert add_btn is not None

    def test_report_list_page_header(self, app, logged_in_client):
        """Report list should have page_header with student_selector."""
        client, data = logged_in_client
        resp = client.get('/report/')
        soup = get_soup(resp)

        header = soup.find('h4', class_='fw-bold')
        assert header is not None
        assert '学习报告' in header.get_text()

    def test_problem_list_page_header(self, app, logged_in_client):
        """Problem list should use page_header macro."""
        client, data = logged_in_client
        resp = client.get('/problem/')
        soup = get_soup(resp)

        header = soup.find('h4', class_='fw-bold')
        assert header is not None
        assert '题库' in header.get_text()


class TestChartBoxMacro:
    """chart_box macro should use CSS height classes instead of inline styles."""

    def test_dashboard_charts_use_responsive_class(self, app, logged_in_client):
        """Dashboard chart containers should use chart-responsive CSS class."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        for chart_id in ['radar-chart', 'heatmap-chart', 'difficulty-chart', 'status-chart', 'trend-chart']:
            el = soup.find(id=chart_id)
            assert el is not None, f'Chart container {chart_id} not found'
            assert 'chart-responsive' in el.get('class', []), \
                f'{chart_id} should use chart-responsive CSS class'

    def test_knowledge_graph_uses_lg_class(self, app, logged_in_client):
        """Knowledge graph should use chart-responsive-lg for larger height."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/knowledge/?student_id={sid}')
        soup = get_soup(resp)

        graph = soup.find(id='knowledge-graph')
        assert graph is not None
        assert 'chart-responsive-lg' in graph.get('class', []), \
            'Knowledge graph should use chart-responsive-lg class'

    def test_chart_box_renders_title(self, app, logged_in_client):
        """chart_box should render a chart-title div when title is provided."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        chart_titles = soup.select('.chart-title')
        assert len(chart_titles) >= 5, 'Dashboard should have at least 5 chart titles'

    def test_dashboard_new_chart_containers(self, app, logged_in_client):
        """Dashboard HTML should contain new chart containers."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        for container_id in ['status-chart', 'trend-chart', 'platform-stats']:
            el = soup.find(id=container_id)
            assert el is not None, f'Dashboard should contain id="{container_id}"'


class TestEmptyStateMacro:
    """empty_state macro should render responsive icon classes."""

    def test_dashboard_empty_state_no_students(self, auth_client):
        """Dashboard with no students should show empty_state with responsive icon."""
        resp = auth_client.get('/dashboard/')
        soup = get_soup(resp)

        empty_icon = soup.select_one('.empty-state-icon')
        assert empty_icon is not None, 'Empty state should use empty-state-icon CSS class'

    def test_empty_state_has_correct_structure(self, auth_client):
        """Empty state should be centered with proper padding."""
        resp = auth_client.get('/dashboard/')
        soup = get_soup(resp)

        # Should have centered container
        centered = soup.find('div', class_='text-center')
        assert centered is not None

    def test_settings_small_empty_state(self, app, logged_in_client):
        """Settings page empty account list should use small empty state."""
        client, data = logged_in_client
        # Delete the existing account first
        acc_id = data['account_id']
        client.post(f'/settings/account/{acc_id}/delete')

        resp = client.get('/settings/')
        soup = get_soup(resp)

        small_icon = soup.select_one('.empty-state-icon-sm')
        assert small_icon is not None, 'Small empty state should use empty-state-icon-sm class'


class TestTableColClassMacro:
    """table_col_class should output responsive d-none/d-{bp}-table-cell classes."""

    def test_student_list_table_responsive_columns(self, app, logged_in_client):
        """Student list table should hide columns on small screens."""
        client, data = logged_in_client
        resp = client.get('/student/')
        soup = get_soup(resp)

        table = soup.find('table')
        assert table is not None, 'Student list should have a table'
        headers = table.find_all('th')

        # # column and 水平 column should have d-none d-sm-table-cell
        sm_hidden = [th for th in headers if has_classes(th, 'd-none', 'd-sm-table-cell')]
        assert len(sm_hidden) >= 1, 'At least 1 column should be hidden below sm breakpoint'

        # 绑定账号数 and 创建时间 should have d-none d-md-table-cell
        md_hidden = [th for th in headers if has_classes(th, 'd-none', 'd-md-table-cell')]
        assert len(md_hidden) >= 1, 'At least 1 column should be hidden below md breakpoint'

    def test_problem_list_table_responsive_columns(self, app, logged_in_client):
        """Problem list should hide difficulty at md, knowledge/AI at lg."""
        client, data = logged_in_client
        resp = client.get('/problem/')
        soup = get_soup(resp)

        table = soup.find('table')
        assert table is not None
        headers = table.find_all('th')

        md_hidden = [th for th in headers if has_classes(th, 'd-none', 'd-md-table-cell')]
        assert len(md_hidden) >= 1, 'Difficulty column should be hidden below md'

        lg_hidden = [th for th in headers if has_classes(th, 'd-none', 'd-lg-table-cell')]
        assert len(lg_hidden) >= 2, 'Knowledge and AI columns should be hidden below lg'

    def test_report_list_table_responsive_columns(self, app, logged_in_client):
        """Report list table should hide # at sm and 生成时间 at md."""
        client, data = logged_in_client
        # Create a report so the table is displayed
        with app.app_context():
            report = Report(
                student_id=data['student_id'],
                report_type='weekly',
                period_start=datetime.utcnow() - timedelta(days=7),
                period_end=datetime.utcnow(),
                stats_json='{}',
                ai_content='Test',
            )
            db.session.add(report)
            db.session.commit()

        resp = client.get('/report/')
        soup = get_soup(resp)

        table = soup.find('table')
        assert table is not None
        headers = table.find_all('th')

        sm_hidden = [th for th in headers if has_classes(th, 'd-none', 'd-sm-table-cell')]
        assert len(sm_hidden) >= 1, '# column should be hidden below sm'

        md_hidden = [th for th in headers if has_classes(th, 'd-none', 'd-md-table-cell')]
        assert len(md_hidden) >= 1, '生成时间 should be hidden below md'

    def test_settings_table_responsive_columns(self):
        """Settings template should use table_col_class('md') for hiding columns.

        The template source must reference responsive column hiding for
        account ID and last sync columns, regardless of whether the view
        currently passes the accounts data.
        """
        with open('app/templates/settings/index.html', 'r') as f:
            template_src = f.read()

        # Template should invoke table_col_class('md') for responsive hiding
        assert "table_col_class('md')" in template_src, \
            'Settings template should use table_col_class macro for md columns'
        # Should appear at least twice (account ID + last sync)
        count = template_src.count("table_col_class('md')")
        assert count >= 2, \
            f'Settings should hide >= 2 columns at md breakpoint, found {count}'

    def test_table_body_columns_match_headers(self, app, logged_in_client):
        """Table body tds should have same responsive classes as their th."""
        client, data = logged_in_client
        resp = client.get('/student/')
        soup = get_soup(resp)

        table = soup.find('table')
        assert table is not None

        tbody = table.find('tbody')
        if tbody:
            first_row = tbody.find('tr')
            if first_row:
                tds = first_row.find_all('td')
                # Check that some tds also have d-none classes
                hidden_tds = [td for td in tds if 'd-none' in td.get('class', [])]
                assert len(hidden_tds) >= 1, \
                    'Table body cells should also have responsive hide classes'


class TestStudentSelectorMacro:
    """student_selector should render with flex-wrap for mobile."""

    def test_dashboard_student_selector(self, app, logged_in_client):
        """Dashboard should have student selector with flex-wrap."""
        client, data = logged_in_client
        resp = client.get('/dashboard/')
        soup = get_soup(resp)

        selector = soup.find('select', id='student-selector')
        assert selector is not None, 'Dashboard should render student selector'

        wrapper = selector.find_parent('div', class_='d-flex')
        assert wrapper is not None
        assert has_classes(wrapper, 'd-flex', 'flex-wrap', 'gap-2')

    def test_knowledge_student_selector(self, app, logged_in_client):
        """Knowledge page should have student selector."""
        client, data = logged_in_client
        resp = client.get('/knowledge/')
        soup = get_soup(resp)

        selector = soup.find('select', id='student-selector')
        assert selector is not None


# ===========================================================================
# Responsive layout tests: grid columns, flex-wrap, table-responsive
# ===========================================================================

class TestResponsiveGridLayout:
    """Verify responsive grid column classes across pages."""

    def test_dashboard_chart_rows_have_col_12(self, app, logged_in_client):
        """Dashboard chart columns should start with col-12 for mobile stacking."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        soup = get_soup(resp)

        for chart_id in ['radar-chart', 'heatmap-chart', 'difficulty-chart']:
            el = soup.find(id=chart_id)
            if el:
                col_div = el.find_parent('div', class_='col-12')
                assert col_div is not None, \
                    f'{chart_id} parent should have col-12 for mobile stacking'

    def test_report_detail_columns_responsive(self, app, logged_in_client):
        """Report detail should have col-12 + col-lg breakpoints."""
        client, data = logged_in_client
        with app.app_context():
            report = Report(
                student_id=data['student_id'],
                report_type='weekly',
                period_start=datetime.utcnow() - timedelta(days=7),
                period_end=datetime.utcnow(),
                stats_json='{}',
                ai_content='Test',
            )
            db.session.add(report)
            db.session.commit()
            rid = report.id

        resp = client.get(f'/report/{rid}')
        soup = get_soup(resp)

        radar_col = soup.find(id='report-radar')
        if radar_col:
            col = radar_col.find_parent('div', class_='col-12')
            assert col is not None, 'Report radar should be in col-12 column'
            assert has_classes(col, 'col-12', 'col-lg-5')

    def test_student_detail_layout_responsive(self, app, logged_in_client):
        """Student detail should have col-12 col-lg-4 / col-12 col-lg-8."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/student/{sid}')
        soup = get_soup(resp)

        # Find the main row
        row = soup.find('div', class_='row')
        assert row is not None

        cols = row.find_all('div', recursive=False)
        col_classes = [' '.join(c.get('class', [])) for c in cols]

        # Should have col-12 col-lg-4 and col-12 col-lg-8
        has_info_col = any('col-12' in c and 'col-lg-4' in c for c in col_classes)
        has_main_col = any('col-12' in c and 'col-lg-8' in c for c in col_classes)
        assert has_info_col, 'Student detail should have col-12 col-lg-4 info column'
        assert has_main_col, 'Student detail should have col-12 col-lg-8 main column'

    def test_student_form_grade_level_responsive(self, app, logged_in_client):
        """Student form grade/level fields should have col-12 col-md-6."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/student/{sid}/edit')
        soup = get_soup(resp)

        grade_select = soup.find('select', id='grade')
        assert grade_select is not None
        col = grade_select.find_parent('div', class_='col-12')
        assert col is not None
        assert has_classes(col, 'col-12', 'col-md-6'), \
            'Grade field should be in col-12 col-md-6'

    def test_problem_filter_form_responsive(self, app, logged_in_client):
        """Problem list filter form columns should have col-12 col-sm-6 col-md-2."""
        client, data = logged_in_client
        resp = client.get('/problem/')
        soup = get_soup(resp)

        platform_select = soup.find('select', id='filter-platform')
        assert platform_select is not None

        col = platform_select.find_parent('div', class_='col-12')
        assert col is not None
        assert has_classes(col, 'col-12', 'col-sm-6', 'col-md-2'), \
            'Filter columns should have col-12 col-sm-6 col-md-2'

    def test_settings_subsections_responsive(self, app, logged_in_client):
        """Settings AI/instructions sections should have col-12 col-lg-6."""
        client, data = logged_in_client
        resp = client.get('/settings/')
        soup = get_soup(resp)

        # Find col-12 col-lg-6 sections
        lg6_cols = soup.find_all('div', class_=lambda c: c and 'col-lg-6' in c)
        for col in lg6_cols:
            assert 'col-12' in col.get('class', []), \
                'Settings sub-sections should have col-12 prefix'


class TestTableResponsive:
    """All data tables should be wrapped in table-responsive."""

    def test_student_list_table_responsive(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/student/')
        soup = get_soup(resp)
        assert soup.select_one('.table-responsive') is not None

    def test_problem_list_table_responsive(self, app, logged_in_client):
        client, data = logged_in_client
        resp = client.get('/problem/')
        soup = get_soup(resp)
        assert soup.select_one('.table-responsive') is not None

    def test_settings_table_responsive(self):
        """Settings template should wrap the accounts table in table-responsive."""
        with open('app/templates/settings/index.html', 'r') as f:
            template_src = f.read()
        assert 'table-responsive' in template_src, \
            'Settings template should have table-responsive wrapper'


class TestFlexWrapPatterns:
    """Containers that may overflow should use flex-wrap."""

    def test_card_headers_flex_wrap(self, app, logged_in_client):
        """Card headers with actions should have flex-wrap gap-2."""
        client, data = logged_in_client

        # Settings has card-header with action buttons
        resp = client.get('/settings/')
        soup = get_soup(resp)
        header = soup.find('div', class_='card-header')
        assert header is not None
        assert has_classes(header, 'flex-wrap', 'gap-2'), \
            'Settings card-header should have flex-wrap gap-2'

    def test_student_detail_card_header_flex_wrap(self, app, logged_in_client):
        """Student detail card headers with actions should flex-wrap."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/student/{sid}')
        soup = get_soup(resp)

        # Platform accounts card header
        headers = soup.find_all('div', class_='card-header')
        action_headers = [h for h in headers if h.find('a', class_='btn')]
        for h in action_headers:
            assert has_classes(h, 'flex-wrap', 'gap-2'), \
                'Card headers with actions should have flex-wrap gap-2'


# ===========================================================================
# Knowledge graph mobile adaptations
# ===========================================================================

class TestKnowledgeGraphResponsive:
    """Knowledge graph page mobile-specific elements."""

    def test_node_detail_panel_max_width(self, app, logged_in_client):
        """Node detail panel should have max-width: calc(100vw - 40px)."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/knowledge/?student_id={sid}')
        html = resp.data.decode('utf-8')

        assert 'calc(100vw - 40px)' in html, \
            'Node detail panel should have max-width: calc(100vw - 40px)'

    def test_knowledge_graph_has_data_student_id(self, app, logged_in_client):
        """Knowledge graph container should have data-student-id for JS."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/knowledge/?student_id={sid}')
        soup = get_soup(resp)

        graph = soup.find(id='knowledge-graph')
        assert graph is not None
        # extra_attrs are rendered via Jinja2 which may auto-escape quotes,
        # so the attribute value can contain literal quote characters.
        attr_val = graph.get('data-student-id', '')
        assert str(sid) in attr_val.strip('"')


# ===========================================================================
# CSS responsive classes existence in stylesheet
# ===========================================================================

class TestCSSResponsiveClasses:
    """Verify that the CSS file contains required responsive rules."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        with open('app/static/css/style.css', 'r') as f:
            self.css = f.read()

    def test_chart_responsive_class_exists(self):
        assert '.chart-responsive' in self.css

    def test_chart_responsive_lg_class_exists(self):
        assert '.chart-responsive-lg' in self.css

    def test_empty_state_icon_class_exists(self):
        assert '.empty-state-icon' in self.css

    def test_empty_state_icon_sm_class_exists(self):
        assert '.empty-state-icon-sm' in self.css

    def test_media_query_768_exists(self):
        assert '@media (max-width: 768px)' in self.css

    def test_media_query_576_exists(self):
        assert '@media (max-width: 576px)' in self.css

    def test_chart_responsive_in_768_media_query(self):
        """chart-responsive should have reduced height in 768px media query."""
        # Find the 768px media query block
        match = re.search(
            r'@media\s*\(max-width:\s*768px\)\s*\{(.*?)\n\}',
            self.css, re.DOTALL
        )
        assert match is not None
        block = match.group(1)
        assert '.chart-responsive' in block
        assert '280px' in block

    def test_chart_responsive_in_576_media_query(self):
        """chart-responsive should have further reduced height in 576px query."""
        match = re.search(
            r'@media\s*\(max-width:\s*576px\)\s*\{(.*?)\n\}',
            self.css, re.DOTALL
        )
        assert match is not None
        block = match.group(1)
        assert '.chart-responsive' in block
        assert '220px' in block

    def test_stat_card_font_reduction_in_576(self):
        """stat-card should have reduced font size in 576px query."""
        match = re.search(
            r'@media\s*\(max-width:\s*576px\)\s*\{(.*?)\n\}',
            self.css, re.DOTALL
        )
        assert match is not None
        block = match.group(1)
        assert '.stat-card' in block
        assert '1.25rem' in block

    def test_node_detail_panel_mobile_repositioned(self):
        """node-detail-panel should be repositioned in 768px query."""
        match = re.search(
            r'@media\s*\(max-width:\s*768px\)\s*\{(.*?)\n\}',
            self.css, re.DOTALL
        )
        assert match is not None
        block = match.group(1)
        assert '#node-detail-panel' in block
        assert 'max-height' in block


# ===========================================================================
# JS mobile adaptation tests (verify scripts are loaded)
# ===========================================================================

class TestJSMobileAdaptation:
    """Verify JS files are included on the correct pages."""

    def test_dashboard_loads_dashboard_js(self, app, logged_in_client):
        """Dashboard with student should load dashboard.js."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/dashboard/?student_id={sid}')
        html = resp.data.decode('utf-8')
        assert 'dashboard.js' in html

    def test_knowledge_loads_knowledge_js(self, app, logged_in_client):
        """Knowledge graph with student should load knowledge_graph.js."""
        client, data = logged_in_client
        sid = data['student_id']
        resp = client.get(f'/knowledge/?student_id={sid}')
        html = resp.data.decode('utf-8')
        assert 'knowledge_graph.js' in html

    def test_report_detail_loads_report_js(self, app, logged_in_client):
        """Report detail should load report.js."""
        client, data = logged_in_client
        with app.app_context():
            report = Report(
                student_id=data['student_id'],
                report_type='weekly',
                period_start=datetime.utcnow() - timedelta(days=7),
                period_end=datetime.utcnow(),
                stats_json='{}',
                ai_content='Test',
            )
            db.session.add(report)
            db.session.commit()
            rid = report.id

        resp = client.get(f'/report/{rid}')
        html = resp.data.decode('utf-8')
        assert 'report.js' in html


class TestJSContainsMobileChecks:
    """Verify JS files contain isMobile() function for responsive behavior."""

    def test_dashboard_js_has_is_mobile(self):
        with open('app/static/js/dashboard.js', 'r') as f:
            content = f.read()
        assert 'isMobile' in content, 'dashboard.js should have isMobile function'
        assert 'window.innerWidth' in content

    def test_knowledge_graph_js_has_is_mobile(self):
        with open('app/static/js/knowledge_graph.js', 'r') as f:
            content = f.read()
        assert 'isMobile' in content, 'knowledge_graph.js should have isMobile function'
        assert 'isTablet' in content, 'knowledge_graph.js should have isTablet function'

    def test_report_js_has_is_mobile(self):
        with open('app/static/js/report.js', 'r') as f:
            content = f.read()
        assert 'isMobile' in content, 'report.js should have isMobile function'

    def test_dashboard_js_mobile_radar_config(self):
        """Dashboard radar chart should adjust splitNumber for mobile."""
        with open('app/static/js/dashboard.js', 'r') as f:
            content = f.read()
        assert 'splitNumber' in content
        # Should reference mobile variable for conditional config
        assert 'mobile' in content

    def test_dashboard_js_mobile_heatmap_config(self):
        """Dashboard heatmap should hide visualMap on mobile."""
        with open('app/static/js/dashboard.js', 'r') as f:
            content = f.read()
        assert 'visualMap' in content
        assert 'show' in content

    def test_knowledge_js_mobile_force_params(self):
        """Knowledge graph should adjust force params for mobile."""
        with open('app/static/js/knowledge_graph.js', 'r') as f:
            content = f.read()
        assert 'repulsion' in content
        assert 'gravity' in content
        assert 'edgeLength' in content

    def test_knowledge_graph_js_dependency_highlight(self):
        """knowledge_graph.js should contain dependency highlighting functions."""
        with open('app/static/js/knowledge_graph.js', 'r') as f:
            content = f.read()
        for func in ['buildDependencyMaps', 'toggleDependencyHighlight',
                      'restoreGraph', 'findAllAncestors', 'findAllDescendants']:
            assert func in content, \
                f'knowledge_graph.js should contain {func}'

    def test_knowledge_graph_js_jump_link(self):
        """knowledge_graph.js should support problem list jump links."""
        with open('app/static/js/knowledge_graph.js', 'r') as f:
            content = f.read()
        assert 'encodeURIComponent' in content, \
            'knowledge_graph.js should use encodeURIComponent for jump links'

    def test_report_js_mobile_radar_config(self):
        """Report radar should adjust radius for mobile."""
        with open('app/static/js/report.js', 'r') as f:
            content = f.read()
        assert 'radius' in content
        assert 'mobile' in content
