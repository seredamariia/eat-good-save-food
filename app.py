import os
from flask import Flask, send_from_directory, jsonify
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'eat-good-dev-secret')

    from models import init_db
    init_db()

    from routes.auth   import auth_bp
    from routes.cafes  import cafes_bp
    from routes.menu   import menu_bp
    from routes.orders import orders_bp
    from routes.admin  import admin_bp

    for bp in (auth_bp, cafes_bp, menu_bp, orders_bp, admin_bp):
        app.register_blueprint(bp)

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        return send_from_directory('templates', 'index.html')

    @app.errorhandler(404)
    def not_found(e): return jsonify({'error': 'Не знайдено'}), 404

    @app.errorhandler(500)
    def server_error(e): return jsonify({'error': 'Помилка сервера'}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    print('🌿 Eat Good Save Food → http://localhost:5001')
    app.run(debug=True, host='0.0.0.0', port=5001)
