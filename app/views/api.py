# app/views/api.py
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from ..models import Team, Answer, Tournament, TaskBlock, Task, TaskExample, db, TeamBlockStart
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from ..utils import (
    get_team_active_block,
    get_team_block_time_left,
    get_team_block_end_time,
    get_team_block_start_time,
)
from sqlalchemy.orm import joinedload

bp = Blueprint("api", __name__, url_prefix="/api")

@bp.route("/tournaments", methods=["GET"])
def api_tournaments():
    tournaments = Tournament.query.options(joinedload(Tournament.blocks)).order_by(Tournament.id.desc()).all()

    out = []
    for t in tournaments:
        out.append({
            "id": t.id,
            "name": t.name,
        })
    return jsonify({"tournaments": out})


@bp.route("/tournament/<tid>", methods=["GET"])
def get_tournament(tid):
    if not tid:
        return jsonify({"error": "tournament id required (use ?id=NN)"}), 400

    tournament = Tournament.query.get(tid)
    if not tournament:
        return jsonify({"error": "No tournament found with id {}".format(tid)}), 404

    now = datetime.now(timezone.utc)
    
    # Инициализируем started_at для команды, если еще не установлено
    team = current_user
    if not team.started_at:
        team.started_at = now
        db.session.commit()

    # Определяем активный блок для команды
    active_block = get_team_active_block(team, tournament)
    active_block_obj = None
    state = "waiting"
    
    if active_block:
        block_start = get_team_block_start_time(team, active_block)
        block_end = get_team_block_end_time(team, active_block)
        if block_start and not block_end:
            time_left = get_team_block_time_left(team, active_block)
            active_block_obj = {
                "id": active_block.id,
                "name": active_block.name,
                "order": active_block.order,
                "max_duration": active_block.max_duration,
                "image_url": active_block.image_url,
                "time_left": time_left,
            }
            state = "running"
        else:
            # блок еще не начат (pending)
            state = "waiting"

    blocks_sorted = sorted(list(tournament.blocks), key=lambda b: b.order)
    block_timings = []
    for block in blocks_sorted:
        start_ts = get_team_block_start_time(team, block)
        end_ts = get_team_block_end_time(team, block)
        block_timings.append((block, start_ts, end_ts))

    if not active_block:
        any_started = any(start_ts is not None for (_, start_ts, _) in block_timings)
        all_finished = all((start_ts is not None and end_ts is not None) for (_, start_ts, end_ts) in block_timings)
        if any_started and all_finished:
            state = "finished"
        else:
            state = "waiting"

    blocks_payload = []
    for block, block_start, block_end in block_timings:
        start_offset = None
        if block_start and team.started_at:
            start_offset = int((block_start - team.started_at).total_seconds())
        blocks_payload.append({
            "id": block.id,
            "name": block.name,
            "order": block.order,
            "max_duration": block.max_duration,
            "started_at": block_start.isoformat() if block_start else None,
            "finished_at": block_end.isoformat() if block_end else None,
            "start_offset": start_offset,
        })

    response = {
        "id": tournament.id,
        "name": tournament.name,
        "group": getattr(tournament, "group", None),
        "server_time": now.isoformat(),
        "started_at": team.started_at.isoformat() if team.started_at else None,
        "state": state,
        "active_block": active_block_obj,
        "blocks": blocks_payload,
    }
    return jsonify(response)


