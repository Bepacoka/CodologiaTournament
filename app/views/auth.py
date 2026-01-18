# app/views/auth.py
from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_user
from ..models import Team, Tournament, db

bp = Blueprint("auth", __name__, url_prefix="/auth")

# Регистрация закомментирована - не в публичном доступе
# @bp.route("/register/<int:tournament_id>", methods=["GET", "POST"])
# def register(tournament_id):
#     # список турниров для селекта (включаем все, но пометим завершённые)
#     tournaments = Tournament.query.order_by(Tournament.id).all()

#     # allow preselect via querystring
#     if not tournament_id:
#         return abort(400)
#     pre_tournament_id = tournament_id

#     if request.method == "POST":
#         team_name = (request.form.get("team_name") or "").strip()
#         member1 = (request.form.get("member1") or "").strip()
#         member2 = (request.form.get("member2") or "").strip()
#         member3 = (request.form.get("member3") or "").strip()
#         tournament_id = request.form.get("tournament_id", type=int)

#         if not team_name:
#             return render_template("register.html",
#                                    tournaments=tournaments,
#                                    tournament=None,
#                                    error="Название команды обязательно")

#         # Если member1 не указан, используем название команды
#         if not member1:
#             member1 = team_name

#         tournament = Tournament.query.get(tournament_id)
#         if not tournament:
#             return render_template("register.html",
#                                    tournaments=tournaments,
#                                    tournament=None,
#                                    error="Выбранный турнир не найден")

#         # Проверяем, что команда с таким именем еще не существует в этом турнире
#         existing_team = Team.query.filter_by(name=team_name, tournament_id=tournament_id).first()
#         if existing_team:
#             return render_template("register.html",
#                                    tournaments=tournaments,
#                                    tournament=tournament,
#                                    error=f"Команда с названием '{team_name}' уже зарегистрирована на этот турнир")

#         # создать команду
#         from datetime import datetime, timezone
#         team = Team(
#             name=team_name,
#             member1=member1,
#             member2=member2 or None,
#             member3=member3 or None,
#             tournament_id=tournament.id,
#             started_at=datetime.now(timezone.utc)
#         )
#         db.session.add(team)
#         db.session.commit()

#         # логиним команду (у Team есть get_id и is_authenticated)
#         login_user(team)

#         # редирект в турнирную страницу (или на турнир/таски)
#         return redirect(url_for("tasks.tournament", tournament_id=tournament.id))

#     # GET
#     tournament = Tournament.query.get(pre_tournament_id) if pre_tournament_id else None
#     return render_template("register.html", tournaments=tournaments, tournament=tournament)

@bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Страница входа для команд.
    Теперь требует ввод пароля и проверяет его.
    """
    if request.method == "POST":
        team_name = (request.form.get("team_name") or "").strip()
        password = (request.form.get("password") or "").strip()

        if not team_name:
            return render_template("login.html", error="Название команды обязательно")
        if not password:
            return render_template("login.html", error="Пароль обязателен")

        # Ищем команду по имени
        team = Team.query.filter_by(name=team_name).first()

        if not team:
            return render_template("login.html", error="Команда с таким названием не найдена")

        # Проверяем пароль
        if not team.check_password(password):
            return render_template("login.html", error="Неверный пароль")

        # Логиним команду
        login_user(team)

        # Редирект на турнир команды
        return redirect(url_for("tasks.tournament", tournament_id=team.tournament_id))

    # GET
    return render_template("login.html")