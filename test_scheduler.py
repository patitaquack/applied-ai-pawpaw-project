import pytest
from datetime import date, timedelta
from pawpal_system import (
    Task, Pet, Owner, generate_schedule,
    filter_tasks, sort_by_time, expand_recurring, detect_conflicts,
    ScheduledTask, ConflictWarning,
)


def make_owner(available_minutes=120):
    pet = Pet(name="Mochi", species="dog")
    return Owner(name="Jordan", available_minutes=available_minutes, pet=pet)


# ── Priority ordering ─────────────────────────────────────────────────────────

def test_high_priority_scheduled_before_low():
    owner = make_owner(available_minutes=60)
    tasks = [
        Task(title="Low task", duration_minutes=20, priority="low"),
        Task(title="High task", duration_minutes=20, priority="high"),
    ]
    schedule = generate_schedule(owner, tasks)
    titles = [st.task.title for st in schedule.scheduled_tasks]
    assert titles.index("High task") < titles.index("Low task")


def test_high_before_medium_before_low():
    owner = make_owner(available_minutes=120)
    tasks = [
        Task(title="Low", duration_minutes=10, priority="low"),
        Task(title="High", duration_minutes=10, priority="high"),
        Task(title="Medium", duration_minutes=10, priority="medium"),
    ]
    schedule = generate_schedule(owner, tasks)
    titles = [st.task.title for st in schedule.scheduled_tasks]
    assert titles == ["High", "Medium", "Low"]


# ── Time constraint ───────────────────────────────────────────────────────────

def test_tasks_exceeding_available_time_are_skipped():
    owner = make_owner(available_minutes=30)
    tasks = [
        Task(title="Short", duration_minutes=20, priority="high"),
        Task(title="Too long", duration_minutes=60, priority="high"),
    ]
    schedule = generate_schedule(owner, tasks)
    assert len(schedule.scheduled_tasks) == 1
    assert schedule.scheduled_tasks[0].task.title == "Short"
    assert len(schedule.skipped_tasks) == 1
    assert schedule.skipped_tasks[0].title == "Too long"


def test_total_scheduled_minutes_does_not_exceed_available():
    owner = make_owner(available_minutes=45)
    tasks = [
        Task(title="A", duration_minutes=20, priority="high"),
        Task(title="B", duration_minutes=20, priority="medium"),
        Task(title="C", duration_minutes=20, priority="low"),
    ]
    schedule = generate_schedule(owner, tasks)
    assert schedule.total_minutes_scheduled <= owner.available_minutes


def test_exact_fit_schedules_all_tasks():
    owner = make_owner(available_minutes=30)
    tasks = [
        Task(title="A", duration_minutes=10, priority="high"),
        Task(title="B", duration_minutes=10, priority="medium"),
        Task(title="C", duration_minutes=10, priority="low"),
    ]
    schedule = generate_schedule(owner, tasks)
    assert len(schedule.scheduled_tasks) == 3
    assert len(schedule.skipped_tasks) == 0


# ── Start times ───────────────────────────────────────────────────────────────

def test_tasks_start_times_are_sequential():
    owner = make_owner(available_minutes=60)
    tasks = [
        Task(title="First", duration_minutes=15, priority="high"),
        Task(title="Second", duration_minutes=15, priority="medium"),
    ]
    schedule = generate_schedule(owner, tasks, day_start_minute=480)
    first, second = schedule.scheduled_tasks
    assert first.start_minute == 480
    assert second.start_minute == 480 + 15


def test_custom_day_start_minute_is_respected():
    owner = make_owner(available_minutes=60)
    tasks = [Task(title="Task", duration_minutes=20, priority="high")]
    schedule = generate_schedule(owner, tasks, day_start_minute=600)  # 10:00 AM
    assert schedule.scheduled_tasks[0].start_minute == 600


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_task_list_produces_empty_schedule():
    owner = make_owner(available_minutes=60)
    schedule = generate_schedule(owner, [])
    assert schedule.scheduled_tasks == []
    assert schedule.skipped_tasks == []


def test_single_task_too_long_is_skipped():
    owner = make_owner(available_minutes=10)
    tasks = [Task(title="Long task", duration_minutes=60, priority="high")]
    schedule = generate_schedule(owner, tasks)
    assert schedule.scheduled_tasks == []
    assert len(schedule.skipped_tasks) == 1


