# app/utils.py
from datetime import datetime, timezone, timedelta
from sqlalchemy import func

def get_team_block_start_time(team, block):
    """
    Определяет время начала блока для команды.
    Блок начинается когда команда нажала кнопку "Начать следующий блок" на станице /waiting.
    Для первого блока - автоматиечски начинается при первом ответе (для обратной совместимости).    
    Возвращает datetime или None если блок еще не начался.
    """
    from .models import Answer, TaskBlock, TeamBlockStart
    
    # Время начала турнира для команды
    block_start = TeamBlockStart.query.filter_by(
        team_id=team.id,
        block_id=block.id
    ).first()
    
    if block_start:
        return block_start.started_at
    
    # Для обратной совместимости: если это первый блок и команда ещё не начинала блоки явно,
    # то первый блок начинается при первом ответе или с начала турнира
    prev_block = TaskBlock.query.filter_by(
        tournament_id=block.tournament_id
    ).filter(
        TaskBlock.order < block.order
    ).order_by(TaskBlock.order.desc()).first()
    
    if not prev_block:
        # Это первый блок - начинается с начала турнира
        team_start = team.started_at
        if team_start:
            return team_start
    
    # Если время не установлено - блок ещё не начался
    return None

def get_team_block_end_time(team, block):
    """
    Определяет время окончания блока для команды.
    Блок заканчивается когда:
    1. Все задачи в блоке решены, ИЛИ
    2. Достигнута максимальная длительность блока
    
    Возвращает datetime или None если блок еще не закончен.
    """
    from .models import Answer, Task
    
    block_start = get_team_block_start_time(team, block)
    if not block_start:
        return None
    
    # Проверим, отвечены ли все задачи (независимо от правильности)
    all_tasks = Task.query.filter_by(block_id=block.id).all()
    all_answered = True
    
    for task in all_tasks:
        if task.type == "examples":
            # Для задач с примерами нужно проверить все примеры
            examples = task.examples
            for example in examples:
                answer = Answer.query.filter_by(
                    team_id=team.id,
                    task_id=task.id,
                    example_id=example.id
                ).first()
                if not answer:
                    all_answered = False
                    break
            if not all_answered:
                break
        else:
            # Для обычных задач нужен любой ответ
            answer = Answer.query.filter_by(
                team_id=team.id,
                task_id=task.id,
                example_id=None
            ).first()
            if not answer:
                all_answered = False
                break
    
    if all_answered:
        # Найти время последнего ответа в блоке
        last_answer = Answer.query.filter_by(team_id=team.id).join(
            Answer.task
        ).filter(
            Answer.task.has(block_id=block.id)
        ).order_by(Answer.submitted_at.desc()).first()
        
        if last_answer:
            return last_answer.submitted_at
    
    # Проверим максимальную длительность
    max_end = block_start + timedelta(seconds=block.max_duration)
    now = datetime.now(timezone.utc)
    
    if now >= max_end:
        return max_end
    
    return None

def get_team_active_block(team, tournament):
    """
    Определяет активный блок для команды.
    Возвращает TaskBlock или None.
    """
    from .models import TaskBlock
    
    blocks = TaskBlock.query.filter_by(
        tournament_id=tournament.id
    ).order_by(TaskBlock.order.asc()).all()
    
    if not blocks:
        return None
    
    now = datetime.now(timezone.utc)
    
    for block in blocks:
        block_start = get_team_block_start_time(team, block)
        block_end = get_team_block_end_time(team, block)
        
        if block_start and not block_end:
            # Блок начался и еще не закончен
            return block
        elif not block_start:
            # Блок еще не начался - это следующий активный блок
            return block
    
    # Все блоки закончены
    return None

def get_team_block_time_left(team, block):
    """
    Возвращает оставшееся время блока для команды в секундах.
    Учитывает максимальную длительность и время начала блока.
    """
    block_start = get_team_block_start_time(team, block)
    if not block_start:
        return None
    
    block_end = get_team_block_end_time(team, block)
    if block_end:
        return 0  # Блок уже закончен
    
    now = datetime.now(timezone.utc)
    max_end = block_start + timedelta(seconds=block.max_duration)
    
    time_left = (max_end - now).total_seconds()
    return max(0, time_left)