@bp.route("/block/<int:block_id>", methods=["GET"])
@login_required
def get_block(block_id):
    block = TaskBlock.query.get(block_id)
    if not block:
        return jsonify({"error": "Block not found"}), 404

    now = datetime.now(timezone.utc)
    team = current_user
    
    # Инициализируем started_at для команды, если еще не установлено
    if not team.started_at:
        team.started_at = now
        db.session.commit()
    
    from ..utils import get_team_block_start_time, get_team_block_end_time
    block_start = get_team_block_start_time(team, block)
    block_end = get_team_block_end_time(team, block)
    
    is_active = block_start is not None and block_end is None
    is_finished = block_end is not None
    
    time_left = get_team_block_time_left(team, block)

    tasks_data = []
    # Задачи доступны если блок активен или закончен
    if is_active or is_finished:
        for task in block.tasks:
            # points: если в БД None — вернуть 0 (или любое другое безопасное значение)
            pts = task.points if (task.points is not None) else 0

            # статус для текущей команды (best-effort; если неавторизован — none)
            status = "none"
            try:
                if getattr(current_user, "is_authenticated", False):
                    # берем все ответы этой команды по задаче (включая ответы по примерам)
                    if task.type == "examples":
                        # Для задач с примерами проверяем все примеры
                        examples = task.examples
                        answers = Answer.query.filter_by(team_id=current_user.id, task_id=task.id).all()
                        if not answers or len(answers) == 0:
                            status = "none"
                        else:
                            # Проверяем все ли примеры отвечены
                            answered_examples = set(a.example_id for a in answers if a.example_id is not None)
                            total_examples = len(examples)
                            if len(answered_examples) < total_examples:
                                status = "none"
                            else:
                                # Считаем правильные ответы
                                correct_count = sum(1 for a in answers if a.is_correct)
                                if correct_count == total_examples:
                                    status = "right"
                                elif correct_count > 0:
                                    status = "partial"
                                else:
                                    status = "wrong"
                    else:
                        # Для обычных задач
                        answers = Answer.query.filter_by(team_id=current_user.id, task_id=task.id, example_id=None).all()
                        if not answers:
                            status = "none"
                        else:
                            answer = answers[0]
                            status = "right" if answer.is_correct else "wrong"
            except Exception:
                status = "none"

            tasks_data.append({
                "id": task.id,
                "title": task.title,
                "points": pts,
                "order": task.order,
                "type": getattr(task, "type", "single"),
                "status": status
            })

    response = {
        "id": block.id,
        "name": block.name,
        "order": block.order,
        "max_duration": block.max_duration,
        "image_url": block.image_url,
        "is_active": is_active,
        "is_finished": is_finished,
        "time_left": time_left,
        "tasks": tasks_data
    }
    return jsonify(response)



@bp.route("/task/<int:task_id>", methods=["GET"])
@login_required
def api_get_task(task_id):
    task = Task.query.get_or_404(task_id)

    # существующий ответ на обычную задачу (example_id IS NULL)
    existing = Answer.query.filter_by(
        team_id=current_user.id,
        task_id=task.id,
        example_id=None
    ).first()

    data = {
        "id": task.id,
        "title": task.title,
        "text": task.text,
        "type": task.type or "single",
        "image_url": task.image_url,
        "points": task.points,
        "order": task.order,
        "existing_answer": None,
        "examples": []
    }

    if existing:
        data["existing_answer"] = {
            "answer_text": existing.answer_text,
            "is_correct": existing.is_correct,
            "points": getattr(existing, "points", None),
            "submitted_at": existing.submitted_at.isoformat() if existing.submitted_at else None
        }

    # для задач типа "examples" отдаём массив примеров и (если есть) saved answer для каждого
    examples = TaskExample.query.filter_by(task_id=task.id).order_by(TaskExample.id).all()
    for ex in examples:
        ea = Answer.query.filter_by(
            team_id=current_user.id,
            task_id=task.id,
            example_id=ex.id
        ).first()
        data["examples"].append({
            "id": ex.id,
            "text": ex.text,
            "points": getattr(ex, "points", None),
            "existing_answer": {
                "answer_text": ea.answer_text,
                "is_correct": ea.is_correct,
                "points": getattr(ea, "points", None),
                "submitted_at": ea.submitted_at.isoformat() if ea.submitted_at else None
            } if ea else None
        })

    return jsonify(data)



