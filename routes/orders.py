"""
Маршрути управління замовленнями.
"""
import sqlite3, os, random, string
from flask import Blueprint, request, jsonify
from models import get_session, Cafe, MenuItem, Order, OrderItem, Payment
from auth_utils import jwt_required
from models import get_session

orders_bp = Blueprint('orders', __name__, url_prefix='/api/orders')
DB_PATH = os.getenv('DATABASE_PATH', 'eat_good.db')


def _gen_code() -> str:
    """Генерує унікальний буквено-цифровий код підтвердження замовлення."""
    chars = string.ascii_uppercase + string.digits
    conn  = sqlite3.connect(DB_PATH)
    while True:
        code = ''.join(random.choices(chars, k=8))
        if not conn.execute("SELECT 1 FROM orders WHERE confirmation_code=?", (code,)).fetchone():
            conn.close()
            return code


def _order_with_items(order_id, conn=None):
    """Повертає замовлення з позиціями та назвою закладу через SQL JOIN."""
    close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        close = True

    row = conn.execute(
        "SELECT o.*, c.name AS cafe_name FROM orders o JOIN cafes c ON o.cafe_id=c.id WHERE o.id=?",
        (order_id,)
    ).fetchone()
    if not row:
        if close: conn.close()
        return None

    d = dict(row)
    items_rows = conn.execute(
        """SELECT oi.*, m.name AS menu_item_name
           FROM order_items oi JOIN menu_items m ON oi.menu_item_id=m.id
           WHERE oi.order_id=?""", (order_id,)
    ).fetchall()

    d['items'] = [{
        'id':             r['id'],
        'menu_item_id':   r['menu_item_id'],
        'menu_item_name': r['menu_item_name'],
        'quantity':       r['quantity'],
        'price_at_order': float(r['price_at_order']),
        'subtotal':       round(float(r['price_at_order']) * r['quantity'], 2),
    } for r in items_rows]

    if close: conn.close()
    return d


@orders_bp.route('/', methods=['POST'])
@jwt_required
def create_order(current_user):
    
    if current_user['role'] != 'consumer':
        return jsonify({'error': 'Тільки споживачі можуть оформлювати замовлення'}), 403

    data           = request.get_json() or {}
    items_data     = data.get('items', [])
    payment_method = data.get('payment_method', 'cash')

    if not items_data:
        return jsonify({'error': 'Кошик порожній'}), 400
    if payment_method not in ('card', 'online', 'cash'):
        return jsonify({'error': 'Невірний спосіб оплати'}), 400

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        total    = 0.0
        cafe_id  = None
        validated = []

        for entry in items_data:
            mid = entry.get('menu_item_id')
            qty = int(entry.get('quantity', 1))
            if qty < 1:
                conn.close()
                return jsonify({'error': 'Кількість має бути >= 1'}), 400

            item = conn.execute(
                "SELECT * FROM menu_items WHERE id=? AND is_active=1", (mid,)
            ).fetchone()
            if not item:
                conn.close()
                return jsonify({'error': f'Позиція {mid} недоступна або не існує'}), 400

            if cafe_id is None:
                cafe_id = item['cafe_id']
            elif cafe_id != item['cafe_id']:
                conn.close()
                return jsonify({'error': 'Усі позиції мають бути з одного закладу'}), 400

            total += float(item['discount_price']) * qty
            validated.append({'item': dict(item), 'qty': qty})

        code           = _gen_code()
        initial_status = 'created'
        pay_status     = 'initiated'

        cur = conn.execute(
            "INSERT INTO orders (user_id, cafe_id, status, confirmation_code, total_amount) VALUES (?,?,?,?,?)",
            (current_user['id'], cafe_id, initial_status, code, round(total, 2))
        )
        order_id = cur.lastrowid

        for v in validated:
            conn.execute(
                "INSERT INTO order_items (order_id, menu_item_id, quantity, price_at_order) VALUES (?,?,?,?)",
                (order_id, v['item']['id'], v['qty'], v['item']['discount_price'])
            )

        conn.execute(
            "INSERT INTO payments (order_id, payment_method, payment_status) VALUES (?,?,?)",
            (order_id, payment_method, pay_status)
        )
        conn.commit()

        result = _order_with_items(order_id, conn)
        conn.close()
        return jsonify(result), 201

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@orders_bp.route('/my', methods=['GET'])
@jwt_required
def my_orders(current_user):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id FROM orders WHERE user_id=? ORDER BY created_at DESC",
        (current_user['id'],)
    ).fetchall()
    result = [_order_with_items(r['id'], conn) for r in rows]
    conn.close()
    return jsonify([r for r in result if r]), 200


