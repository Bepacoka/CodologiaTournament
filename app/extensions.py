# app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.login_view = "auth.login"  # endpoint для login

db = SQLAlchemy(
    session_options={
        "autoflush": False,
        "expire_on_commit": False,
    }
)

migrate = Migrate()
