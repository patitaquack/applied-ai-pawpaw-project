from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import List, Optional

CATEGORIES = {"feeding", "walk", "grooming", "medication", "playtime", "litter", "other"}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
VALID_STATUSES = {"pending", "done", "skipped"}
VALID_RECURRENCES = {"none", "daily", "twice_daily", "weekly"}
RECURRENCE_DAYS = {"daily": 1, "twice_daily": 1, "weekly": 7}


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: str
    category: str = "other"
    notes: str = ""
    pet_name: str = ""
    status: str = "pending"
    recurrence: str = "none"
    preferred_start_minute: Optional[int] = None
    deadline_minute: Optional[int] = None
    medication_dose: str = ""
    instructions: str = ""
    due_date: date = field(default_factory=date.today)
    task_id: Optional[int] = None

    def __post_init__(self):
        if self.priority not in PRIORITY_ORDER:
            raise ValueError(f"priority must be one of {list(PRIORITY_ORDER)}")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {list(VALID_STATUSES)}")
        if self.recurrence not in VALID_RECURRENCES:
            raise ValueError(f"recurrence must be one of {list(VALID_RECURRENCES)}")
        if self.category not in CATEGORIES:
            self.category = "other"

    def mark_complete(self) -> Optional["Task"]:
        self.status = "done"
        if self.recurrence == "none":
            return None
        days_ahead = RECURRENCE_DAYS[self.recurrence]
        next_due = self.due_date + timedelta(days=days_ahead)
        return replace(self, status="pending", due_date=next_due, task_id=None)

    @property
    def is_critical(self) -> bool:
        return self.category in {"feeding", "medication"} or self.priority == "high"


@dataclass
class Pet:
    name: str
    species: str
    age_years: float = 0.0
    weight_kg: float = 0.0
    health_conditions: str = ""
    activity_level: str = "moderate"
    size: str = ""          # small | medium | large
    age_group: str = ""     # puppy | adult | senior
    lifestyle: str = ""     # active_dog | low_energy_dog | indoor_cat
    pet_id: Optional[int] = None

    @property
    def is_senior(self) -> bool:
        if self.species == "dog" and self.age_years >= 7:
            return True
        if self.species == "cat" and self.age_years >= 10:
            return True
        return False


@dataclass
class Owner:
    name: str
    available_minutes: int
    pet: Optional[Pet] = None
    tasks: List[Task] = field(default_factory=list)
    owner_id: Optional[int] = None

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)

    def clear_tasks(self) -> None:
        self.tasks.clear()

    def mark_task_complete(self, title: str) -> Optional[Task]:
        for task in self.tasks:
            if task.title == title and task.status == "pending":
                next_task = task.mark_complete()
                if next_task is not None:
                    self.tasks.append(next_task)
                return next_task
        return None

    def filter_tasks(self, pet_name=None, status=None) -> List[Task]:
        return [
            t for t in self.tasks
            if (pet_name is None or t.pet_name == pet_name)
            and (status is None or t.status == status)
        ]


@dataclass
class ScheduledTask:
    task: Task
    start_minute: int
    reason: str = ""

    @property
    def end_minute(self) -> int:
        return self.start_minute + self.task.duration_minutes

    def start_time_str(self) -> str:
        return minutes_to_time(self.start_minute)

    def end_time_str(self) -> str:
        return minutes_to_time(self.end_minute)


@dataclass
class ConflictWarning:
    task_a: str
    task_b: str
    pet_a: str
    pet_b: str
    overlap_start: int
    overlap_end: int

    @property
    def same_pet(self) -> bool:
        return self.pet_a == self.pet_b

    def message(self) -> str:
        overlap_duration = self.overlap_end - self.overlap_start
        who = (
            f"same pet ({self.pet_a})"
            if self.same_pet
            else f"different pets ({self.pet_a} and {self.pet_b})"
        )
        return (
            f"WARNING: '{self.task_a}' and '{self.task_b}' overlap by "
            f"{overlap_duration} min at {minutes_to_time(self.overlap_start)} [{who}]"
        )


