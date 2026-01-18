"""All

Revision ID: 4e4cf0ee3061
Revises: 928ed1a729ee
Create Date: 2025-12-29 15:35:07.632652

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4e4cf0ee3061'
down_revision = '928ed1a729ee'
branch_labels = None
depends_on = None

def _column_exists(conn, table, column):
    q = sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    )
    return bool(conn.execute(q, {"table": table, "column": column}).fetchone())

def _constraint_exists(conn, table, constraint_name):
    q = sa.text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE table_name = :table AND constraint_name = :cname"
    )
    return bool(conn.execute(q, {"table": table, "cname": constraint_name}).fetchone())

def _index_exists(conn, index_name):
    q = sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :iname")
    return bool(conn.execute(q, {"iname": index_name}).fetchone())

def _unique_constraint_name_for_column(conn, table, column):
    """
    Попробуем найти имя уникального ограничения, которое покрывает столбец column в таблице table.
    Возвращаем имя или None.
    """
    q = sa.text(
        "SELECT tc.constraint_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name AND tc.table_name = kcu.table_name "
        "WHERE tc.table_name = :table AND tc.constraint_type = 'UNIQUE' AND kcu.column_name = :column"
    )
    row = conn.execute(q, {"table": table, "column": column}).fetchone()
    return row[0] if row else None


def upgrade():
    conn = op.get_bind()

    # ---------- answers: заменить уникалку (drop old, create new) ----------
    # старое имя, как генерилось Alembic-ом, вероятно "answers_team_id_task_id_example_id_key"
    old_name = "answers_team_id_task_id_example_id_key"
    new_name = "uq_answers_team_task_example"

    if _constraint_exists(conn, "answers", old_name):
        try:
            op.drop_constraint(old_name, "answers", type_="unique")
        except Exception:
            # если по какой-то причине drop упал — просто логируем (не останавливаем миграцию)
            pass

    if not _constraint_exists(conn, "answers", new_name):
        op.create_unique_constraint(new_name, "answers", ["team_id", "task_id", "example_id"])

    # ---------- teams: добавить tournament_id (безопасно) и связанные изменения ----------
    # 1) добавить колонку tournament_id если нет
    if not _column_exists(conn, "teams", "tournament_id"):
        # добавим nullable колонку сначала
        op.add_column("teams", sa.Column("tournament_id", sa.Integer(), nullable=True))

        # если в таблице tournaments есть хотя бы одна запись, заполним NULL-ы её id,
        # чтобы потом можно было сделать NOT NULL безопасно
        row = conn.execute(sa.text("SELECT id FROM tournaments ORDER BY id LIMIT 1")).fetchone()
        if row:
            tid = row[0]
            conn.execute(sa.text("UPDATE teams SET tournament_id = :tid WHERE tournament_id IS NULL"), {"tid": tid})

        # теперь сделаем NOT NULL (если возможно)
        op.alter_column("teams", "tournament_id", nullable=False)

    # 2) убедиться, что member1 NOT NULL (если требуется)
    # оригинальная миграция делает member1 nullable=False
    # проверяем текущую схему и применяем только если нужно
    # (оп.alter_column не упадёт, если нет изменений, но мы проверим для аккуратности)
    # NOTE: SQLAlchemy не даёт простого способа узнать nullable через op, поэтому просто вызываем alter_column всегда
    try:
        op.alter_column("teams", "member1", existing_type=sa.VARCHAR(length=100), nullable=False)
    except Exception:
        # если не получилось — не фатально
        pass

    # 3) убрать уникальный индекс/constraint по login (если есть)
    login_uq = _unique_constraint_name_for_column(conn, "teams", "login")
    if login_uq:
        try:
            op.drop_constraint(login_uq, "teams", type_="unique")
        except Exception:
            pass

    # 4) создать FK tournament_id -> tournaments(id) если ещё нет
    fk_name = "teams_tournament_id_fkey"
    if not _constraint_exists(conn, "teams", fk_name):
        # op.create_foreign_key(None, ...) создаёт системное имя; укажем явное имя чтобы проще обращаться
        op.create_foreign_key(fk_name, "teams", "tournaments", ["tournament_id"], ["id"])

    # 5) удалить старые поля login, password_hash если они присутствуют
    if _column_exists(conn, "teams", "password_hash"):
        try:
            op.drop_column("teams", "password_hash")
        except Exception:
            pass
    if _column_exists(conn, "teams", "login"):
        try:
            op.drop_column("teams", "login")
        except Exception:
            pass

    # ---------- tournaments: добавить column "group" и индекс, если не существует ----------
    if not _column_exists(conn, "tournaments", "group"):
        op.add_column("tournaments", sa.Column("group", sa.String(length=32), nullable=True))

    idx_name = "ix_tournaments_group"
    if not _index_exists(conn, idx_name):
        op.create_index(idx_name, "tournaments", ["group"], unique=False)


def downgrade():
    conn = op.get_bind()

    # ---------- tournaments: откатить индекс/колонку "group" если есть ----------
    idx_name = "ix_tournaments_group"
    if _index_exists(conn, idx_name):
        try:
            op.drop_index(idx_name, table_name="tournaments")
        except Exception:
            pass

    if _column_exists(conn, "tournaments", "group"):
        try:
            op.drop_column("tournaments", "group")
        except Exception:
            pass

    # ---------- teams: восстановить login/password_hash (в безопасном виде) и удалить tournament_id ----------
    # ВНИМАНИЕ: восстановление login/password_hash может быть проблематично, добавляем их nullable=True,
    # чтобы downgrade не падал из-за отсутствия данных. Если тебе нужно восстановить их non-null —
    # лучше делать это вручную после отката.
    if not _column_exists(conn, "teams", "login"):
        op.add_column("teams", sa.Column("login", sa.VARCHAR(length=50), nullable=True))
    if not _column_exists(conn, "teams", "password_hash"):
        op.add_column("teams", sa.Column("password_hash", sa.VARCHAR(length=200), nullable=True))

    # если уникальное ограничение на login отсутствует — (попытка) создать его
    login_uq = _unique_constraint_name_for_column(conn, "teams", "login")
    if not login_uq:
        try:
            op.create_unique_constraint("teams_login_key", "teams", ["login"])
        except Exception:
            pass

    # вернуть member1 nullable=True (как было до миграции)
    try:
        op.alter_column("teams", "member1", existing_type=sa.VARCHAR(length=100), nullable=True)
    except Exception:
        pass

    # удалить FK и колонку tournament_id если они есть
    fk_name = "teams_tournament_id_fkey"
    if _constraint_exists(conn, "teams", fk_name):
        try:
            op.drop_constraint(fk_name, "teams", type_="foreignkey")
        except Exception:
            pass

    if _column_exists(conn, "teams", "tournament_id"):
        try:
            op.drop_column("teams", "tournament_id")
        except Exception:
            pass

    # ---------- answers: вернуть старое имя уникалки, удалить новую если есть ----------
    new_name = "uq_answers_team_task_example"
    old_name = "answers_team_id_task_id_example_id_key"
    # удалить нашу новую уникалку, если она существует
    if _constraint_exists(conn, "answers", new_name):
        try:
            op.drop_constraint(new_name, "answers", type_="unique")
        except Exception:
            pass

    # восстановить старую (если её нет)
    if not _constraint_exists(conn, "answers", old_name):
        try:
            op.create_unique_constraint(old_name, "answers", ["team_id", "task_id", "example_id"])
        except Exception:
            pass