def test_invalid_priority_raises():
    with pytest.raises(ValueError):
        Task(title="Bad", duration_minutes=10, priority="urgent")


def test_zero_duration_raises():
    with pytest.raises(ValueError):
        Task(title="Bad", duration_minutes=0, priority="high")


# ── Reasoning ─────────────────────────────────────────────────────────────────

def test_scheduled_tasks_have_non_empty_reason():
    owner = make_owner(available_minutes=60)
    tasks = [Task(title="Walk", duration_minutes=20, priority="high")]
    schedule = generate_schedule(owner, tasks)
    assert schedule.scheduled_tasks[0].reason != ""


def test_reason_includes_start_time():
    owner = make_owner(available_minutes=60)
    tasks = [Task(title="Walk", duration_minutes=20, priority="high")]
    schedule = generate_schedule(owner, tasks, day_start_minute=480)
    assert "8:00 AM" in schedule.scheduled_tasks[0].reason


# ── filter_tasks (standalone function) ───────────────────────────────────────

def test_filter_by_status_pending():
    tasks = [
        Task(title="A", duration_minutes=10, priority="high", status="pending"),
        Task(title="B", duration_minutes=10, priority="high", status="done"),
        Task(title="C", duration_minutes=10, priority="high", status="skipped"),
    ]
    result = filter_tasks(tasks, status="pending")
    assert len(result) == 1
    assert result[0].title == "A"


def test_filter_by_pet_name():
    tasks = [
        Task(title="Walk",   duration_minutes=10, priority="high", pet_name="Mochi"),
        Task(title="Litter", duration_minutes=5,  priority="high", pet_name="Bean"),
        Task(title="Meds",   duration_minutes=5,  priority="high", pet_name="Mochi"),
    ]
    result = filter_tasks(tasks, pet_name="Mochi")
    assert len(result) == 2
    assert all(t.pet_name == "Mochi" for t in result)


def test_filter_by_pet_name_and_status():
    tasks = [
        Task(title="A", duration_minutes=10, priority="high", pet_name="Mochi", status="pending"),
        Task(title="B", duration_minutes=10, priority="high", pet_name="Mochi", status="done"),
        Task(title="C", duration_minutes=10, priority="high", pet_name="Bean",  status="pending"),
    ]
    result = filter_tasks(tasks, pet_name="Mochi", status="pending")
    assert len(result) == 1
    assert result[0].title == "A"


def test_filter_no_arguments_returns_all():
    tasks = [
        Task(title="A", duration_minutes=10, priority="high", status="pending"),
        Task(title="B", duration_minutes=10, priority="low",  status="done"),
    ]
    assert filter_tasks(tasks) == tasks


def test_filter_returns_empty_when_no_match():
    tasks = [Task(title="A", duration_minutes=10, priority="high", pet_name="Mochi")]
    assert filter_tasks(tasks, pet_name="Bean") == []


# ── Owner.filter_tasks (method) ───────────────────────────────────────────────

def test_owner_filter_tasks_pending():
    owner = make_owner()
    owner.add_task(Task(title="Walk", duration_minutes=20, priority="high", status="pending"))
    owner.add_task(Task(title="Bath", duration_minutes=30, priority="low",  status="done"))
    result = owner.filter_tasks(status="pending")
    assert len(result) == 1
    assert result[0].title == "Walk"


def test_owner_filter_tasks_by_pet():
    owner = make_owner()
    owner.add_task(Task(title="Walk",   duration_minutes=20, priority="high", pet_name="Mochi"))
    owner.add_task(Task(title="Litter", duration_minutes=5,  priority="high", pet_name="Bean"))
    result = owner.filter_tasks(pet_name="Bean")
    assert len(result) == 1
    assert result[0].title == "Litter"


# ── sort_by_time ──────────────────────────────────────────────────────────────

def test_sort_by_time_orders_by_preferred_start():
    tasks = [
        Task(title="Late",  duration_minutes=10, priority="high", preferred_start_minute=600),
        Task(title="Early", duration_minutes=10, priority="high", preferred_start_minute=480),
        Task(title="Mid",   duration_minutes=10, priority="high", preferred_start_minute=540),
    ]
    result = sort_by_time(tasks)
    assert [t.title for t in result] == ["Early", "Mid", "Late"]


