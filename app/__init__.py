from flask import Flask, jsonify, redirect, render_template, request, url_for

from .config import get_config
from .extensions import csrf, db, limiter, login_manager


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"error": "請先登入"}), 401
        return redirect(url_for("auth.login", next=request.path))

    from .auth.routes import bp as auth_bp
    from .students.routes import bp as students_bp
    from .purchases.routes import bp as purchases_bp
    from .classes.routes import bp as classes_bp
    from .api.routes import bp as api_bp
    from .accounts.routes import bp as accounts_bp
    from .exercises.routes import bp as exercises_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(exercises_bp)

    # API 端點走 JSON,以 401/403 回應取代導向登入頁；CSRF 由呼叫端另行處理(見 README 說明)。
    csrf.exempt(api_bp)

    from . import commands

    commands.register(app)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'",
        )
        return response

    @app.errorhandler(403)
    def forbidden(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "權限不足"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(err):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(err):
        app.logger.exception("Unhandled server error")
        return render_template("errors/500.html"), 500

    @app.route("/")
    def index():
        return redirect(url_for("students.list_students"))

    @app.route("/healthz")
    def healthz():
        """Render 健康檢查用，不需登入、不查資料庫，僅確認應用程式行程存活。"""
        return jsonify({"status": "ok"})

    @app.context_processor
    def inject_logout_form():
        from .forms import DeleteConfirmForm

        return {"logout_form": DeleteConfirmForm()}

    @app.context_processor
    def inject_pending_account_count():
        from flask_login import current_user

        count = 0
        if current_user.is_authenticated and current_user.role in ("admin", "coach"):
            count = User.query.filter_by(status="pending").count()
        return {"pending_account_count": count}

    return app
