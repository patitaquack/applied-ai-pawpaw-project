from datetime import date
from typing import List


def _task(title, duration, priority, category, recurrence, preferred=None, notes=""):
    return {
        "title": title,
        "duration_minutes": duration,
        "priority": priority,
        "category": category,
        "notes": notes,
        "pet_name": "",
        "status": "pending",
        "recurrence": recurrence,
        "preferred_start_minute": preferred,
        "deadline_minute": None,
        "medication_dose": "",
        "instructions": notes,
        "due_date": date.today(),
    }


# Walk durations (minutes) per size, adjusted later for age
_WALK = {
    "small":  {"morning": 15, "evening": 10},
    "medium": {"morning": 25, "evening": 20},
    "large":  {"morning": 40, "evening": 30},
}

_PLAY = {"small": 10, "medium": 15, "large": 20}


def get_suggestions(
    pet_type: str,      # "dog" | "cat"
    size: str,          # "small" | "medium" | "large"  (dogs only)
    age_group: str,     # "puppy" | "adult" | "senior"
    lifestyle: str,     # "active_dog" | "low_energy_dog" | "indoor_cat"
) -> List[dict]:

    if pet_type == "dog":
        return _dog_suggestions(size, age_group, lifestyle)
    return _cat_suggestions(age_group)


# ── Dogs ──────────────────────────────────────────────────────────────────────

def _dog_suggestions(size: str, age_group: str, lifestyle: str) -> List[dict]:
    morning = _WALK[size]["morning"]
    evening = _WALK[size]["evening"]

    if age_group == "puppy":
        morning = min(morning, 15)
        evening = min(evening, 10)
    elif age_group == "senior":
        morning = max(morning - 10, 10)
        evening = max(evening - 5, 5)

    tasks = [
        _task("Feeding",           10, "high",   "feeding",  "twice_daily", preferred=480),
        _task("Fresh water check",  5, "high",   "other",    "twice_daily", preferred=480),
        _task("Morning walk", morning, "high",   "walk",     "daily",       preferred=480),
        _task("Evening walk", evening, "medium", "walk",     "daily",       preferred=1080),
        _task("Potty break",        5, "high",   "other",    "daily"),
    ]

    # Small dogs and puppies need more frequent potty breaks
    if size == "small" or age_group == "puppy":
        tasks.append(_task("Midday potty break", 5, "high", "other", "daily", preferred=720))

    # Puppy-specific
    if age_group == "puppy":
        tasks += [
            _task("Training session",  10, "medium", "playtime", "daily", preferred=600,
                  notes="Keep sessions short and positive"),
            _task("Short play session", 10, "medium", "playtime", "daily"),
        ]

    # Active dog gets more playtime
    if lifestyle == "active_dog":
        tasks.append(
            _task("Playtime / exercise", _PLAY[size], "medium", "playtime", "daily")
        )

    # Grooming for all dogs
    tasks += [
        _task("Brushing",    10, "low", "grooming", "daily"),
        _task("Weekly bath", 30, "low", "grooming", "weekly",
              notes="Check ears and nails while bathing"),
    ]

    # Large dogs need extra exercise
    if size == "large":
        tasks.append(_task("Extra exercise / fetch", 20, "medium", "playtime", "daily"))

    # Senior-specific
    if age_group == "senior":
        tasks += [
            _task("Medication reminder",      5, "high",   "medication", "daily", preferred=510),
            _task("Gentle stretch / rest", 5, "low",    "other",      "daily",
                  notes="Check joints, ensure comfortable resting spot"),
        ]

    return tasks


# ── Cats ──────────────────────────────────────────────────────────────────────

def _cat_suggestions(age_group: str) -> List[dict]:
    tasks = [
        _task("Feeding",                  10, "high",   "feeding",  "twice_daily", preferred=480),
        _task("Fresh water check",         5, "high",   "other",    "daily",       preferred=480),
        _task("Litter box cleaning",       5, "high",   "litter",   "daily"),
        _task("Indoor playtime",          15, "medium", "playtime", "daily"),
        _task("Brushing",                 10, "low",    "grooming", "daily"),
        _task("Window / perch enrichment", 10, "low",   "playtime", "daily",
              notes="Rotate toys, add bird feeder view if possible"),
        _task("Nail trim reminder",       10, "low",    "grooming", "weekly"),
        _task("Weekly litter deep clean", 15, "medium", "litter",   "weekly"),
    ]

    if age_group == "senior":
        tasks.append(
            _task("Medication reminder", 5, "high", "medication", "daily", preferred=510)
        )

    return tasks
