import os

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for

from .config import get_config
from .extensions import csrf, db, limiter, login_manager
from .services import category_badge_class, to_taipei


# 登入成功時設為 True，登入後第一個渲染的頁面會彈跳顯示公告並清除。
LOGIN_ANNOUNCEMENTS_KEY = "show_login_announcements"
# 這次登入在 login_sessions 表的 id，頁面瀏覽紀錄靠它連到同一次登入。
LOGIN_SESSION_KEY = "login_session_id"


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    app.jinja_env.filters["category_badge_class"] = category_badge_class
    app.jinja_env.filters["taipei"] = to_taipei

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
    from .announcements.routes import bp as announcements_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(exercises_bp)
    app.register_blueprint(announcements_bp)

    # API 端點走 JSON,以 401/403 回應取代導向登入頁；CSRF 由呼叫端另行處理(見 README 說明)。
    csrf.exempt(api_bp)

    from . import commands

    commands.register(app)

    # 須修改密碼的帳號只能進入修改密碼頁與登出，其餘頁面一律導向修改密碼(API 回 403)。
    _PASSWORD_CHANGE_ALLOWED = {"auth.change_own_password", "auth.logout", "static", "healthz", "finish_page_view"}

    @app.before_request
    def require_password_change():
        from flask_login import current_user

        if not current_user.is_authenticated or not current_user.must_change_password:
            return None
        if request.endpoint in _PASSWORD_CHANGE_ALLOWED:
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "請先修改密碼"}), 403
        return redirect(url_for("auth.change_own_password"))

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers.setdefault(
            "Content-Security-Policy",
            # Font Awesome 圖示(選單)從 cdnjs 載入，樣式表另以 SRI 雜湊鎖定內容
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdnjs.cloudflare.com",
        )
        return response

    @app.template_global()
    def page_view_key():
        """base.html 呼叫：產生這次頁面的紀錄代碼，回應成功送出後才寫入 page_views(見 record_page_view)。"""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return None
        if "page_view_key" not in g:
            from .services import new_page_view_key

            g.page_view_key = new_page_view_key()
        return g.page_view_key

    @app.after_request
    def record_page_view(response):
        """登入使用者成功開啟的頁面記一筆；錯誤頁、導向、API、靜態檔都不記。紀錄失敗不影響頁面。"""
        key = g.pop("page_view_key", None)
        if key is None or request.method != "GET" or response.status_code != 200:
            return response
        if response.mimetype != "text/html":
            return response
        from flask_login import current_user

        from . import services

        if not current_user.is_authenticated:
            return response
        try:
            url = request.full_path.rstrip("?") if request.query_string else request.path
            services.record_page_view(
                current_user, key, url, endpoint=request.endpoint, login_session_id=session.get(LOGIN_SESSION_KEY)
            )
        except Exception:
            db.session.rollback()
            app.logger.exception("記錄頁面瀏覽失敗")
        return response

    @app.route("/page-views/<view_key>/finish", methods=["POST"])
    @csrf.exempt
    @limiter.exempt
    def finish_page_view(view_key):
        """瀏覽器離開/切走頁面時以 sendBeacon 回報載入與停留時間。
        不檢查 CSRF：view_key 是隨機值，只會出現在本人的頁面上，且只能更新自己的紀錄。"""
        from flask_login import current_user

        from . import services

        if not current_user.is_authenticated:
            return "", 401
        data = request.get_json(silent=True, force=True) or {}
        found = services.finish_page_view(
            current_user, view_key, load_ms=data.get("load_ms"), duration_ms=data.get("duration_ms")
        )
        return "", 204 if found else 404

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

    @app.template_global()
    def asset_url(filename):
        """靜態檔網址加上檔案修改時間，檔案一改瀏覽器(特別是手機)就會重新下載，不會沿用舊的快取。"""
        path = os.path.join(app.static_folder, filename)
        version = int(os.path.getmtime(path)) if os.path.exists(path) else 0
        return url_for("static", filename=filename, v=version)

    @app.context_processor
    def inject_logout_form():
        from .forms import DeleteConfirmForm

        return {"logout_form": DeleteConfirmForm()}

    @app.context_processor
    def inject_pending_account_count():
        from flask_login import current_user

        from .services import visible_accounts_query

        count = 0
        if current_user.is_authenticated and current_user.role in ("admin", "coach"):
            count = visible_accounts_query(current_user).filter_by(status="pending").count()
        return {"pending_account_count": count}

    @app.context_processor
    def inject_login_announcements():
        """登入後第一個畫面彈跳顯示上架中的公告(REQ-044)；須先修改密碼時延到改完密碼後才顯示。"""
        from flask_login import current_user

        from .services import list_live_announcements_for, taipei_now

        if (
            not current_user.is_authenticated
            or current_user.must_change_password
            or not session.get(LOGIN_ANNOUNCEMENTS_KEY)
        ):
            return {}
        session.pop(LOGIN_ANNOUNCEMENTS_KEY)
        return {
            "login_announcements": list_live_announcements_for(current_user.role),
            "announcement_today": taipei_now().date().isoformat(),
        }

    return app
