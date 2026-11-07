# HiveMine Final QA Report

**Audit date:** 7 November 2026  
**Scope:** Existing HiveMine simulation, Streamlit dashboard, seeded judge demo, task/network failure behavior, and repository claims/licensing.

## Executive result

The application is suitable for a **controlled live judge demonstration when run from the repository `.venv`**. The final suite passed, both 200-tick CLI runs exited successfully, the Streamlit server returned HTTP 200, and the seeded stress matrix passed 24/24 scenarios.

Two verified defects were fixed during this audit: a robot failure could leave other robots blocked behind the failed robot, and expired or failed-owner claims could leave global task records stuck as in progress. The deadlock shock was also made safe: it now only repositions two idle robots that have no active task or charging reservation; if it cannot do that safely, it reports that it did not inject the event.

This is a simulation, not a physical robot controller or a production distributed system. The global `python` interpreter in this environment could not install or run the project because it has no network access and lacks the project's dependencies. Use the validated `.venv` interpreter.

## Part A — Environment commands

| Command | Outcome |
|---|---|
| `python -m pip install -r requirements.txt` | **Failed in system Python.** PyPI was unreachable (`WinError 10051`); pip could not resolve `mesa>=3.0`. No package was downloaded. |
| `python -m pytest -q` | **Failed in system Python:** `No module named pytest`. |
| `python -m warehouse_sim.main --ticks 200` | **Failed in system Python:** `No module named mesa`. |
| `python -m warehouse_sim.main --ticks 200 --shock` | **Failed in system Python:** `No module named mesa`. |
| `streamlit run warehouse_sim/dashboard.py` equivalent using `.venv` | **Started successfully.** The server logged its local URL; `/_stcore/health` returned HTTP 200 `ok` and `/` returned HTTP 200. The server was stopped after the check. |

The repository environment already had all requirements installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Result: exit code 0; each direct requirement was reported “already satisfied.” No download was needed.

## Part B — Simulation stress checks

Ran 240 ticks per scenario for seeds **7, 42, and 2026**: 24 reproducible runs total.

| Scenario | Intervention |
|---|---|
| Normal | No injected network failure |
| Partition | Two robot groups from tick 31; restore at tick 101 |
| Blackout | All robot communication split at tick 31; restore at tick 101 |
| Isolation | Robot 2 isolated at tick 31; restore at tick 101 |
| Packet loss | 80% loss from tick 31 to 90 |
| Delayed messages | Five-tick latency from tick 31 to 90 |
| Robot failure | Robot 2 failed at tick 31 |
| Heavy workload | 24 urgent/normal orders queued before the run |

**Result: 24/24 scenarios passed the audited invariants.** Across these runs there were no thrown exceptions, recorded collisions, duplicate task completions, negative stock quantities, charging states away from their assigned docks, or orphaned global `IN_PROGRESS` ownership records at tick 240. Partition, blackout, and isolation cases returned to one connected robot group and completed reconciliation before the end of the run. Completed deliveries ranged from 4 to 12 per scenario; completion of every submitted order is not guaranteed.

The existing suite also checks message paths, delayed delivery across link changes, idempotent completion/stock decrement, conflict resolution, and reconciliation. In particular, the duplicate-completion regression confirms the same task cannot decrement inventory twice.

### Defects fixed

- **Failed robot blocking aisle traffic:** `kill_robot` now marks a failed robot’s aisle cell as blocked and asks the traffic controller to reroute live paths. The shared packing station is deliberately excluded because it is a shared work cell and closing the only packing station would make every delivery impossible. The seed-42 failure regression completes 9 deliveries by tick 240 with no collisions.
- **Stale task ownership:** the model reopens a task in the shared Order Agent queue after there is no live robot executing it and no unexpired claim held by a live robot. Claims from failed robots are ignored during claim receipt and state merge.
- **Unsafe deadlock injection:** the previous fallback could move busy or charging robots. The event now requires two idle robots with no task or charger reservation and a clear test corridor. It returns an error rather than disrupting active work when those conditions are not met.
- **Robot Perspective dataframe warnings:** mixed numeric task IDs and placeholder strings caused Arrow conversion warnings. Message-table task and bid values now use consistent text types.
- **Technical claims:** the README and traffic-controller description now describe peer coordination and collision avoidance without claiming that physical control is fully decentralized or that collisions are impossible.