@bp.route("/task/<int:task_id>", methods=["POST"])
@login_required
def api_post_task(task_id):
    task = Task.query.get_or_404(task_id)

    data = None
    if request.is_json:
        data = request.get_json()
    else:
        if "answer" in request.form:
            data = {"answer": request.form["answer"]}

    if not data:
        return jsonify({"ok": False, "error": "Answer required"}), 400

    # --- обычная задача ---
    if "answer" in data:
        existing = Answer.query.filter_by(
            team_id=current_user.id,
            task_id=task.id,
            example_id=None
        ).first()

        ans_text = str(data["answer"])
        is_correct = (ans_text.strip() == (task.correct_answer or "").strip())

        if existing:
            existing.answer_text = ans_text
            existing.is_correct = is_correct
            existing.points = (task.points if is_correct else 0)
            answer = existing
        else:
            answer = Answer(
                team_id=current_user.id,
                task_id=task.id,
                example_id=None,
                answer_text=ans_text,
                is_correct=is_correct,
                points=(task.points if is_correct else 0)
            )
            db.session.add(answer)
        db.session.commit()
        
        # Проверяем, завершен ли блок после сохранения ответа
        response_data = {"ok": True, "is_correct": is_correct, "answer_text": ans_text}
        block = task.block
        if block:
            block_end_time = get_team_block_end_time(current_user, block)
            if block_end_time is not None:
                # Блок завершен, проверяем следующий блок
                response_data["block_completed"] = True
                tournament = Tournament.query.get(block.tournament_id)
                next_block = get_team_active_block(current_user, tournament)
                if next_block and next_block.id != block.id:
                    # Есть следующий блок
                    response_data["next_block"] = {
                        "id": next_block.id,
                        "name": next_block.name,
                        "order": next_block.order
                    }
                # Если next_block нет или он равен текущему - это последний блок, next_block не добавляем
        
        return jsonify(response_data)

    # --- задача с примерами ---
    elif "answers" in data:
        answers = data["answers"]
        if not isinstance(answers, list):
            return jsonify({"ok": False, "error": "Answers must be a list"}), 400

        results = []
        for ans in answers:
            ex_id = ans.get("example_id")
            ans_text = str(ans.get("answer", ""))

            if ex_id is None:
                results.append({"example_id": None, "error": "example_id required"})
                continue

            # защитная проверка — существует ли пример
            example = TaskExample.query.get(ex_id)
            if not example or example.task_id != task.id:
                results.append({"example_id": ex_id, "error": "Example not found"})
                continue

            # уже отправляли ли ответ на этот пример?
            existing = Answer.query.filter_by(
                team_id=current_user.id,
                task_id=task.id,
                example_id=ex_id
            ).first()

            is_correct = (ans_text.strip() == (example.correct_answer or "").strip())
            points = getattr(example, "points", None)
            if points is None:
                points = 0
            awarded = points if is_correct else 0

            if existing:
                existing.answer_text = ans_text
                existing.is_correct = is_correct
                existing.points = awarded
            else:
                answer_obj = Answer(
                    team_id=current_user.id,
                    task_id=task.id,
                    example_id=ex_id,
                    answer_text=ans_text,
                    is_correct=is_correct,
                    points=awarded
                )
                db.session.add(answer_obj)

            results.append({"example_id": ex_id, "is_correct": is_correct, "points": awarded})

        db.session.commit()
        
        # Проверяем, завершен ли блок после сохранения ответов
        response_data = {"ok": True, "results": results}
        block = task.block
        if block:
            block_end_time = get_team_block_end_time(current_user, block)
            if block_end_time is not None:
                # Блок завершен, проверяем следующий блок
                response_data["block_completed"] = True
                tournament = Tournament.query.get(block.tournament_id)
                next_block = get_team_active_block(current_user, tournament)
                if next_block and next_block.id != block.id:
                    # Есть следующий блок
                    response_data["next_block"] = {
                        "id": next_block.id,
                        "name": next_block.name,
                        "order": next_block.order
                    }
                # Если next_block нет или он равен текущему - это последний блок, next_block не добавляем
        
        return jsonify(response_data)

    else:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

# app/api.py (добавьте в Blueprint bp)
from collections import defaultdict