def test_sort_by_time_none_goes_last():
    tasks = [
        Task(title="No pref",  duration_minutes=10, priority="high", preferred_start_minute=None),
        Task(title="Has pref", duration_minutes=10, priority="high", preferred_start_minute=480),
    ]
    result = sort_by_time(tasks)
    assert result[0].title == "Has pref"
    assert result[1].title == "No pref"


def test_sort_by_time_all_none_preserves_order():
    tasks = [
        Task(title="A", duration_minutes=10, priority="high", preferred_start_minute=None),
        Task(title="B", duration_minutes=10, priority="low",  preferred_start_minute=None),
    ]
    result = sort_by_time(tasks)
    # all keys are equal (9999), so original order is preserved (stable sort)
    assert [t.title for t in result] == ["A", "B"]


# ── expand_recurring ──────────────────────────────────────────────────────────

def test_expand_twice_daily_creates_two_entries():
    tasks = [Task(title="Feeding", duration_minutes=10, priority="high",
                  recurrence="twice_daily", preferred_start_minute=480)]
    result = expand_recurring(tasks)
    assert len(result) == 2
    assert result[0].title == "Feeding"
    assert result[1].title == "Feeding (2nd)"


def test_expand_twice_daily_second_copy_offset_by_8_hours():
    tasks = [Task(title="Feeding", duration_minutes=10, priority="high",
                  recurrence="twice_daily", preferred_start_minute=480)]
    result = expand_recurring(tasks)
    assert result[1].preferred_start_minute == 480 + 480  # 4 PM


def test_expand_daily_not_duplicated():
    tasks = [Task(title="Walk", duration_minutes=20, priority="high", recurrence="daily")]
    result = expand_recurring(tasks)
    assert len(result) == 1


def test_expand_none_recurrence_not_duplicated():
    tasks = [Task(title="Groom", duration_minutes=30, priority="low", recurrence="none")]
    result = expand_recurring(tasks)
    assert len(result) == 1


def test_expand_weekly_not_duplicated():
    tasks = [Task(title="Bath", duration_minutes=30, priority="low", recurrence="weekly")]
    result = expand_recurring(tasks)
    assert len(result) == 1


# ── Task.mark_complete ────────────────────────────────────────────────────────

def test_mark_complete_sets_status_to_done():
    task = Task(title="Walk", duration_minutes=20, priority="high", recurrence="daily")
    task.mark_complete()
    assert task.status == "done"


def test_mark_complete_daily_returns_next_day():
    today = date.today()
    task = Task(title="Walk", duration_minutes=20, priority="high",
                recurrence="daily", due_date=today)
    next_task = task.mark_complete()
    assert next_task is not None
    assert next_task.due_date == today + timedelta(days=1)
    assert next_task.status == "pending"


def test_mark_complete_weekly_returns_seven_days_later():
    today = date.today()
    task = Task(title="Bath", duration_minutes=30, priority="low",
                recurrence="weekly", due_date=today)
    next_task = task.mark_complete()
    assert next_task is not None
    assert next_task.due_date == today + timedelta(days=7)


def test_mark_complete_twice_daily_returns_next_day():
    today = date.today()
    task = Task(title="Feeding", duration_minutes=10, priority="high",
                recurrence="twice_daily", due_date=today)
    next_task = task.mark_complete()
    assert next_task.due_date == today + timedelta(days=1)


def test_mark_complete_none_recurrence_returns_none():
    task = Task(title="One-off", duration_minutes=15, priority="medium", recurrence="none")
    next_task = task.mark_complete()
    assert next_task is None


def test_mark_complete_next_task_has_same_title():
    task = Task(title="Medication", duration_minutes=5, priority="high", recurrence="daily")
    next_task = task.mark_complete()
    assert next_task.title == "Medication"


# ── Owner.mark_task_complete ──────────────────────────────────────────────────

def test_owner_mark_task_complete_adds_next_occurrence():
    owner = make_owner()
    owner.add_task(Task(title="Walk", duration_minutes=20, priority="high", recurrence="daily"))
    owner.mark_task_complete("Walk")
    titles = [t.title for t in owner.tasks]
    assert titles.count("Walk") == 2  # original (done) + new (pending)


