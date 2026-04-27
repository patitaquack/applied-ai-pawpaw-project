# PawPal+

Production-grade daily pet care planner built with Streamlit. Supports multiple pets,
rule-based task suggestions, greedy-gap scheduling, conflict detection, and daily/weekly views.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER (browser)                             │
│   Fills in owner name · adds pets · adds/edits tasks · sets time    │
└────────────────────────────┬────────────────────────────────────────┘
                             │  HTTP (Streamlit)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        app.py  (Streamlit UI)                       │
│                                                                     │
│  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐   │
│  │  Pet Profile │  │   Add Tasks    │  │    Today's Plan       │   │
│  │  tab         │  │   tab          │  │    tab                │   │
│  │              │  │                │  │                       │   │
│  │ Owner form   │  │ Quick Suggest  │  │ Preview → Finalize    │   │
│  │ Add Pet form │  │ Manual form    │  │ Replan controls       │   │
│  └──────┬───────┘  └───────┬────────┘  └──────────┬────────────┘   │
│         │                  │                       │               │
│         ▼                  ▼                       ▼               │
│  session_state.pets  session_state.tasks   session_state.schedule  │
└──────┬──────────────────────┬────────────────────────┬─────────────┘
       │                      │                        │
       ▼                      ▼                        ▼
┌─────────────┐   ┌───────────────────────┐   ┌──────────────────────┐
│ suggestions │   │      scheduler.py     │   │   notifications.py   │
│ .py         │   │                       │   │                      │
│             │   │ 1. filter (pending)   │   │ check_overdue()      │
│ Rule-based  │   │ 2. expand_recurring() │   │ check_upcoming()     │
│ task recs   │   │ 3. anchor + gap-fill  │   │ check_deadline_      │
│ per species │   │ 4. detect_conflicts() │   │   warnings()         │
│ size, age   │   │ 5. build reasons      │   │                      │
└─────────────┘   └──────────┬────────────┘   └──────────────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │    Schedule object  │  ← human reviews Preview
                  │    (models.py)      │    before Finalize
                  │                     │
                  │  scheduled_tasks[]  │
                  │  skipped_tasks[]    │
                  │  conflicts[]        │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │    database.py      │
                  │    (SQLite)         │
                  │                     │
                  │  owners table       │
                  │  pets table         │
                  │  tasks table        │
                  └─────────────────────┘

Data flow:  Input → Suggestions → Task Queue → Scheduler → Preview
            → [Human approves] → Finalized Schedule → Notifications
```

### Component Roles

| File | Role |
|---|---|
| `app.py` | Streamlit UI, session state, page routing |
| `models.py` | Dataclasses: `Task`, `Pet`, `Owner`, `Schedule`, `ScheduledTask` |
| `scheduler.py` | Greedy-gap scheduling algorithm + conflict detection |
| `suggestions.py` | Rule-based task recommendations (species / size / age / lifestyle) |
| `notifications.py` | Overdue, deadline, and upcoming-task alerts |
| `database.py` | SQLite persistence (owners, pets, tasks) |
| `logger.py` | Centralized logging to `pawpal.log` + stderr |

### Human-in-the-Loop Checkpoints

1. **Quick Suggestions preview** — user reviews recommended tasks before adding them to the queue.
2. **Schedule Preview** — full schedule shown before "Finalize"; user can cancel or adjust.
3. **Conflict warnings** — shown inline; user decides whether to replan or proceed.
4. **Replan controls** — user can adjust available time and regenerate at any point.

---

## Setup

### Prerequisites

- **Python 3.10 or higher** (tested on 3.12)
- pip

### 1. Clone the repo

```bash
git clone <repo-url>
cd applied-ai-pawpaw-project
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` in your browser.

### 5. Run the tests

```bash
pytest test_scheduler.py -v
```

All 47 tests should pass.

---

## Logging

Every run appends to `pawpal.log` in the project directory.

```
2026-04-26 10:00:01 [INFO]  scheduler — generate_schedule | owner=Jordan available=120 min tasks=8 day_start=480
2026-04-26 10:00:01 [INFO]  scheduler — generate_schedule | result: scheduled=7 skipped=1 conflicts=0
2026-04-26 10:00:01 [WARNING] scheduler — SKIPPED anchored task 'Evening walk' — Preferred time 6:00 PM is outside today's window
```

- **DEBUG** — all DB reads/writes, schedule internals
- **INFO** — schedule generation, pet/task saves
- **WARNING** — skipped tasks, conflicts, missing records
- **ERROR** — exceptions caught in the UI (full traceback in log)

---

## Project Structure

```
applied-ai-pawpaw-project/
├── app.py              # Streamlit UI entry point
├── models.py           # Core dataclasses
├── scheduler.py        # Scheduling algorithm
├── suggestions.py      # Rule-based task suggestions
├── notifications.py    # Overdue / deadline alerts
├── database.py         # SQLite persistence layer
├── logger.py           # Logging configuration
├── main.py             # CLI demo (no Streamlit required)
├── test_scheduler.py   # pytest suite (47 tests)
├── requirements.txt    # Python dependencies
└── pawpal.log          # Runtime log (auto-created)
```

---

## Sample Interactions

**Add a dog named Mochi (medium, adult, active):**
1. Open **Pet Profile** tab → fill Owner name → Save Owner
2. Add pet: name=Mochi, species=dog, size=medium, age=adult → Add Pet Profile
3. Open **Add Tasks** → Quick Suggestions → select Mochi → Preview → Add suggestions

**Generate today's schedule:**
1. Set available time (e.g. 180 min), day starts at 8
2. Click **Preview Full Schedule** → review tasks + conflicts
3. Click **Finalize & View Schedule** → redirects to daily plan page

**Weekly view:**
1. Add Tasks tab → **Create weekly schedule** → redirects to 7-day view

---

## Design Decisions

- **In-memory session state, not DB-backed UI** — Streamlit's rerun model makes SQLite
  reads on every interaction expensive. Session state holds the live view; `database.py`
  is available for persistence/export but not wired to the live UI to keep latency low.
- **Greedy gap-fill, not optimal** — Anchored tasks lock their preferred time; floating
  tasks fill gaps left-to-right by priority. This is O(n²) worst case but fast enough
  for realistic pet-care task counts (<50) and produces explainable schedules.
- **Conflicts reported, not prevented** — The scheduler never raises on conflicts.
  `ConflictWarning` objects are returned and displayed so the owner can decide how to respond.
- **Rule-based suggestions, not LLM** — `suggestions.py` uses deterministic rules keyed
  on species/size/age/lifestyle. This makes outputs reproducible and testable without
  API keys or network access.
