import sqlite3, os
from flask import Blueprint, request, jsonify
from models import get_session, Cafe, MenuItem
from auth_utils import jwt_required

menu_bp = Blueprint('menu', __name__, url_prefix='/api/menu')
DB_PATH = os.getenv('DATABASE_PATH', 'eat_good.db')


def _items_with_cafe(only_active=True, cafe_id=None):
    """Отримує позиції меню разом з даними закладу через JOIN."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = """SELECT m.*, c.name AS cafe_name, c.address AS cafe_address
             FROM menu_items m JOIN cafes c ON m.cafe_id=c.id"""
    conds, params = [], []
    if only_active:
        conds.append("m.is_active=1")
    if cafe_id:
        conds.append("m.cafe_id=?"); params.append(cafe_id)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        price = float(d['price']) or 1
        disc  = float(d['discount_price'])
        d['discount_percent'] = int((1 - disc / price) * 100) if price else 0
        d['is_active'] = bool(d['is_active'])
        result.append(d)
    return result


@menu_bp.route('/', methods=['GET'])
def list_all():
    return jsonify(_items_with_cafe(only_active=True)), 200


@menu_bp.route('/<int:item_id>', methods=['GET'])
def get_item(item_id):
    with get_session() as s:
        item = s.get(MenuItem, item_id)
        if not item: return jsonify({'error': 'Не знайдено'}), 404
        return jsonify(item.to_dict()), 200


@menu_bp.route('/', methods=['POST'])
@jwt_required
def create_item(current_user):
    if current_user['role'] not in ('cafe', 'admin'):
        return jsonify({'error': 'Недостатньо прав'}), 403
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name: return jsonify({'error': "Назва обов'язкова"}), 400
    try:
        price = float(data['price'])
        disc  = float(data['discount_price'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Невірна ціна'}), 400
    if price <= 0 or disc <= 0:
        return jsonify({'error': 'Ціна має бути > 0'}), 400
    if disc >= price:
        return jsonify({'error': 'Ціна зі знижкою має бути меншою за оригінальну'}), 400

    with get_session() as s:
        if current_user['role'] == 'admin':
            cafe_id = data.get('cafe_id')
            if not cafe_id: return jsonify({'error': 'Вкажіть cafe_id'}), 400
        else:
            cafe = s.query(Cafe).filter_by(owner_id=current_user['id']).first()
            if not cafe: return jsonify({'error': 'Спочатку створіть заклад'}), 400
            cafe_id = cafe.id

        item = MenuItem(cafe_id=cafe_id, name=name, description=data.get('description',''),
                        price=price, discount_price=disc)
        s.add(item); s.commit()
        items = _items_with_cafe(only_active=False, cafe_id=cafe_id)
        created = next((i for i in items if i['id'] == item.id), item.to_dict())
        return jsonify(created), 201


@menu_bp.route('/<int:item_id>', methods=['PUT'])
@jwt_required
def update_item(current_user, item_id):
    with get_session() as s:
        item = s.get(MenuItem, item_id)
        if not item: return jsonify({'error': 'Не знайдено'}), 404
        cafe = s.get(Cafe, item.cafe_id)
        if cafe.owner_id != current_user['id'] and current_user['role'] != 'admin':
            return jsonify({'error': 'Недостатньо прав'}), 403
        d     = request.get_json() or {}
        price = float(d.get('price', item.price))
        disc  = float(d.get('discount_price', item.discount_price))
        if disc >= price:
            return jsonify({'error': 'Ціна зі знижкою має бути меншою за оригінальну'}), 400
        name        = d.get('name', item.name)
        description = d.get('description', item.description)
        is_active   = bool(d['is_active']) if 'is_active' in d else item.is_active
        # Прямий SQL
        s._conn.execute(
            "UPDATE menu_items SET name=?, description=?, price=?, discount_price=?, is_active=? WHERE id=?",
            (name, description, price, disc, int(is_active), item_id)
        )
        s._conn.commit()
        items = _items_with_cafe(only_active=False, cafe_id=item.cafe_id)
        updated = next((i for i in items if i['id'] == item_id), item.to_dict())
        return jsonify(updated), 200


@menu_bp.route('/<int:item_id>', methods=['DELETE'])
@jwt_required
def deactivate_item(current_user, item_id):
    with get_session() as s:
        item = s.get(MenuItem, item_id)
        if not item:
            return jsonify({'error': 'Не знайдено'}), 404
        cafe = s.get(Cafe, item.cafe_id)
        if cafe.owner_id != current_user['id'] and current_user['role'] != 'admin':
            return jsonify({'error': 'Недостатньо прав'}), 403
        # Прямий SQL замість ORM
        s._conn.execute("UPDATE menu_items SET is_active=0 WHERE id=?", (item_id,))
        s._conn.commit()
        return jsonify({'message': 'Деактивовано'}), 200