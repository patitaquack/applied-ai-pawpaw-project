from datetime import date
from pawpal_system import Task, Pet, Owner, sort_by_time, generate_schedule


def print_task_list(tasks):
    if not tasks:
        print("  (none)")
    for t in tasks:
        pref = f"  preferred: {t.preferred_start_minute // 60:02d}:00" if t.preferred_start_minute else ""
        print(f"  [{t.status:7}] [{t.priority:6}] [{t.recurrence:11}] due: {t.due_date}  {t.title}{pref}")


def main():
    # ── Setup ──────────────────────────────────────────────────────────────────
    pet = Pet(name="Mochi", species="dog")
    owner = Owner(name="Jordan", available_minutes=120, pet=pet)

    # Add tasks out of order — mixed recurrences and preferred times
    owner.add_task(Task(
        title="Evening walk", duration_minutes=20, priority="medium",
        pet_name="Mochi", recurrence="daily",
        preferred_start_minute=1080,          # 6 PM
        due_date=date.today(),
    ))
    owner.add_task(Task(
        title="Feeding", duration_minutes=10, priority="high",
        pet_name="Mochi", recurrence="twice_daily",
        preferred_start_minute=480,           # 8 AM
        due_date=date.today(),
    ))
    owner.add_task(Task(
        title="Medication", duration_minutes=5, priority="high",
        pet_name="Mochi", recurrence="daily",
        preferred_start_minute=510,           # 8:30 AM
        due_date=date.today(),
    ))
    owner.add_task(Task(
        title="Bath time", duration_minutes=30, priority="low",
        pet_name="Mochi", recurrence="weekly",
        preferred_start_minute=None,
        due_date=date.today(),
    ))
    owner.add_task(Task(
        title="Grooming", duration_minutes=20, priority="low",
        pet_name="Mochi", recurrence="none",
        preferred_start_minute=None,
        due_date=date.today(),
    ))

    # ── 1. All tasks as added (out of order) ───────────────────────────────────
    print("\n=== All tasks (as added — out of order) ===")
    print_task_list(owner.tasks)

    # ── 2. Sorted by preferred start time ─────────────────────────────────────
    print("\n=== Sorted by preferred start time ===")
    print_task_list(sort_by_time(owner.tasks))

    # ── 3. Filter: pending only ────────────────────────────────────────────────
    print("\n=== Filter: status = pending ===")
    print_task_list(owner.filter_tasks(status="pending"))

    # ── 4. Mark "Feeding" complete — daily, so next occurrence auto-created ────
    print("\n=== Marking 'Feeding' complete (daily recurrence) ===")
    next_task = owner.mark_task_complete("Feeding")
    if next_task:
        print(f"  Next occurrence created: '{next_task.title}' due {next_task.due_date} (status: {next_task.status})")

    # ── 5. Mark "Bath time" complete — weekly, so next due in 7 days ──────────
    print("\n=== Marking 'Bath time' complete (weekly recurrence) ===")
    next_task = owner.mark_task_complete("Bath time")
    if next_task:
        print(f"  Next occurrence created: '{next_task.title}' due {next_task.due_date} (status: {next_task.status})")

    # ── 6. Mark "Grooming" complete — no recurrence, no next task ─────────────
    print("\n=== Marking 'Grooming' complete (no recurrence) ===")
    next_task = owner.mark_task_complete("Grooming")
    print(f"  Next occurrence: {next_task}")  # should print None

    # ── 7. All tasks after completions — shows done + new pending entries ──────
    print("\n=== All tasks after marking completions ===")
    print_task_list(owner.tasks)

    # ── 8. Filter: only pending tasks now ─────────────────────────────────────
    print("\n=== Filter: status = pending (after completions) ===")
    print_task_list(owner.filter_tasks(status="pending"))

    # ── 9. Full generated schedule (pending only) ──────────────────────────────
    print("\n=== Generated schedule for Mochi (pending tasks only) ===")
    schedule = generate_schedule(owner, owner.tasks, day_start_minute=480, pet_name="Mochi")
    print(f"Available: {owner.available_minutes} min | Scheduled: {schedule.total_minutes_scheduled} min\n")
    for st in schedule.scheduled_tasks:
        print(f"  {st.start_time_str()} - {st.end_time_str()}  [{st.task.priority}]  {st.task.title}")
        print(f"    Why: {st.reason}")

    if schedule.skipped_tasks:
        print("\nSkipped:")
        for t in schedule.skipped_tasks:
            print(f"  - {t.title} ({t.duration_minutes} min)")

    if schedule.conflicts:
        print("\nConflicts:")
        for a, b in schedule.conflicts:
            print(f"  ! '{a}' overlaps with '{b}'")
    else:
        print("\nNo conflicts.")


if __name__ == "__main__":
    main()