## Part C — Judge Demo

The Streamlit AppTest workflow starts the demo from a fresh fixed-seed model, pauses, continues, replays, and verifies the replay’s measured counters match. The final seeded run completed at **tick 47** with no Streamlit exceptions:

- Tasks completed during the outage: **1**
- Independent decisions during the outage: **2**
- Messages delayed: **0**
- Messages dropped: **189**
- State-sync messages received after recovery: **20**
- State merges with changes: **7**
- Reconciliation finished: **yes**

These are observed values for seed 42, not preset claims. The demo regression compares the full metric tuple across replay. See [JUDGE_DEMO_SCRIPT.md](JUDGE_DEMO_SCRIPT.md) for the button-by-button walkthrough.

## Part D — UI interaction checks

Streamlit AppTest exercised:

- Start, Pause, Reset, and simulation speed.
- Top-down camera toggle and robot selection from fleet and Explore views.
- Robot Perspective and 3D Warehouse modes.
- Guided walkthrough Next, Previous, Pause/Resume, and Exit.
- Chaos Lab split, isolation, blackout, unstable transport, aisle block, robot failure, and restore controls.
- Judge Demo start, pause, continue, and replay.
- After-action JSON, full evidence JSON, and history CSV download-button clicks.
- Navigation and presentation mode while preserving the same model instance.

The exports were clicked through AppTest and raised no app exceptions. This verifies the export UI path and payload construction, not the browser’s file-save dialog or downloaded file on disk.

## Part E — Technical and licensing review

- Task allocation is peer-negotiated through a seeded in-process graph network. It is not a full CBBA implementation and has no guarantee of consensus under arbitrary partitions or loss.
- Traffic reservations, CBS routing, physical occupancy, the order/task ledger, and inventory accounting remain shared simulation services. Inventory completion is idempotent; physical shelf reservations are not a replicated transactional protocol during a total partition.
- The application uses deterministic scoring, A*, CBS, Mesa agents and seeded random demand. It does not implement a trained learning policy, an LLM, or deployed physical robots.
- The repository contains an MIT `LICENSE` naming `vpxhi`. That license file does not grant rights to third-party packages, and this local audit cannot establish that every carried-forward source contribution is owned by or licensed through that notice. The tracked tree contains no obvious vendored dependency source; installed dependencies remain governed by their own licenses. Confirm contributor permissions and preserve applicable dependency notices before redistribution.

## Part F — Final verification

Final checks executed after the code changes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m warehouse_sim.main --ticks 200
.\.venv\Scripts\python.exe -m warehouse_sim.main --ticks 200 --shock
.\.venv\Scripts\python.exe -m compileall -q warehouse_sim
git diff --check
```

Results: **106 tests passed**; normal CLI exited 0 at 200 ticks with 7 tasks completed and 0 collisions; shock CLI exited 0 at 200 ticks with 6 tasks completed, 1 failed robot, 3 verified recoveries and 0 collisions; compilation passed. The shock CLI could not inject its tick-170 deadlock scenario because fewer than two safe idle robots were available; the event returned an explanatory error and continued safely. `git diff --check` passed with only Git line-ending notices.

### Readiness

**Ready for a controlled judge demonstration using `.venv` and the seeded Judge Demo workflow.** Do not describe the result as a certified collision-free physical robot system, guaranteed consensus, or a complete solution to all orders under every fault pattern. Browser screenshot testing and actual laptop/projector overflow inspection were unavailable; the Streamlit server and controls were checked with HTTP health probes and AppTest instead.