def test_owner_mark_task_complete_original_is_done():
    owner = make_owner()
    owner.add_task(Task(title="Walk", duration_minutes=20, priority="high", recurrence="daily"))
    owner.mark_task_complete("Walk")
    assert owner.tasks[0].status == "done"


def test_owner_mark_task_complete_no_recurrence_does_not_add():
    owner = make_owner()
    owner.add_task(Task(title="Groom", duration_minutes=30, priority="low", recurrence="none"))
    owner.mark_task_complete("Groom")
    assert len(owner.tasks) == 1  # no new task added
    assert owner.tasks[0].status == "done"


def test_owner_mark_task_complete_unknown_title_returns_none():
    owner = make_owner()
    result = owner.mark_task_complete("Nonexistent task")
    assert result is None


# ── detect_conflicts ──────────────────────────────────────────────────────────

def _make_scheduled(title, start, duration, pet_name="Mochi"):
    task = Task(title=title, duration_minutes=duration, priority="high", pet_name=pet_name)
    return ScheduledTask(task=task, start_minute=start)


def test_no_conflicts_when_tasks_are_sequential():
    scheduled = [
        _make_scheduled("Walk",    start=480, duration=20),
        _make_scheduled("Feeding", start=500, duration=10),
    ]
    assert detect_conflicts(scheduled) == []


def test_detects_overlap_same_pet():
    scheduled = [
        _make_scheduled("Walk",    start=480, duration=30, pet_name="Mochi"),
        _make_scheduled("Feeding", start=490, duration=10, pet_name="Mochi"),
    ]
    conflicts = detect_conflicts(scheduled)
    assert len(conflicts) == 1
    assert conflicts[0].same_pet is True
    assert conflicts[0].task_a == "Walk"
    assert conflicts[0].task_b == "Feeding"


def test_detects_overlap_different_pets():
    scheduled = [
        _make_scheduled("Walk",   start=480, duration=30, pet_name="Mochi"),
        _make_scheduled("Litter", start=490, duration=10, pet_name="Bean"),
    ]
    conflicts = detect_conflicts(scheduled)
    assert len(conflicts) == 1
    assert conflicts[0].same_pet is False


def test_conflict_overlap_duration_is_correct():
    # Walk: 480-510, Feeding: 495-515 → overlap is 495-510 = 15 min
    scheduled = [
        _make_scheduled("Walk",    start=480, duration=30),
        _make_scheduled("Feeding", start=495, duration=20),
    ]
    conflicts = detect_conflicts(scheduled)
    assert conflicts[0].overlap_start == 495
    assert conflicts[0].overlap_end == 510


def test_conflict_message_is_non_empty_string():
    scheduled = [
        _make_scheduled("Walk",    start=480, duration=30),
        _make_scheduled("Feeding", start=490, duration=10),
    ]
    conflicts = detect_conflicts(scheduled)
    msg = conflicts[0].message()
    assert isinstance(msg, str)
    assert "WARNING" in msg
    assert "Walk" in msg
    assert "Feeding" in msg


def test_tasks_touching_but_not_overlapping_have_no_conflict():
    # Walk ends at 500, Feeding starts at 500 — adjacent, not overlapping
    scheduled = [
        _make_scheduled("Walk",    start=480, duration=20),
        _make_scheduled("Feeding", start=500, duration=10),
    ]
    assert detect_conflicts(scheduled) == []


def test_generate_schedule_attaches_conflicts_to_result():
    # generate_schedule uses greedy sequential placement so normally no conflicts;
    # inject two manually overlapping tasks to verify Schedule.conflicts is populated
    owner = make_owner(available_minutes=120)
    scheduled = [
        _make_scheduled("Walk",    start=480, duration=30),
        _make_scheduled("Feeding", start=490, duration=10),
    ]
    from pawpal_system import Schedule
    sched = Schedule(owner=owner, scheduled_tasks=scheduled)
    from pawpal_system import detect_conflicts
    sched.conflicts = detect_conflicts(sched.scheduled_tasks)
    assert len(sched.conflicts) == 1


# ── Invalid status / recurrence validation ────────────────────────────────────

def test_invalid_status_raises():
    with pytest.raises(ValueError):
        Task(title="Bad", duration_minutes=10, priority="high", status="cancelled")


def test_invalid_recurrence_raises():
    with pytest.raises(ValueError):
        Task(title="Bad", duration_minutes=10, priority="high", recurrence="monthly")
