# app/views/tasks.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, send_from_directory
import os
from flask_login import login_required, current_user
from ..models import Task, Answer, TaskBlock, Tournament, TeamBlockStart
from ..extensions import db
from datetime import datetime, timezone
from sqlalchemy.orm import joinedload

bp = Blueprint("tasks", __name__)

# ---- routes ----

@bp.route("/")
def index():
    # загружаем турниры с блоками, чтобы не было N+1
    tournaments = Tournament.query.options(joinedload(Tournament.blocks)).order_by(Tournament.id.desc()).all()
    finished_ids = set()  # Теперь не используется, но оставляем для совместимости с шаблоном

    return render_template("index.html", tournaments=tournaments, finished_ids=finished_ids)


@bp.route("/waiting")
@login_required
def waiting():
    """
    Страница ожидания старта турнира или между блоками.
    Если передан next_block_id - показываем страницу ожидания с кнопкой для начала следующего блока.
    """
    tid = request.args.get("tournament_id", type=int)
    next_block_id = request.args.get("next_block_id", type=int)

    if tid:
        tournament = Tournament.query.get(tid)
        if tournament:
            # Инициализируем started_at если еще не установлено
            if not current_user.started_at:
                current_user.started_at = datetime.now(timezone.utc)
                db.session.commit()
            
            # Если передан next_block_id, проверяем его существование и принадлежность
            if next_block_id:
                next_block = TaskBlock.query.get(next_block_id)
                if next_block and next_block.tournament_id == tournament.id:
                    return render_template("waiting.html", tournament=tournament, 
                                         next_block=next_block, server_time=datetime.now(timezone.utc).isoformat())
                else:
                    # Если next_block_id невалиден, убираем его и редиректим без него
                    return redirect(url_for("tasks.waiting", tournament_id=tid))
            
            # Если нет next_block_id, просто отображаем waiting без кнопки старта
            return render_template("waiting.html", tournament=tournament, 
                                 server_time=datetime.now(timezone.utc).isoformat())

    # Если турнир не найден, показываем список турниров
    tournaments = Tournament.query.order_by(Tournament.id.desc()).all()
    return render_template("waiting.html", tournament=None, tournaments=tournaments)

@bp.route("/tournament/<int:tournament_id>")
@login_required
def tournament(tournament_id):
    if not tournament_id:
        return abort(400, description="tournament_id required")

    tournament = Tournament.query.get(tournament_id)

    # нет турнира — возвращаем на waiting
    if not tournament:
        return redirect(url_for("tasks.waiting", tournament_id=tournament_id))

    # Инициализируем started_at для команды, если еще не установлено
    if not current_user.started_at:
        current_user.started_at = datetime.now(timezone.utc)
        db.session.commit()

    blocks = sorted(list(tournament.blocks), key=lambda b: (b.order or 0, b.id))

    # Получаем активный блок
    from ..utils import get_team_active_block
    active_block = get_team_active_block(current_user, tournament)
    
    if active_block:
        # Если есть активный блок, рендерим страницу турнира в обычном режиме
        return render_template(
            "tournament.html",
            tournament=tournament,
            tid=tournament_id,
            active_block=active_block,
            review_mode=False,
        )
    # Если активного блока нет, проверяем неначатые блоки
    pending_block = None
    if blocks:
        for block in blocks:
            block_start = TeamBlockStart.query.filter_by(
                team_id=current_user.id,
                block_id=block.id
            ).first()
            if not block_start:
                pending_block = block
                break

    # Если есть блоки, которые ещё не начинались и турнир не завершён — переходим на waiting
    if pending_block:
        return redirect(url_for("tasks.waiting", tournament_id=tournament_id, next_block_id=pending_block.id))

    # Все блоки начаты/завершены — режим просмотра
    initial_block = blocks[0] if blocks else None
    return render_template(
        "tournament.html",
        tournament=tournament,
        tid=tournament_id,
        active_block=initial_block,
        review_mode=True,
    )

@bp.route("/start_block", methods=["POST"])
@login_required
def start_block():
    """
    Устанавливает время начала блока для команды.
    Вызывается при нажатии кнопки "Начать следующий блок".
    """
    block_id = request.json.get("block_id") if request.is_json else request.form.get("block_id", type=int)
    
    if not block_id:
        return jsonify({"ok": False, "error": "block_id required"}), 400
    
    block = TaskBlock.query.get(block_id)
    if not block:
        return jsonify({"ok": False, "error": "Block not found"}), 404
    
    # Проверяем, что блок относится к турниру команды
    if block.tournament_id != current_user.tournament_id:
        return jsonify({"ok": False, "error": "Block does not belong to team's tournament"}), 403
    
    # Проверяем, не начат ли блок уже
    existing = TeamBlockStart.query.filter_by(
        team_id=current_user.id,
        block_id=block_id
    ).first()
    
    if existing:
        # Блок уже начат
        return jsonify({"ok": True, "already_started": True, "started_at": existing.started_at.isoformat()})
    
    # Устанавливаем время начала блока
    block_start = TeamBlockStart(
        team_id=current_user.id,
        block_id=block_id,
        started_at=datetime.now(timezone.utc)
    )
    db.session.add(block_start)
    db.session.commit()
    
    return jsonify({"ok": True, "started_at": block_start.started_at.isoformat()})

@bp.route('/favicon.ico')
def favicon():
    print("ppupupu", bp.root_path)
    return send_from_directory(os.path.join(bp.root_path, '../static'),
                               'favicon.png', mimetype='image/png')