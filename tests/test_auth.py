"""Tests for authentication: register, login, logout, permissions."""

import pytest
from app.models import User


class TestRegister:
    def test_get_register_page(self, client):
        resp = client.get('/auth/register')
        assert resp.status_code == 200

    def test_register_success(self, app, db, client):
        resp = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'pass123',
            'password_confirm': 'pass123',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')

        with app.app_context():
            user = User.query.filter_by(username='newuser').first()
            assert user is not None
            assert user.check_password('pass123')

    def test_register_duplicate_username(self, app, db, client):
        with app.app_context():
            user = User(username='existing', email='ex@example.com')
            user.set_password('pw')
            db.session.add(user)
            db.session.commit()

        resp = client.post('/auth/register', data={
            'username': 'existing',
            'email': 'other@example.com',
            'password': 'pass123',
            'password_confirm': 'pass123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '用户名已存在' in resp.data.decode('utf-8')

    def test_register_password_mismatch(self, app, db, client):
        resp = client.post('/auth/register', data={
            'username': 'newuser2',
            'email': 'new2@example.com',
            'password': 'pass123',
            'password_confirm': 'different',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '两次密码不一致' in resp.data.decode('utf-8')

    def test_register_missing_fields(self, app, db, client):
        resp = client.post('/auth/register', data={
            'username': '',
            'email': '',
            'password': '',
            'password_confirm': '',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '请填写所有必填项' in resp.data.decode('utf-8')

    def test_register_duplicate_email(self, app, db, client):
        with app.app_context():
            user = User(username='user_a', email='dup@example.com')
            user.set_password('pw')
            db.session.add(user)
            db.session.commit()

        resp = client.post('/auth/register', data={
            'username': 'user_b',
            'email': 'dup@example.com',
            'password': 'pass123',
            'password_confirm': 'pass123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '邮箱已注册' in resp.data.decode('utf-8')


class TestLogin:
    def test_get_login_page(self, client):
        resp = client.get('/auth/login')
        assert resp.status_code == 200

    def test_login_success(self, app, db, client):
        with app.app_context():
            user = User(username='loginuser', email='login@example.com')
            user.set_password('correctpw')
            db.session.add(user)
            db.session.commit()

        resp = client.post('/auth/login', data={
            'username': 'loginuser',
            'password': 'correctpw',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert '/dashboard' in resp.headers.get('Location', '')

    def test_login_wrong_password(self, app, db, client):
        with app.app_context():
            user = User(username='loginuser2', email='login2@example.com')
            user.set_password('correctpw')
            db.session.add(user)
            db.session.commit()

        resp = client.post('/auth/login', data={
            'username': 'loginuser2',
            'password': 'wrongpw',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '用户名或密码错误' in resp.data.decode('utf-8')

    def test_login_nonexistent_user(self, app, db, client):
        resp = client.post('/auth/login', data={
            'username': 'ghost',
            'password': 'anything',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '用户名或密码错误' in resp.data.decode('utf-8')


class TestLogout:
    def test_logout(self, auth_client):
        resp = auth_client.get('/auth/logout', follow_redirects=False)
        assert resp.status_code == 302
        assert '/auth/login' in resp.headers.get('Location', '')


class TestProtectedRoutes:
    def test_dashboard_requires_login(self, client):
        resp = client.get('/dashboard/', follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers.get('Location', '')
        assert '/auth/login' in location or 'login' in location
