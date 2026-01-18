# app/views/dashboard.py
from flask import Blueprint, render_template, url_for, request, jsonify
from flask_login import login_required
from ..models import Tournament, TaskBlock, Team, TaskExample, Answer, Task
from datetime import datetime, timezone, timedelta
from collections import defaultdict

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

def _fmt_hms(seconds):
    try:
        s = int(max(0, int(seconds)))
    except Exception:
        return "00:00:00"
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"

def compute_block_table(block):
    tasks = list(block.tasks)
    teams = Team.query.filter_by(tournament_id=block.tournament_id).order_by(Team.name).all()

    task_examples = {}
    for t in tasks:
        if getattr(t, "type", "single") == "examples":
            examples = TaskExample.query.filter_by(task_id=t.id).order_by(TaskExample.id).all()
            task_examples[t.id] = examples
        else:
            task_examples[t.id] = []

    rows = []
    for team in teams:
        cells = []
        total = 0
        for t in tasks:
            if getattr(t, "type", "single") != "examples":
                a = Answer.query.filter_by(team_id=team.id, task_id=t.id, example_id=None).first()
                if not a:
                    cells.append({"state": "no-answer", "points": None})
                else:
                    pts = getattr(a, "points", 0) or 0
                    total += pts
                    cells.append({"state": "correct" if a.is_correct else "wrong", "points": pts})
            else:
                examples = task_examples.get(t.id, [])
                if not examples:
                    cells.append({"state": "no-answer", "points": None})
                    continue
                ans_list = Answer.query.filter_by(team_id=team.id, task_id=t.id).all()
                by_ex = {a.example_id: a for a in ans_list if a.example_id is not None}
                if not by_ex:
                    cells.append({"state": "no-answer", "points": None})
                else:
                    points_sum = 0
                    correct_count = 0
                    for ex in examples:
                        a = by_ex.get(ex.id)
                        if a:
                            points_sum += getattr(a, "points", 0) or 0
                            if getattr(a, "is_correct", False):
                                correct_count += 1
                    total += points_sum
                    if correct_count == len(examples):
                        cells.append({"state": "correct", "points": points_sum})
                    elif correct_count > 0:
                        cells.append({"state": "partial", "points": points_sum})
                    else:
                        cells.append({"state": "wrong", "points": points_sum})
        rows.append({"team": team, "cells": cells, "total": total})

    rows.sort(key=lambda r: (-r["total"], r["team"].name or ""))
    idx_to_label = {}
    if rows:
        last = None
        start = 0
        for i, r in enumerate(rows):
            if last is None:
                last = r["total"]; start = 0
            elif r["total"] != last:
                label = str(start+1) if start == i-1 else f"{start+1}-{i}"
                for j in range(start, i):
                    idx_to_label[j] = label
                last = r["total"]; start = i
        n = len(rows)
        label = str(start+1) if start == n-1 else f"{start+1}-{n}"
        for j in range(start, n):
            idx_to_label[j] = label

    for idx, r in enumerate(rows):
        r["rank_label"] = idx_to_label.get(idx, str(idx+1))

    return {"tasks": tasks, "rows": rows}


@bp.route("/<int:tournament_id>", methods=["GET"])
def index(tournament_id):
    """
    /dashboard/<tournament_id>
    """
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        # отрисовать пустую страницу
        return render_template("dashboard.html", tournament=None, blocks=[], active_block_id=None, blocks_data=[], overall_api="", server_time=None, blocks_meta={}, tournament_end=None)

    blocks = sorted(list(tournament.blocks), key=lambda b: b.order)
    blocks_data = []
    for b in blocks:
        data = compute_block_table(b)
        blocks_data.append({"block": b, "tasks": data["tasks"], "rows": data["rows"]})

    # По умолчанию показываем общие результаты, а не первый блок
    active_block_id = None

    # Метаданные времени больше не нужны, но оставляем для совместимости
    server_time = datetime.now(timezone.utc)
    blocks_meta = {}
    tournament_end = None
    
    for b in blocks:
        blocks_meta[b.id] = {"start_iso": None, "end_iso": None}

    return render_template(
        "dashboard.html",
        tournament=tournament,
        blocks=blocks,
        active_block_id=active_block_id,
        blocks_data=blocks_data,
        overall_api=url_for("api.get_dashboard_overall", tournament_id=tournament.id),
        server_time=server_time.isoformat(),
        blocks_meta=blocks_meta,
        tournament_end=tournament_end
    )