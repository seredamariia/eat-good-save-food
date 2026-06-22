import re
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import get_session, User, Cafe
from auth_utils import create_token, jwt_required

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _hash(p):
    try:    return generate_password_hash(p, method='pbkdf2:sha256')
    except: return generate_password_hash(p)


@auth_bp.route('/register', methods=['POST'])
def register():
    data     = request.get_json() or {}
    phone    = data.get('phone', '').strip()
    password = data.get('password', '')
    role     = data.get('role', 'consumer')

    if not phone or not password:
        return jsonify({'error': "Телефон та пароль обов'язкові"}), 400
    if not re.match(r'^\+?[\d\s\-]{7,20}$', phone):
        return jsonify({'error': 'Невірний формат номера'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Пароль мінімум 6 символів'}), 400
    if role not in ('consumer', 'cafe'):
        role = 'consumer'

    with get_session() as s:
        if s.query(User).filter_by(phone=phone).first():
            return jsonify({'error': 'Номер вже зареєстрований'}), 409
        u = User(
            phone=phone,
            password_hash=_hash(password),
            role=role
        )

        s.add(u)
        s.flush()

        if role == 'cafe':
            cafe = Cafe(
            owner_id=u.id,
            name='Новий заклад',
            address=''
            )
            s.add(cafe)

        s.commit()
        token = create_token(u.id)
        return jsonify({'token': token, 'user': u.to_dict()}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data     = request.get_json() or {}
    phone    = data.get('phone', '').strip()
    password = data.get('password', '')

    with get_session() as s:
        u = s.query(User).filter_by(phone=phone).first()
        if not u or not check_password_hash(u.password_hash, password):
            return jsonify({'error': 'Невірний телефон або пароль'}), 401
        if not u.is_active:
            return jsonify({'error': 'Акаунт заблокований'}), 403
        token = create_token(u.id)
        return jsonify({'token': token, 'user': u.to_dict()}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required
def me(current_user):
    return jsonify(current_user), 200


@auth_bp.route('/change_password', methods=['PUT'])
@jwt_required
def change_password(current_user):
    data  = request.get_json() or {}
    old_p = data.get('old_password','')
    new_p = data.get('new_password','')
    if not old_p or not new_p:
        return jsonify({'error': 'Заповніть всі поля'}), 400
    if len(new_p) < 6:
        return jsonify({'error': 'Новий пароль мінімум 6 символів'}), 400
    with get_session() as s:
        u = s.query(User).filter_by(id=current_user['id']).first()
        if not u:
            return jsonify({'error': 'Користувача не знайдено'}), 404
        if not check_password_hash(u.password_hash, old_p):
            return jsonify({'error': 'Поточний пароль невірний'}), 400
        s._conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash(new_p), current_user['id'])
        )
        s._conn.commit()
    return jsonify({'message': 'Пароль змінено'}), 200

@auth_bp.route('/update_profile', methods=['PUT'])
@jwt_required
def update_profile(current_user):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    with get_session() as s:
        u = s.query(User).filter_by(id=current_user['id']).first()
        if not u:
            return jsonify({'error': 'Користувача не знайдено'}), 404
        u.display_name = name or None
        u._save(s._conn)
        s._conn.commit()
    return jsonify({'name': u.display_name}), 200
