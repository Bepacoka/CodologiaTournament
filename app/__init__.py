# app/__init__.py
from flask import Flask, url_for
from .extensions import db, migrate, login_manager
from .config import Config

# Импортируем все модели **здесь**, чтобы Alembic их видел
from .models import Team, Task, Answer, TeamBlockStart

def create_app():
    print("create_app() called")
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    @login_manager.user_loader
    def load_user(user_id):
        # user_id хранится как str — приводим к int
        try:
            return Team.query.get(int(user_id))
        except Exception:
            return None

    def tournament_state_label(state):
        labels = {
            "draft": "Черновик",
            "waiting": "Ожидание",
            "running": "Идёт",
            "finished": "Завершён",
        }
        if not state:
            return "—"
        return labels.get(state.value, state.value)

    def format_dt(dt):
        if not dt:
            return "—"
        return dt.strftime("%d.%m.%Y %H:%M")

    app.jinja_env.filters["dt"] = format_dt
    app.jinja_env.filters["tstate"] = tournament_state_label


    from .views.auth import bp as auth_bp
    from .views.tasks import bp as tasks_bp
    from .views.dashboard import bp as dashboard_bp
    from .views.admin import bp as admin_bp
    from .views.api import bp as api_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(auth_bp)

    return app