@orders_bp.route('/cafe', methods=['GET'])
@jwt_required
def cafe_orders(current_user):
    if current_user['role'] not in ('cafe', 'admin'):
        return jsonify({'error': 'Недостатньо прав'}), 403

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cafe = conn.execute("SELECT id FROM cafes WHERE owner_id=?", (current_user['id'],)).fetchone()
    if not cafe:
        conn.close()
        return jsonify({'error': 'Заклад не знайдено'}), 404

    status_f = request.args.get('status')
    if status_f:
        rows = conn.execute(
            "SELECT id FROM orders WHERE cafe_id=? AND status=? ORDER BY created_at DESC",
            (cafe['id'], status_f)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM orders WHERE cafe_id=? ORDER BY created_at DESC",
            (cafe['id'],)
        ).fetchall()

    result = [_order_with_items(r['id'], conn) for r in rows]
    conn.close()
    return jsonify([r for r in result if r]), 200


@orders_bp.route('/verify', methods=['POST'])
@jwt_required
def verify_order(current_user):
    
    if current_user['role'] not in ('cafe', 'admin'):
        return jsonify({'error': 'Недостатньо прав'}), 403

    data = request.get_json() or {}
    code = data.get('confirmation_code', '').strip().upper()
    if not code:
        return jsonify({'error': "Код підтвердження обов'язковий"}), 400

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    order = conn.execute(
        "SELECT o.*, c.owner_id FROM orders o JOIN cafes c ON o.cafe_id=c.id WHERE o.confirmation_code=?",
        (code,)
    ).fetchone()

    if not order:
        conn.close()
        return jsonify({'error': 'Невірний код. Замовлення не знайдено'}), 404

    order = dict(order)

    if current_user['role'] != 'admin' and order['owner_id'] != current_user['id']:
        conn.close()
        return jsonify({'error': 'Замовлення не належить вашому закладу'}), 403

    if order['status'] == 'completed':
        conn.close()
        return jsonify({'error': 'Замовлення вже видано'}), 400
    if order['status'] == 'cancelled':
        conn.close()
        return jsonify({'error': 'Замовлення скасовано'}), 400
    if order['status'] == 'created':
        conn.close()
        return jsonify({'error': 'Замовлення ще не підтверджено закладом'}), 400

    conn.execute("UPDATE orders SET status='completed' WHERE id=?", (order['id'],))
    conn.execute("UPDATE payments SET payment_status='successful' WHERE order_id=?", (order['id'],))
    conn.commit()

    result = _order_with_items(order['id'], conn)
    conn.close()
    return jsonify({'message': 'Замовлення видано!', 'order': result}), 200


@orders_bp.route('/<int:order_id>/confirm', methods=['POST'])
@jwt_required
def confirm_order(current_user, order_id):
    """Підтвердження замовлення закладом: paid → confirmed."""
    if current_user['role'] not in ('cafe', 'admin'):
        return jsonify({'error': 'Недостатньо прав'}), 403

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({'error': 'Замовлення не знайдено'}), 404

    order = dict(order)
    if current_user['role'] != 'admin':
        cafe = conn.execute("SELECT id FROM cafes WHERE owner_id=?", (current_user['id'],)).fetchone()
        if not cafe or order['cafe_id'] != cafe['id']:
            conn.close()
            return jsonify({'error': 'Доступ заборонено'}), 403

    if order['status'] not in ('paid', 'confirmed'):
        conn.close()
        return jsonify({'error': 'Замовлення ще не підтверджено закладом'}), 400

    conn.execute("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
    conn.execute("UPDATE payments SET payment_status='successful' WHERE order_id=?", (order_id,))
    conn.commit()
    result = _order_with_items(order_id, conn)
    conn.close()
    return jsonify(result), 200

@orders_bp.route('/<int:order_id>/confirm_payment', methods=['POST'])
@jwt_required
def confirm_payment(current_user, order_id):
    if current_user['role'] not in ('cafe', 'admin'):
        return jsonify({'error': 'Недостатньо прав'}), 403
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({'error': 'Не знайдено'}), 404
    
    if order['status'] != 'created':
        conn.close()
        return jsonify({'error': 'Замовлення вже оброблено'}), 400
    
    conn.execute("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Оплату підтверджено'}), 200

@orders_bp.route('/<int:order_id>/cancel', methods=['POST'])
@jwt_required
def cancel_order(current_user, order_id):
    """Скасування замовлення споживачем або адміністратором."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({'error': 'Замовлення не знайдено'}), 404

    order = dict(order)
    if order['user_id'] != current_user['id'] and current_user['role'] != 'admin':
        conn.close()
        return jsonify({'error': 'Доступ заборонено'}), 403

    if order['status'] in ('completed', 'cancelled'):
        conn.close()
        return jsonify({'error': 'Неможливо скасувати'}), 400

    conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Замовлення скасовано'}), 200