@dataclass
class Schedule:
    owner: Owner
    scheduled_tasks: List[ScheduledTask] = field(default_factory=list)
    skipped_tasks: List[Task] = field(default_factory=list)
    conflicts: List[ConflictWarning] = field(default_factory=list)
    skipped_reasons: dict = field(default_factory=dict)

    @property
    def total_minutes_scheduled(self) -> int:
        return sum(st.task.duration_minutes for st in self.scheduled_tasks)

    @property
    def completed_count(self) -> int:
        return sum(1 for st in self.scheduled_tasks if st.task.status == "done")

    @property
    def pending_count(self) -> int:
        return sum(1 for st in self.scheduled_tasks if st.task.status == "pending")

    def to_rows(self) -> List[dict]:
        return [
            {
                "Time": f"{s.start_time_str()} – {s.end_time_str()}",
                "Pet": s.task.pet_name or "—",
                "Task": s.task.title,
                "Category": s.task.category.capitalize(),
                "Duration (min)": s.task.duration_minutes,
                "Priority": s.task.priority.capitalize(),
                "Recurrence": s.task.recurrence,
                "Why": s.reason,
            }
            for s in self.scheduled_tasks
        ]

    def skipped_rows(self) -> List[dict]:
        return [
            {
                "Task": t.title,
                "Category": t.category.capitalize(),
                "Duration (min)": t.duration_minutes,
                "Priority": t.priority.capitalize(),
                "Why skipped": self.skipped_reasons.get(t.title, "Not enough time or outside day window"),
                "Suggestion": _suggest_alternative(t),
            }
            for t in self.skipped_tasks
        ]

    def conflict_rows(self) -> List[dict]:
        return [
            {
                "Task A": c.task_a,
                "Task B": c.task_b,
                "Same pet": c.same_pet,
                "Pets": f"{c.pet_a} / {c.pet_b}",
                "Overlap at": minutes_to_time(c.overlap_start),
                "Overlap (min)": c.overlap_end - c.overlap_start,
            }
            for c in self.conflicts
        ]


# ── Pet Templates ─────────────────────────────────────────────────────────────

def get_pet_templates(pet: Pet) -> List[Task]:
    tasks = []
    if pet.species == "dog":
        tasks = [
            Task(title="Morning walk", duration_minutes=30, priority="high", category="walk",
                 recurrence="daily", preferred_start_minute=480, pet_name=pet.name),
            Task(title="Feeding", duration_minutes=10, priority="high", category="feeding",
                 recurrence="twice_daily", preferred_start_minute=480, pet_name=pet.name),
            Task(title="Evening walk", duration_minutes=20, priority="medium", category="walk",
                 recurrence="daily", preferred_start_minute=1080, pet_name=pet.name),
            Task(title="Playtime", duration_minutes=15, priority="medium", category="playtime",
                 recurrence="daily", pet_name=pet.name),
            Task(title="Grooming", duration_minutes=20, priority="low", category="grooming",
                 recurrence="weekly", pet_name=pet.name),
        ]
    elif pet.species == "cat":
        tasks = [
            Task(title="Feeding", duration_minutes=10, priority="high", category="feeding",
                 recurrence="twice_daily", preferred_start_minute=480, pet_name=pet.name),
            Task(title="Litter box", duration_minutes=5, priority="high", category="litter",
                 recurrence="daily", pet_name=pet.name),
            Task(title="Playtime", duration_minutes=15, priority="medium", category="playtime",
                 recurrence="daily", pet_name=pet.name),
        ]
    else:
        tasks = [
            Task(title="Feeding", duration_minutes=10, priority="high", category="feeding",
                 recurrence="twice_daily", preferred_start_minute=480, pet_name=pet.name),
            Task(title="Playtime", duration_minutes=15, priority="medium", category="playtime",
                 recurrence="daily", pet_name=pet.name),
        ]

    if pet.is_senior:
        tasks.append(
            Task(title="Medication", duration_minutes=5, priority="high", category="medication",
                 recurrence="daily", preferred_start_minute=510, pet_name=pet.name)
        )

    return tasks


# ── Helpers ───────────────────────────────────────────────────────────────────

def minutes_to_time(minutes: int) -> str:
    h, m = divmod(minutes % (24 * 60), 60)
    period = "AM" if h < 12 else "PM"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d} {period}"


def _suggest_alternative(task: Task) -> str:
    if task.is_critical:
        return "Critical — reschedule immediately or move to top of tomorrow's list"
    if task.priority == "medium":
        return "Try scheduling earlier in the day or reducing duration"
    return "Move to tomorrow or consider reducing duration"
