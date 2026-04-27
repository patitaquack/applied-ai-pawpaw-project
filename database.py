import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import List, Optional

from logger import get_logger
from models import Task, Pet, Owner

DB_PATH = "pawpal.db"
_log = get_logger(__name__)


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except sqlite3.Error as exc:
        _log.error("DB error: %s", exc)
        raise
    finally:
        con.close()


def init_db() -> None:
    _log.debug("init_db | ensuring schema exists in %s", DB_PATH)
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS owners (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT NOT NULL,
                available_minutes INTEGER DEFAULT 60
            );

            CREATE TABLE IF NOT EXISTS pets (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id          INTEGER REFERENCES owners(id),
                name              TEXT NOT NULL,
                species           TEXT NOT NULL,
                age_years         REAL    DEFAULT 0,
                weight_kg         REAL    DEFAULT 0,
                health_conditions TEXT    DEFAULT '',
                activity_level    TEXT    DEFAULT 'moderate'
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_name               TEXT    NOT NULL,
                title                  TEXT    NOT NULL,
                duration_minutes       INTEGER NOT NULL,
                priority               TEXT    NOT NULL,
                category               TEXT    DEFAULT 'other',
                notes                  TEXT    DEFAULT '',
                status                 TEXT    DEFAULT 'pending',
                recurrence             TEXT    DEFAULT 'none',
                preferred_start_minute INTEGER,
                deadline_minute        INTEGER,
                medication_dose        TEXT    DEFAULT '',
                instructions           TEXT    DEFAULT '',
                due_date               TEXT    NOT NULL
            );
        """)


# ── Owner ─────────────────────────────────────────────────────────────────────

def save_owner(owner: Owner) -> int:
    with _conn() as con:
        if owner.owner_id:
            con.execute(
                "UPDATE owners SET name=?, available_minutes=? WHERE id=?",
                (owner.name, owner.available_minutes, owner.owner_id),
            )
            _log.debug("save_owner | updated id=%d name=%s", owner.owner_id, owner.name)
            return owner.owner_id
        cur = con.execute(
            "INSERT INTO owners (name, available_minutes) VALUES (?, ?)",
            (owner.name, owner.available_minutes),
        )
        _log.info("save_owner | inserted id=%d name=%s", cur.lastrowid, owner.name)
        return cur.lastrowid


def load_owner(owner_id: int) -> Optional[Owner]:
    with _conn() as con:
        row = con.execute("SELECT * FROM owners WHERE id=?", (owner_id,)).fetchone()
    if not row:
        _log.warning("load_owner | id=%d not found", owner_id)
        return None
    return Owner(name=row["name"], available_minutes=row["available_minutes"], owner_id=row["id"])


# ── Pet ───────────────────────────────────────────────────────────────────────

def save_pet(pet: Pet, owner_id: int) -> int:
    with _conn() as con:
        if pet.pet_id:
            con.execute(
                """UPDATE pets SET name=?, species=?, age_years=?, weight_kg=?,
                   health_conditions=?, activity_level=? WHERE id=?""",
                (pet.name, pet.species, pet.age_years, pet.weight_kg,
                 pet.health_conditions, pet.activity_level, pet.pet_id),
            )
            _log.debug("save_pet | updated id=%d name=%s", pet.pet_id, pet.name)
            return pet.pet_id
        cur = con.execute(
            """INSERT INTO pets (owner_id, name, species, age_years, weight_kg,
               health_conditions, activity_level) VALUES (?,?,?,?,?,?,?)""",
            (owner_id, pet.name, pet.species, pet.age_years, pet.weight_kg,
             pet.health_conditions, pet.activity_level),
        )
        _log.info("save_pet | inserted id=%d name=%s owner_id=%d", cur.lastrowid, pet.name, owner_id)
        return cur.lastrowid


def load_pet(pet_id: int) -> Optional[Pet]:
    with _conn() as con:
        row = con.execute("SELECT * FROM pets WHERE id=?", (pet_id,)).fetchone()
    if not row:
        _log.warning("load_pet | id=%d not found", pet_id)
        return None
    return Pet(
        name=row["name"], species=row["species"],
        age_years=row["age_years"], weight_kg=row["weight_kg"],
        health_conditions=row["health_conditions"], activity_level=row["activity_level"],
        pet_id=row["id"],
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

def save_task(task: Task) -> int:
    with _conn() as con:
        if task.task_id:
            con.execute(
                """UPDATE tasks SET title=?, duration_minutes=?, priority=?, category=?,
                   notes=?, status=?, recurrence=?, preferred_start_minute=?,
                   deadline_minute=?, medication_dose=?, instructions=?, due_date=?
                   WHERE id=?""",
                (task.title, task.duration_minutes, task.priority, task.category,
                 task.notes, task.status, task.recurrence, task.preferred_start_minute,
                 task.deadline_minute, task.medication_dose, task.instructions,
                 task.due_date.isoformat(), task.task_id),
            )
            _log.debug("save_task | updated id=%d title=%s", task.task_id, task.title)
            return task.task_id
        cur = con.execute(
            """INSERT INTO tasks (pet_name, title, duration_minutes, priority, category,
               notes, status, recurrence, preferred_start_minute, deadline_minute,
               medication_dose, instructions, due_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task.pet_name, task.title, task.duration_minutes, task.priority, task.category,
             task.notes, task.status, task.recurrence, task.preferred_start_minute,
             task.deadline_minute, task.medication_dose, task.instructions,
             task.due_date.isoformat()),
        )
        _log.info("save_task | inserted id=%d title=%s pet=%s", cur.lastrowid, task.title, task.pet_name)
        return cur.lastrowid


def load_tasks(
    pet_name: Optional[str] = None,
    status: Optional[str] = None,
    due_date: Optional[date] = None,
) -> List[Task]:
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if pet_name:
        query += " AND pet_name=?"
        params.append(pet_name)
    if status:
        query += " AND status=?"
        params.append(status)
    if due_date:
        query += " AND due_date=?"
        params.append(due_date.isoformat())

    with _conn() as con:
        rows = con.execute(query, params).fetchall()

    _log.debug("load_tasks | pet=%s status=%s due=%s → %d row(s)", pet_name, status, due_date, len(rows))
    return [
        Task(
            title=row["title"],
            duration_minutes=row["duration_minutes"],
            priority=row["priority"],
            category=row["category"],
            notes=row["notes"],
            pet_name=row["pet_name"],
            status=row["status"],
            recurrence=row["recurrence"],
            preferred_start_minute=row["preferred_start_minute"],
            deadline_minute=row["deadline_minute"],
            medication_dose=row["medication_dose"],
            instructions=row["instructions"],
            due_date=date.fromisoformat(row["due_date"]),
            task_id=row["id"],
        )
        for row in rows
    ]


def delete_task(task_id: int) -> None:
    _log.info("delete_task | id=%d", task_id)
    with _conn() as con:
        con.execute("DELETE FROM tasks WHERE id=?", (task_id,))


def get_weekly_summary(pet_name: str) -> dict:
    """Return status counts for tasks in the past 7 days."""
    from datetime import timedelta
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT status, COUNT(*) as count FROM tasks WHERE pet_name=? AND due_date >= ? GROUP BY status",
            (pet_name, week_ago),
        ).fetchall()
    summary = {row["status"]: row["count"] for row in rows}
    _log.debug("get_weekly_summary | pet=%s result=%s", pet_name, summary)
    return summary
