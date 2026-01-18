# app/config.py

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # ---- Flask ----
    SECRET_KEY = os.getenv("SECRET_KEY", "abracadabra")

    # ---- Database ----
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "postgresql://testuser:testpassword@127.0.0.1:5432/testdb")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---- Security ----
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True   # ОБЯЗАТЕЛЬНО при HTTPS

    # ---- Proxy (nginx) ----
    PREFERRED_URL_SCHEME = "https"

    # ---- JSON / encoding ----
    JSON_AS_ASCII = False
