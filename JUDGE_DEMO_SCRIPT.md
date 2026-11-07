# HiveMine — 60-Second Judge Demo Script

This walkthrough uses the existing Streamlit simulation and its fixed seed (**42**). The demo advances by normal simulation ticks; it does not sleep or fabricate completions.

## Before the presentation

Start HiveMine from the project virtual environment:

```powershell
.\.venv\Scripts\streamlit.exe run warehouse_sim/dashboard.py
```

Leave the dashboard on **Chaos Lab**. The demo button resets to its own fresh seed-42 model, so no other simulation run is required.

## Walkthrough

| Presentation time | Exact action | What to say or point out |
|---|---|---|
| 0–5 sec | Click **Chaos Lab** in the top navigation. Click **Reset**, then click **Chaos Lab** again. | “This is the same live warehouse simulation, reset to a clean state.” Reset returns navigation to Mission Control, so re-open Chaos Lab. |
| 5–10 sec | Click **START 60-SECOND JUDGE DEMO**. | “The demo starts normal operations using seed 42. The robots receive jobs and exchange bids.” |
| 10–22 sec | Let it run through simulation ticks 8–20. Point at the live 3D map, status badge and activity feed. | “The bids use local distance, battery and urgency data. The robot agents decide from the messages they have received.” |
| 22–42 sec | When the badge changes to **PARTITIONED** (around tick 20), keep the demo running. Point at the separate link groups and **Independent decisions** metric. | “The peer network is split. Robots keep working from local knowledge. The counters report observed decisions and work during the outage.” |
| 42–55 sec | Let it run through tick 45. Point out **Tasks completed during outage** if it has incremented. | “In this seed-42 run, one delivery completed while disconnected. That count comes from the model’s completion events.” |
| 55–60 sec | Wait for **Measured results** and the demo to pause. Point at **Messages delayed or dropped** and **Reconciliation updates completed**. | “After restore, 20 state-sync messages arrived and 7 state merges recorded changes. The UI waits for reconciliation; these are measured outcomes.” |

The application typically reaches the results phase by simulation tick 47 (about 33 seconds at the current 0.7-second fragment interval). Use the remaining time to explain the metrics rather than rushing the story.

## Measured reference outcome

The audited seed-42 run completed at tick 47 with:

- 1 delivery completed during the network outage.
- 2 independent decisions during the outage.
- 189 messages dropped and 0 delayed.
- 20 state-sync messages received after recovery.
- 7 state merges with changes.
- Reconciliation complete.

Use the live displayed values if a software or timing change produces different measurements. Do not quote a completion, conflict, or merge that the current run does not show.

## Pause and replay

- During the active story, click **Pause demo**. Click **Continue demo** to resume.
- Click **Replay demo** to start a fresh seed-42 run. Replay resets the model, event feed, counters, and baseline.
- The integration test compares outage completions, independent decisions, received sync messages, and reconciliation counts across a replay.

The standard operating **Start Simulation**, **Pause**, **Reset**, and **Restore Network** controls remain available outside the scripted demo. Use the Restore Network control for an unscripted Chaos Lab test; the Judge Demo restores itself.
