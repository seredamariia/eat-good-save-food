import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv('DATABASE_PATH', 'eat_good.db')

class _Session:
    """Легковагова обгортка над sqlite3, що реалізує інтерфейс SQLAlchemy Session."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def query(self, model):           return _Query(self._conn, model)
    def get(self, model, pk):         return model._get(self._conn, pk)
    def add(self, obj):               obj._pending_session = self._conn
    def add_all(self, objs):          [self.add(o) for o in objs]

    def flush(self):
        for obj in _pending_objects:
            obj._save(self._conn)
        _pending_objects.clear()

    def commit(self):
        self.flush()
        self._conn.commit()

    def refresh(self, obj):
        obj._reload(self._conn)

    def count(self):
        pass  # used via query().count()

    def __enter__(self):  return self
    def __exit__(self, *a): self._conn.close()
    def close(self):        self._conn.close()


_pending_objects = []


class _Query:
    def __init__(self, conn, model):
        self._conn  = conn
        self._model = model
        self._wheres = []
        self._params  = []
        self._order   = None
        self._lim     = None

    def filter_by(self, **kwargs):
        for k, v in kwargs.items():
            self._wheres.append(f"{k}=?")
            self._params.append(v)
        return self

    def filter(self, expr):
        # Підтримка виразів типу Model.field == value
        self._wheres.append(expr._sql)
        self._params.append(expr._val)
        return self

    def order_by(self, expr):
        self._order = expr._sql if hasattr(expr, '_sql') else str(expr)
        return self

    def all(self):
        sql = f"SELECT * FROM {self._model.__tablename__}"
        if self._wheres:
            sql += " WHERE " + " AND ".join(self._wheres)
        if self._order:
            sql += f" ORDER BY {self._order}"
        rows = self._conn.execute(sql, self._params).fetchall()
        return [self._model._from_row(self._conn, r) for r in rows]

    def first(self):
        res = self.all()
        return res[0] if res else None

    def count(self):
        sql = f"SELECT COUNT(*) FROM {self._model.__tablename__}"
        if self._wheres:
            sql += " WHERE " + " AND ".join(self._wheres)
        return self._conn.execute(sql, self._params).fetchone()[0]


class _Expr:
    def __init__(self, sql, val):
        self._sql = sql
        self._val = val


# ─── Base Model ───────────────────────────────────────────────────────────────
class _Model:
    @classmethod
    def _get(cls, conn, pk):
        row = conn.execute(f"SELECT * FROM {cls.__tablename__} WHERE id=?", (pk,)).fetchone()
        return cls._from_row(conn, row) if row else None

    def _save(self, conn):
        raise NotImplementedError

    def _reload(self, conn):
        row = conn.execute(f"SELECT * FROM {self.__class__.__tablename__} WHERE id=?", (self.id,)).fetchone()
        if row:
            self._load(dict(row))

    def _load(self, d): pass

    @property
    def _pending_session(self):
        return None

    @_pending_session.setter
    def _pending_session(self, conn):
        self._conn = conn
        _pending_objects.append(self)


# ─── МОДЕЛЬ: users ────────────────────────────────────────────────────────────
class User(_Model):
    __tablename__ = 'users'

    def __init__(self, phone='', password_hash='', role='consumer', is_active=True):
        self.id            = None
        self.phone         = phone
        self.password_hash = password_hash
        self.role          = role
        self.is_active     = bool(is_active)
        self.display_name  = None
        self.created_at    = datetime.utcnow().isoformat()
        self._conn         = None

    def _load(self, d):
        self.id            = d['id']
        self.phone         = d['phone']
        self.password_hash = d['password_hash']
        self.role          = d['role']
        self.is_active     = bool(d['is_active'])
        self.display_name  = d.get('display_name')
        self.created_at    = d.get('created_at', '')

    @classmethod
    def _from_row(cls, conn, row):
        o = cls.__new__(cls)
        o._conn = conn
        o._load(dict(row))
        return o

    def _save(self, conn):
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO users (phone, password_hash, role, is_active, display_name) VALUES (?,?,?,?,?)",
                (self.phone, self.password_hash, self.role, int(self.is_active), self.display_name)
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE users SET phone=?, password_hash=?, role=?, is_active=?, display_name=? WHERE id=?",
                (self.phone, self.password_hash, self.role, int(self.is_active), self.display_name, self.id)
            )

    def to_dict(self):
        return {
            'id':           self.id,
            'phone':        self.phone,
            'role':         self.role,
            'is_active':    self.is_active,
            'display_name': self.display_name,
            'created_at':   self.created_at,
        }


# ─── МОДЕЛЬ: cafes ────────────────────────────────────────────────────────────
class Cafe(_Model):
    __tablename__ = 'cafes'

    def __init__(self, name='', address='', latitude=None, longitude=None, owner_id=None):
        self.id         = None
        self.name       = name
        self.address    = address
        self.latitude   = latitude
        self.longitude  = longitude
        self.owner_id   = owner_id
        self.created_at = datetime.utcnow().isoformat()
        self._conn      = None

    def _load(self, d):
        self.id         = d['id']
        self.name       = d['name']
        self.address    = d['address']
        self.latitude   = d.get('latitude')
        self.longitude  = d.get('longitude')
        self.owner_id   = d['owner_id']
        self.created_at = d.get('created_at', '')

    @classmethod
    def _from_row(cls, conn, row):
        o = cls.__new__(cls)
        o._conn = conn
        o._load(dict(row))
        return o

    def _save(self, conn):
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO cafes (name, address, latitude, longitude, owner_id) VALUES (?,?,?,?,?)",
                (self.name, self.address, self.latitude, self.longitude, self.owner_id)
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE cafes SET name=?, address=?, latitude=?, longitude=? WHERE id=?",
                (self.name, self.address, self.latitude, self.longitude, self.id)
            )

    def get_menu_items(self, conn=None, only_active=False):
        c = conn or self._conn
        sql = "SELECT * FROM menu_items WHERE cafe_id=?"
        if only_active:
            sql += " AND is_active=1"
        rows = c.execute(sql, (self.id,)).fetchall()
        return [MenuItem._from_row(c, r) for r in rows]

    def to_dict(self, include_menu=False, conn=None):
        d = {
            'id':         self.id,
            'name':       self.name,
            'address':    self.address,
            'latitude':   self.latitude,
            'longitude':  self.longitude,
            'owner_id':   self.owner_id,
            'created_at': self.created_at,
        }
        if include_menu:
            c = conn or self._conn
            d['menu_items'] = [i.to_dict() for i in self.get_menu_items(c)]
        return d


# ─── МОДЕЛЬ: menu_items ───────────────────────────────────────────────────────
class MenuItem(_Model):
    __tablename__ = 'menu_items'

    def __init__(self, cafe_id=None, name='', description='', price=0.0, discount_price=0.0, is_active=True):
        self.id             = None
        self.cafe_id        = cafe_id
        self.name           = name
        self.description    = description or ''
        self.price          = price
        self.discount_price = discount_price
        self.is_active      = bool(is_active)
        self._conn          = None
        self._cafe_name     = None
        self._cafe_address  = None

    def _load(self, d):
        self.id             = d['id']
        self.cafe_id        = d['cafe_id']
        self.name           = d['name']
        self.description    = d.get('description') or ''
        self.price          = float(d['price'])
        self.discount_price = float(d['discount_price'])
        self.is_active      = bool(d['is_active'])
        self._cafe_name     = d.get('cafe_name')
        self._cafe_address  = d.get('cafe_address')

    @classmethod
    def _from_row(cls, conn, row):
        o = cls.__new__(cls)
        o._conn = conn
        o._load(dict(row))
        return o

    def _save(self, conn):
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO menu_items (cafe_id, name, description, price, discount_price, is_active) VALUES (?,?,?,?,?,?)",
                (self.cafe_id, self.name, self.description, self.price, self.discount_price, int(self.is_active))
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE menu_items SET name=?, description=?, price=?, discount_price=?, is_active=? WHERE id=?",
                (self.name, self.description, self.price, self.discount_price, int(self.is_active), self.id)
            )

    @property
    def discount_percent(self):
        if self.price and self.price > 0:
            return int((1 - self.discount_price / self.price) * 100)
        return 0

    def to_dict(self):
        return {
            'id':               self.id,
            'cafe_id':          self.cafe_id,
            'cafe_name':        self._cafe_name,
            'cafe_address':     self._cafe_address,
            'name':             self.name,
            'description':      self.description,
            'price':            self.price,
            'discount_price':   self.discount_price,
            'is_active':        self.is_active,
            'discount_percent': self.discount_percent,
        }


# ─── МОДЕЛЬ: orders ───────────────────────────────────────────────────────────
class Order(_Model):
    """Статуси: created → paid → confirmed → completed | cancelled"""
    __tablename__ = 'orders'

    def __init__(self, user_id=None, cafe_id=None, status='created',
                 confirmation_code=None, total_amount=0.0):
        self.id                = None
        self.user_id           = user_id
        self.cafe_id           = cafe_id
        self.status            = status
        self.confirmation_code = confirmation_code
        self.total_amount      = total_amount
        self.created_at        = datetime.utcnow().isoformat()
        self._conn             = None
        self._cafe_name        = None
        self._items            = []

    def _load(self, d):
        self.id                = d['id']
        self.user_id           = d['user_id']
        self.cafe_id           = d['cafe_id']
        self.status            = d['status']
        self.confirmation_code = d.get('confirmation_code')
        self.total_amount      = float(d['total_amount'])
        self.created_at        = d.get('created_at', '')
        self._cafe_name        = d.get('cafe_name')
        self._items            = []

    @classmethod
    def _from_row(cls, conn, row):
        o = cls.__new__(cls)
        o._conn = conn
        o._load(dict(row))
        return o

    def _save(self, conn):
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO orders (user_id, cafe_id, status, confirmation_code, total_amount) VALUES (?,?,?,?,?)",
                (self.user_id, self.cafe_id, self.status, self.confirmation_code, round(self.total_amount, 2))
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE orders SET status=? WHERE id=?",
                (self.status, self.id)
            )

    def get_items(self, conn=None):
        c = conn or self._conn
        rows = c.execute(
            """SELECT oi.*, m.name AS menu_item_name
               FROM order_items oi
               JOIN menu_items m ON oi.menu_item_id=m.id
               WHERE oi.order_id=?""", (self.id,)
        ).fetchall()
        return [OrderItem._from_row(c, r) for r in rows]

    def get_cafe_name(self, conn=None):
        c = conn or self._conn
        if self._cafe_name:
            return self._cafe_name
        row = c.execute("SELECT name FROM cafes WHERE id=?", (self.cafe_id,)).fetchone()
        return row['name'] if row else None

    def to_dict(self, conn=None):
        c = conn or self._conn
        items = self.get_items(c)
        return {
            'id':                self.id,
            'user_id':           self.user_id,
            'cafe_id':           self.cafe_id,
            'cafe_name':         self.get_cafe_name(c),
            'status':            self.status,
            'confirmation_code': self.confirmation_code,
            'total_amount':      self.total_amount,
            'created_at':        self.created_at,
            'items':             [i.to_dict() for i in items],
        }


# ─── МОДЕЛЬ: order_items ──────────────────────────────────────────────────────
class OrderItem(_Model):
    __tablename__ = 'order_items'

    def __init__(self, order_id=None, menu_item_id=None, quantity=1, price_at_order=0.0):
        self.id             = None
        self.order_id       = order_id
        self.menu_item_id   = menu_item_id
        self.quantity       = quantity
        self.price_at_order = price_at_order
        self._conn          = None
        self._menu_item_name = None

    def _load(self, d):
        self.id               = d['id']
        self.order_id         = d['order_id']
        self.menu_item_id     = d['menu_item_id']
        self.quantity         = d['quantity']
        self.price_at_order   = float(d['price_at_order'])
        self._menu_item_name  = d.get('menu_item_name')

    @classmethod
    def _from_row(cls, conn, row):
        o = cls.__new__(cls)
        o._conn = conn
        o._load(dict(row))
        return o

    def _save(self, conn):
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO order_items (order_id, menu_item_id, quantity, price_at_order) VALUES (?,?,?,?)",
                (self.order_id, self.menu_item_id, self.quantity, self.price_at_order)
            )
            self.id = cur.lastrowid

    def to_dict(self):
        return {
            'id':              self.id,
            'menu_item_id':    self.menu_item_id,
            'menu_item_name':  self._menu_item_name,
            'quantity':        self.quantity,
            'price_at_order':  self.price_at_order,
            'subtotal':        round(self.price_at_order * self.quantity, 2),
        }


# ─── МОДЕЛЬ: payments ─────────────────────────────────────────────────────────
class Payment(_Model):
    __tablename__ = 'payments'

    def __init__(self, order_id=None, payment_method='cash', payment_status='initiated', transaction_ref=None):
        self.id              = None
        self.order_id        = order_id
        self.payment_method  = payment_method
        self.payment_status  = payment_status
        self.transaction_ref = transaction_ref
        self._conn           = None

    def _load(self, d):
        self.id              = d['id']
        self.order_id        = d['order_id']
        self.payment_method  = d['payment_method']
        self.payment_status  = d['payment_status']
        self.transaction_ref = d.get('transaction_ref')

    @classmethod
    def _from_row(cls, conn, row):
        o = cls.__new__(cls)
        o._conn = conn
        o._load(dict(row))
        return o

    def _save(self, conn):
        if self.id is None:
            cur = conn.execute(
                "INSERT INTO payments (order_id, payment_method, payment_status, transaction_ref) VALUES (?,?,?,?)",
                (self.order_id, self.payment_method, self.payment_status, self.transaction_ref)
            )
            self.id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE payments SET payment_status=? WHERE order_id=?",
                (self.payment_status, self.order_id)
            )


# ─── SESSION FACTORY ──────────────────────────────────────────────────────────
def get_session() -> _Session:
    """Повертає нову сесію для взаємодії з базою даних (аналог SQLAlchemy Session)."""
    return _Session(DB_PATH)


# ─── ІНІЦІАЛІЗАЦІЯ БД ─────────────────────────────────────────────────────────
def init_db():
    """Створює всі таблиці та наповнює демо-даними при першому запуску."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone VARCHAR(20) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'consumer',
            is_active INTEGER NOT NULL DEFAULT 1,
            display_name VARCHAR(100) DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cafes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200) NOT NULL,
            address VARCHAR(500) NOT NULL,
            latitude REAL,
            longitude REAL,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cafe_id INTEGER NOT NULL REFERENCES cafes(id),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            discount_price REAL NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            cafe_id INTEGER NOT NULL REFERENCES cafes(id),
            status VARCHAR(20) NOT NULL DEFAULT 'created',
            confirmation_code VARCHAR(20) UNIQUE,
            total_amount REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
            quantity INTEGER NOT NULL DEFAULT 1,
            price_at_order REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER UNIQUE NOT NULL REFERENCES orders(id),
            payment_method VARCHAR(20) NOT NULL,
            payment_status VARCHAR(20) NOT NULL DEFAULT 'initiated',
            transaction_ref VARCHAR(200)
        );
    """)
    conn.commit()
    conn.close()
    _seed_demo_data()


def _hash(password: str) -> str:
    from werkzeug.security import generate_password_hash
    try:
        return generate_password_hash(password, method='pbkdf2:sha256')
    except Exception:
        return generate_password_hash(password)


def _seed_demo_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    # Тестові акаунти
    conn.execute("INSERT INTO users (phone, password_hash, role) VALUES (?,?,?)",
                 ('+380000000000', _hash('admin123'), 'admin'))
    conn.execute("INSERT INTO users (phone, password_hash, role) VALUES (?,?,?)",
                 ('+380111111111', _hash('cafe123'), 'cafe'))
    conn.execute("INSERT INTO users (phone, password_hash, role) VALUES (?,?,?)",
                 ('+380222222222', _hash('user123'), 'consumer'))

    owner_id = conn.execute("SELECT id FROM users WHERE phone=?", ('+380111111111',)).fetchone()['id']

    # Заклади — Київ (відповідно до вимог)
    conn.execute("INSERT INTO cafes (name, address, latitude, longitude, owner_id) VALUES (?,?,?,?,?)",
                 ("Кав'ярня «Зернятко»", 'вул. Хрещатик, 15, Київ', 50.4501, 30.5234, owner_id))
    conn.execute("INSERT INTO cafes (name, address, latitude, longitude, owner_id) VALUES (?,?,?,?,?)",
                 ("Піцерія «Bella Italia»", 'вул. Велика Васильківська, 72, Київ', 50.4390, 30.5220, owner_id))

    cafe1 = conn.execute("SELECT id FROM cafes WHERE name LIKE '%Зернятко%'").fetchone()['id']
    cafe2 = conn.execute("SELECT id FROM cafes WHERE name LIKE '%Bella%'").fetchone()['id']

    items = [
        (cafe1, 'Круасан з мигдалем',        'Свіжий круасан з мигдальним кремом',     85,  42),
        (cafe1, 'Американо великий',          'Подвійний еспресо з водою',              75,  35),
        (cafe1, 'Сирник з ягодами',           'Домашній сирник, лісові ягоди, сметана', 110, 55),
        (cafe1, 'Сандвіч з лососем',          'Багет, крем-сир, лосось, каперси',       165, 80),
        (cafe2, 'Піца «Маргарита» (шматок)',  'Томат, моцарела, базилік',               95,  45),
        (cafe2, 'Тірамісу',                   'Класичний італійський десерт',            130, 60),
    ]
    conn.executemany(
        "INSERT INTO menu_items (cafe_id, name, description, price, discount_price) VALUES (?,?,?,?,?)",
        items
    )
    conn.commit()
    conn.close()
    print('✅ Demo data seeded! (Київ)')
