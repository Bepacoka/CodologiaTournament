from flask import Blueprint, request, abort, redirect, url_for, render_template
from app.extensions import db
from app.models import Answer, Task, Team, Tournament, TeamBlockStart
from datetime import datetime, timezone
from os import getenv

# Все хорошо, но .tournament-row почему-то имеет высоту больше, чем main, можешь поправить?

bp = Blueprint("admin", __name__)

ADMIN_KEY = getenv("ADMIN_KEY")

def check():
    if request.args.get("key") != ADMIN_KEY:
        abort(403)

@bp.route("/__admin/reset_answers")
def reset_answers():
    check()
    Answer.query.delete()
    db.session.commit()
    return "answers cleared"

@bp.route("/__admin/reset_teams")
def reset_teams():
    check()
    Team.query.delete()
    db.session.commit()
    return "teams cleared"

@bp.route("/__admin/reset_team")
def reset_team():
    check()
    team_name = request.args.get("name")
    if not team_name:
        abort(400, "name parameter is required")
    
    # Find the team by name
    team = Team.query.filter_by(name=team_name).first()
    if not team:
        abort(404, f"Team '{team_name}' not found")
    
    # Delete all answers for this team
    Answer.query.filter_by(team_id=team.id).delete()
    
    # Delete all block starts for this team
    TeamBlockStart.query.filter_by(team_id=team.id).delete()
    
    db.session.commit()
    return f"Team '{team_name}' has been reset (answers and block starts removed)"

@bp.route("/__admin/add_team", methods=["GET", "POST"])
def add_team():
    print("ещкере")
    check()

    if request.method == "POST":
        team_name = request.form.get("name") or request.args.get("name")
        password = request.form.get("password") or request.args.get("password")
        tournament_id = request.form.get("tournament_id", type=int) or request.args.get("tournament_id", type=int)
        member1 = request.form.get("member1") or request.args.get("member1") or team_name
        member2 = request.form.get("member2") or request.args.get("member2")
        member3 = request.form.get("member3") or request.args.get("member3")
    else:
        # GET запрос (для обратной совместимости)
        team_name = request.args.get("name")
        password = request.args.get("password")
        tournament_id = request.args.get("tournament_id", type=int)
        member1 = request.args.get("member1")
        member2 = request.args.get("member2")
        member3 = request.args.get("member3")

    if not team_name:
        abort(400, "name required")

    if not password:
        abort(400, "password required")

    if not tournament_id:
        abort(400, "tournament_id required")

    # Проверяем, что турнир существует
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        abort(400, f"tournament with id {tournament_id} not found")

    # Проверяем уникальность имени команды в рамках турнира
    if Team.query.filter_by(name=team_name, tournament_id=tournament_id).first():
        return f"team '{team_name}' already exists for this tournament"

    # Создаем команду с паролем
    team = Team(
        name=team_name,
        member1=member1 or team_name,
        member2=member2 or None,
        member3=member3 or None,
        tournament_id=tournament_id
    )
    team.set_password(password)
    db.session.add(team)
    db.session.commit()

    return f"team '{team_name}' added with password to tournament {tournament_id}"

@bp.route("/__admin/add_task")
def add_task():
    check()

    order = int(request.args.get("order"))
    if not order:
        abort(400, "order required")

    if Task.query.filter_by(order=order).first():
        return f"task №'{order}' already exists"

    text = request.args.get("text")
    if not text:
        abort(400, "text required")
    answer = request.args.get("answer")
    if not answer:
        abort(400, "answer required")
    
    image_url = request.args.get("image_url")
    task = Task(order=order, correct_answer=answer, text=text, image_url=image_url)
    db.session.add(task)
    db.session.commit()

    return f"task №'{order}' added"

@bp.route("/__admin/teams", methods=["GET", "POST"])
def manage_teams():
    """
    Admin interface for managing teams in tournaments
    """
    check()  # This checks for the admin key
    
    from app.models import Tournament, Team
    
    message = None
    message_type = "info"
    
    # Handle form submission
    if request.method == "POST":
        try:
            team_name = request.form.get("name")
            password = request.form.get("password")
            tournament_id = request.form.get("tournament_id", type=int)
            member1 = request.form.get("member1") or team_name
            member2 = request.form.get("member2")
            member3 = request.form.get("member3")
            
            # Validate required fields
            if not all([team_name, password, tournament_id, member1]):
                message = "Все обязательные поля должны быть заполнены"
                message_type = "danger"
            else:
                # Check if team name already exists for this tournament
                if Team.query.filter_by(name=team_name, tournament_id=tournament_id).first():
                    message = f"Команда с именем '{team_name}' уже существует в этом турнире"
                    message_type = "danger"
                else:
                    # Create the team
                    team = Team(
                        name=team_name,
                        tournament_id=tournament_id,
                        member1=member1,
                        member2=member2 if member2 else None,
                        member3=member3 if member3 else None
                    )
                    team.set_password(password)
                    db.session.add(team)
                    db.session.commit()
                    
                    message = f"Команда '{team_name}' успешно добавлена"
                    message_type = "success"
                    
        except Exception as e:
            db.session.rollback()
            message = f"Ошибка при добавлении команды: {str(e)}"
            message_type = "danger"
    
    # Get all tournaments for the dropdown
    tournaments = Tournament.query.order_by(Tournament.name).all()
    
    # Get all teams with their tournament info
    teams = Team.query.join(Tournament).order_by(Tournament.name, Team.name).all()
    
    return render_template(
        "admin/team_management.html",
        tournaments=tournaments,
        teams=teams,
        message=message,
        message_type=message_type
    )