@bp.route("/dashboard/<int:tournament_id>", methods=["GET"])
def api_dashboard(tournament_id):
    if not tournament_id:
        return jsonify({"error": "tournament_id required"}), 400

    tournament = Tournament.query.get_or_404(tournament_id)
    # подготовим структуры задач/примеров для быстрых lookups
    all_tasks = Task.query.all()
    task_map = {t.id: t for t in all_tasks}

    all_examples = TaskExample.query.all()
    example_map = {ex.id: ex for ex in all_examples}

    # блоки с их задачами (в порядке)
    blocks = []
    for b in tournament.blocks:
        tasks = [
            {"id": t.id, "order": t.order, "title": t.title}
            for t in sorted(b.tasks, key=lambda x: (x.order or 0, x.id))
        ]
        blocks.append({"id": b.id, "name": b.name, "tasks": tasks})

    teams = Team.query.filter_by(tournament_id=tournament.id).order_by(Team.name).all()

    teams_out = []
    for team in teams:
        # все ответы этой команды
        answers = Answer.query.filter_by(team_id=team.id).all()

        per_task = defaultdict(int)   # task_id -> points
        # аккумулируем очки по каждому ответу
        for a in answers:
            tid = a.task_id
            # 1) если в Answer явно есть поле points — используем его
            pts = getattr(a, "points", None)
            if pts is not None:
                try:
                    pts = int(pts)
                except Exception:
                    pts = 0
                per_task[tid] += pts
                continue

            # 2) иначе вычислим из is_correct и дефолтных баллов:
            if a.example_id is None:
                # обычная задача — используем task.points если is_correct
                task = task_map.get(tid)
                task_pts = getattr(task, "points", None) or 0
                per_task[tid] += (task_pts if a.is_correct else 0)
            else:
                # ответ на пример — используем example.points (если есть) при is_correct
                example = example_map.get(a.example_id)
                ex_pts = getattr(example, "points", None)
                if ex_pts is None:
                    # если у примера нет явного балла — по вашему правилу можно взять 0 или дробь
                    ex_pts = 0
                per_task[tid] += (ex_pts if a.is_correct else 0)

        # per_block суммы — суммируем per_task по задачам блока
        per_block = {}
        for b in tournament.blocks:
            s = 0
            for t in b.tasks:
                s += int(per_task.get(t.id, 0) or 0)
            per_block[b.id] = s

        total = sum(int(v or 0) for v in per_task.values())
        team_label = team.name or f"Team #{team.id}"

        teams_out.append({
            "id": team.id,
            "login": team_label,
            "per_task": {str(k): int(v) for k, v in per_task.items()},
            "per_block": {str(k): int(v) for k, v in per_block.items()},
            "total": int(total)
        })

    # сортируем по total desc, затем по id для стабильности
    teams_out.sort(key=lambda x: (-x["total"], x["id"]))

    # вычислим позиции с диапазонами при ничьих (1, 2-4, 5 ...)
    positions = []
    i = 0
    n = len(teams_out)
    while i < n:
        j = i
        while j + 1 < n and teams_out[j + 1]["total"] == teams_out[i]["total"]:
            j += 1
        if i == j:
            pos_str = str(i + 1)
        else:
            pos_str = f"{i+1}-{j+1}"
        for k in range(i, j + 1):
            teams_out[k]["position"] = pos_str
        i = j + 1

    response = {
        "tournament": {"id": tournament.id, "name": tournament.name},
        "blocks": [
            {
                "id": b.id,
                "name": b.name,
                "tasks": [{"id": t.id, "order": t.order} for t in sorted(b.tasks, key=lambda x: (x.order or 0, x.id))]
            } for b in tournament.blocks
        ],
        "teams": teams_out,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    return jsonify(response)

@bp.route("/dashboard/block/<int:block_id>", methods=["GET"])
def get_dashboard_block(block_id):
    block = TaskBlock.query.get_or_404(block_id)

    tasks = list(block.tasks)
    # ТОЛЬКО команды, зарегистрированные на турнир этого блока
    teams = Team.query.filter_by(tournament_id=block.tournament_id).order_by(Team.name).all()

    task_examples = {}
    for t in tasks:
        if getattr(t, "type", "single") == "examples":
            examples = TaskExample.query.filter_by(task_id=t.id).order_by(TaskExample.id).all()
            task_examples[t.id] = [{"id": ex.id, "text": ex.text, "points": getattr(ex, "points", None)} for ex in examples]
        else:
            task_examples[t.id] = []

    rows = []
    for team in teams:
        cells = []
        total = 0
        for t in tasks:
            if t.type == "examples":
                examples = TaskExample.query.filter_by(task_id=t.id).order_by(TaskExample.id).all()
                total_examples = len(examples)
                ans_list = Answer.query.filter_by(team_id=team.id, task_id=t.id).all()
                by_ex = {a.example_id: a for a in ans_list if a.example_id is not None}
                if len(by_ex) == 0:
                    cells.append({"state": "no-answer", "points": None})
                else:
                    correct_count = 0
                    points_sum = 0
                    for ex in examples:
                        a = by_ex.get(ex.id)
                        if a and getattr(a, "is_correct", False):
                            correct_count += 1
                        if a:
                            points_sum += getattr(a, "points", 0) or 0
                    total += points_sum
                    if total_examples > 0 and correct_count == total_examples:
                        cells.append({"state": "correct", "points": points_sum})
                    elif correct_count > 0:
                        cells.append({"state": "partial", "points": points_sum})
                    else:
                        cells.append({"state": "wrong", "points": points_sum})
            else:
                a = Answer.query.filter_by(team_id=team.id, task_id=t.id, example_id=None).first()
                if not a:
                    cells.append({"state": "no-answer", "points": None})
                else:
                    pts = getattr(a, "points", 0) or 0
                    total += pts
                    if getattr(a, "is_correct", False):
                        cells.append({"state": "correct", "points": pts})
                    else:
                        cells.append({"state": "wrong", "points": pts})

        # используем название команды
        team_name = team.name or f"Team #{team.id}"

        rows.append({
            "team_id": team.id,
            "team_name": team_name,
            "member1": team.member1,
            "member2": team.member2,
            "member3": team.member3,
            "cells": cells,
            "total": total
        })


    # сорт и rank labels (как было)
    rows.sort(key=lambda r: (-r["total"], r["team_name"]))
    # ... (вставь код генерации rank_label, идентичный твоему предыдущему)
    # для краткости — скопируй существующую реализацию меток мест (она у тебя уже есть)
    # затем:
    # return jsonify({...})
    # Ниже возвращаем структуру точно так же, как раньше:
    # для сохранения — положим реализацию label-логику из твоего файла (не меняется)
    # --------------------------

    # compute rank labels (same logic as earlier)
    rank_labels = {}
    if rows:
        last_score = None
        start_idx = 0
        for idx, r in enumerate(rows):
            if last_score is None:
                last_score = r["total"]
                start_idx = 0
            elif r["total"] != last_score:
                if start_idx == idx - 1:
                    rank_labels[(start_idx, idx - 1)] = str(start_idx + 1)
                else:
                    rank_labels[(start_idx, idx - 1)] = f"{start_idx + 1}-{idx}"
                last_score = r["total"]
                start_idx = idx
        n = len(rows)
        if start_idx == n - 1:
            rank_labels[(start_idx, n - 1)] = str(start_idx + 1)
        else:
            rank_labels[(start_idx, n - 1)] = f"{start_idx + 1}-{n}"
    labels = []
    for (s, e), label in rank_labels.items():
        for i in range(s, e + 1):
            labels.append((i, label))
    idx_to_label = {i: lab for i, lab in labels}
    for idx, r in enumerate(rows):
        r["rank_label"] = idx_to_label.get(idx, str(idx + 1))

    return jsonify({
        "block": {"id": block.id, "name": block.name},
        "tasks": [{"id": t.id, "title": t.title, "type": t.type, "points": getattr(t, "points", None)} for t in tasks],
        "rows": rows
    })


@bp.route("/dashboard/overall/<int:tournament_id>", methods=["GET"])
def get_dashboard_overall(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    blocks = list(tournament.blocks)
    teams = Team.query.filter_by(tournament_id=tournament.id).order_by(Team.name).all()

    rows = []
    for team in teams:
        cells = []
        total = 0
        for block in blocks:
            pts_block = 0
            any_answer = False
            for t in block.tasks:
                if t.type == "examples":
                    answers = Answer.query.filter(Answer.team_id == team.id, Answer.task_id == t.id, Answer.example_id.isnot(None)).all()
                    if answers:
                        any_answer = True
                        pts_block += sum(getattr(a, "points", 0) or 0 for a in answers)
                else:
                    a = Answer.query.filter_by(team_id=team.id, task_id=t.id, example_id=None).first()
                    if a:
                        any_answer = True
                        pts_block += getattr(a, "points", 0) or 0
            cells.append({"points": pts_block, "answered": any_answer})
            total += pts_block
        team_name = team.name or f"Team #{team.id}"
        rows.append({
            "team_id": team.id,
            "team_name": team_name,
            "member1": team.member1,
            "member2": team.member2,
            "member3": team.member3,
            "cells": cells,
            "total": total
        })


    rows.sort(key=lambda r: (-r["total"], r["team_name"]))
    # compute rank labels same as above
    rank_labels = {}
    if rows:
        last_score = None
        start_idx = 0
        for idx, r in enumerate(rows):
            if last_score is None:
                last_score = r["total"]
                start_idx = 0
            elif r["total"] != last_score:
                if start_idx == idx - 1:
                    rank_labels[(start_idx, idx - 1)] = str(start_idx + 1)
                else:
                    rank_labels[(start_idx, idx - 1)] = f"{start_idx + 1}-{idx}"
                last_score = r["total"]
                start_idx = idx
        n = len(rows)
        if start_idx == n - 1:
            rank_labels[(start_idx, n - 1)] = str(start_idx + 1)
        else:
            rank_labels[(start_idx, n - 1)] = f"{start_idx + 1}-{n}"
    labels = []
    for (s, e), label in rank_labels.items():
        for i in range(s, e + 1):
            labels.append((i, label))
    idx_to_label = {i: lab for i, lab in labels}
    for idx, r in enumerate(rows):
        r["rank_label"] = idx_to_label.get(idx, str(idx + 1))

    return jsonify({
        "tournament": {"id": tournament.id, "name": tournament.name},
        "blocks": [{"id": b.id, "name": b.name} for b in blocks],
        "rows": rows
    })
