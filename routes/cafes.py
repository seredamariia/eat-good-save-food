from flask import Blueprint, request, jsonify
from models import get_session, Cafe
from auth_utils import jwt_required

cafes_bp = Blueprint('cafes', __name__, url_prefix='/api/cafes')


@cafes_bp.route('/', methods=['GET'])
def list_cafes():
    with get_session() as s:
        # Фільтруємо порожні заклади (автоматично створені)
        cafes = [c for c in s.query(Cafe).all() if c.name]
        return jsonify([c.to_dict() for c in cafes]), 200


@cafes_bp.route('/<int:cafe_id>', methods=['GET'])
def get_cafe(cafe_id):
    with get_session() as s:
        c = s.get(Cafe, cafe_id)
        if not c: return jsonify({'error': 'Заклад не знайдено'}), 404
        return jsonify(c.to_dict(include_menu=True)), 200


@cafes_bp.route('/my', methods=['GET'])
@jwt_required
def my_cafe(current_user):
    with get_session() as s:
        c = s.query(Cafe).filter_by(owner_id=current_user['id']).first()
        if not c:
            return jsonify({'error': 'Заклад не знайдено'}), 404
        return jsonify(c.to_dict(include_menu=True)), 200


@cafes_bp.route('/', methods=['POST'])
@jwt_required
def create_cafe(current_user):
    if current_user['role'] not in ('cafe', 'admin'):
        return jsonify({'error': 'Недостатньо прав'}), 403
    data = request.get_json() or {}
    name    = data.get('name', '').strip()
    address = data.get('address', '').strip()
    if not name or not address:
        return jsonify({'error': "Назва та адреса обов'язкові"}), 400
    with get_session() as s:
        c = Cafe(name=name, address=address,
                 latitude=data.get('latitude'), longitude=data.get('longitude'),
                 owner_id=current_user['id'])
        s.add(c); s.commit()
        return jsonify(c.to_dict()), 201


@cafes_bp.route('/<int:cafe_id>', methods=['PUT'])
@jwt_required
def update_cafe(current_user, cafe_id):
    with get_session() as s:
        c = s.get(Cafe, cafe_id)
        if not c: return jsonify({'error': 'Заклад не знайдено'}), 404
        if c.owner_id != current_user['id'] and current_user['role'] != 'admin':
            return jsonify({'error': 'Недостатньо прав'}), 403
        data = request.get_json() or {}
        c.name      = data.get('name',      c.name)
        c.address   = data.get('address',   c.address)
        c.latitude  = data.get('latitude',  c.latitude)
        c.longitude = data.get('longitude', c.longitude)
        s.commit()
        return jsonify(c.to_dict()), 200