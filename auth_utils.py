"""
Утиліти аутентифікації: JWT-токени та декоратор @jwt_required.
Забезпечує захист від несанкціонованого доступу через перевірку JWT-токенів.
"""

import jwt
import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

JWT_SECRET = os.getenv('JWT_SECRET_KEY', 'eat-good-save-food-secret-2024')
DB_PATH    = os.getenv('DATABASE_PATH', 'eat_good.db')


def create_token(user_id: int) -> str:
    """Генерує підписаний JWT-токен для автентифікованого користувача."""
    payload = {
        'sub': str(user_id),
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def decode_token(token: str) -> dict:
    """Декодує та верифікує JWT-токен. Викидає виключення при невалідному токені."""
    return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])


def _get_user_by_id(user_id: int):
    """Пряме звернення до БД для отримання користувача."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    return {
        'id':           d['id'],
        'phone':        d['phone'],
        'role':         d['role'],
        'is_active':    bool(d['is_active']),
        'display_name': d.get('display_name'),
        'created_at':   d.get('created_at', ''),
    }


def jwt_required(f):
    """
    Декоратор для захищених маршрутів.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Токен відсутній'}), 401

        token = auth.split(' ', 1)[1].strip()
        try:
            payload = decode_token(token)
            user_id = int(payload['sub'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Токен прострочений'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'error': f'Невірний токен: {e}'}), 401

        user = _get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'Користувача не знайдено'}), 401
        if not user['is_active']:
            return jsonify({'error': 'Акаунт заблокований'}), 403

        return f(user, *args, **kwargs)

    return decorated
