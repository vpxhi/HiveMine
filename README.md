# HiveMine

### A peer-coordinated multi-agent warehouse digital twin

HiveMine is a reproducible warehouse digital twin built for the **Neptune North Challenge at GreatUniHack**. Its five robot agents negotiate fulfillment work over a simulated peer network, navigate a shared 20 × 20 warehouse, and continue using their local knowledge when communication links fail.

The central demonstration is operational: run normal work, partition the robot network, observe local task decisions and progress, then reconnect the robots and inspect reconciliation. This is an in-process communication simulation, not a controller for physical robots.

## Quick start

Python 3.10+ · Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run warehouse_sim/dashboard.py
```

Open http://localhost:8501. To run the command-line simulation:

```powershell
python -m warehouse_sim.main --ticks 200
python -m warehouse_sim.main --ticks 200 --shock
python -m warehouse_sim.main --demo-network --seed 42
```

Run the test suite:

```powershell
python -m pytest -q
```

## What happens in a tick

```mermaid
flowchart LR
  C[Customer demand] --> O[Order Agent publishes task offer]
  O --> N[Typed peer network]
  N --> R1[Robot 1 local bid]
  N --> R2[Robot 2 local bid]
  N --> R3[Robot 3 local bid]
  N --> R4[Robot 4 local bid]
  N --> R5[Robot 5 local bid]
  R1 & R2 & R3 & R4 & R5 --> A[Reachable peers compare bids]
  A --> X[Robot winner executes task]
  X --> W[Shared physical world commits completion once]
  X --> N
```

The `WarehouseModel` owns the simulation clock, map, physical occupancy, inventory ground truth and outcome metrics. It advances the simulation and renders state; it does not select the robot for ordinary work. Each robot keeps its own position, battery, task memory, bids, claims, event history, neighbours, communication status and decision explanation.

The Order Agent prioritizes orders, resolves SKU locations through Inventory, and publishes task offers. Offers and robot coordination messages use `warehouse_sim/network/`. The Fleet Manager remains for administrative compatibility and existing failure paths, but normal order dispatch does not call its assignment algorithm.

## Decentralised allocation

HiveMine implements a **CBAA-inspired, single-task peer auction**. An eligible idle robot scores a task using `Manhattan distance + 0.12 × (100 − battery %) − 4 for urgent work`. Robots broadcast bids to currently reachable peers. After the one-tick collection window, a robot that has received bids selects the lowest score, with robot ID as a deterministic tie-break, and broadcasts a leased claim. Busy, charging, failed, or low-battery robots do not bid; their local reason is available in the auction details.

This is CBAA-style task bidding, not full CBBA: robots do not build and optimize multi-task bundles, and there is no formal convergence guarantee under arbitrary loss or long partitions. A partition can produce conflicting claims because independent groups cannot observe one another. HiveMine records these conflicts and applies a deterministic score/robot-ID rule when claims meet again.

## Simulated network

`NetworkSimulator` uses a graph with a line of robot peers and an Order Agent connection to Robot 0. Messages have IDs, sender/recipient, typed payloads, creation and expiry ticks, path and delivery status. Routes follow current graph links; a broken path drops the message. The seeded simulator supports:

- link disconnection, two-group partitions and single-robot isolation;
- per-message latency, packet loss, message expiry and reconnection;
- task announcements, bids, claims, completions, status and state-sync messages;
- per-robot local histories, duplicate completion protection and reconciliation logs.

When connectivity returns, robots exchange local task, bid and claim state. Completion is idempotent, and stock is decremented at most once per task. Independent groups can temporarily make conflicting claims; the model does not claim perfect global consistency during a partition.

## Dashboard

HiveMine now opens to a simple three-area product experience:

- **Home** — the interactive Plotly 3D warehouse, Start/Pause/Reset controls, speed, a plain-English activity feed, and a guided walkthrough.
- **Explore** — **Robot Perspective** shows one robot's actual local task, bids, claims, neighbours, delivered messages and recorded decision; the simulator's global task registry is clearly separated for comparison. The alternate **3D Warehouse** mode retains the live map view.
- **Chaos Lab** — split or isolate the peer network, trigger a total blackout, vary latency and packet loss, block an aisle, or fail a robot. Restore network links and inspect actual experiment deltas, a downloadable after-action report and live 3D group state.

The 3D scene shows actual robot positions, planned paths, destinations, delivery task states, shelf racks, packing and charging stations, obstacles and active/broken peer links. Toggle routes, network links and tasks independently. Drag to rotate, scroll to zoom, right-drag to pan, use the camera toggle for a top-down view, or reset the camera from Plotly's toolbar. Robot movement and activity updates follow actual model ticks; Plotly transitions smooth the displayed position changes.

Use **Show me how HiveMine works** for a seven-stage, real-simulation walkthrough, including any observed claim conflict. **START 60-SECOND JUDGE DEMO** runs a repeatable, tick-driven normal/partition/recovery story with pause, continue and replay controls. The Chaos Lab also includes seeded comparison scenarios and JSON run exports.

## Architecture

```mermaid
flowchart TB
  subgraph Shared simulation environment
    M[WarehouseModel: clock, map, physical occupancy, inventory truth, metrics]
    T[Traffic safety service: A-star, CBS, reservations, deadlock monitor]
    I[Inventory: SKU location and idempotent stock commit]
  end
  subgraph Peer network
    O[Order Agent: task offers] --- R0[Robot 0]
    R0 --- R1[Robot 1]
    R1 --- R2[Robot 2]
    R2 --- R3[Robot 3]
    R3 --- R4[Robot 4]
  end
  O -->|task announcement| R0
  R0 -->|bid / claim / status / sync| R1
  R1 --> R2
  R2 --> R3
  R3 --> R4
  R0 & R1 & R2 & R3 & R4 --> T
  R0 & R1 & R2 & R3 & R4 --> M
  I --> M
  M --> D[Streamlit digital twin]
```

The 3D network layer displays robot links; the Order Agent link is a task-source link into Robot 0. The shared traffic safety service still centralizes route reservations and CBS conflict handling. This is a deliberate limitation of the hackathon prototype: task assignment is peer-negotiated, while shared physical safety and inventory accounting remain environmental services.

## Algorithms and safeguards

- A-star for four-directional warehouse routes.
- Conflict-Based Search (CBS) for multi-robot path conflicts and reservations.
- Local distance/battery/urgency bidding with deterministic tie-break.
- Wait-for graph deadlock detection and yielding.
- Finite-state robot control, battery-aware charging and idempotent task completion.
- Seeded message loss and simulation randomness for reproducible scenarios (`--seed`, default 42).

## Limitations

- The graph transport is an in-process simulator, not a real network or ZeroMQ deployment.
- Bid agreement is a small CBAA-inspired auction, not complete CBBA and not guaranteed to converge under arbitrary asynchronous loss.
- A task offer is sourced by the Order Agent through Robot 0. A group cut off from that source can complete known work but may not learn new offers until a state exchange reconnects it.
- Traffic reservation/CBS and inventory truth remain shared safety/environment services.
- Reconciliation is deterministic for received claims; concurrent physical execution may already have progressed before a conflict becomes visible.
- Reconnection is counted as recovered only after the active robots have processed the expected state-sync messages. The measured duration covers that in-process sync exchange, not convergence under every possible asynchronous network.
- Grid movement simplifies acceleration, sensors, turning, payloads, workers and physical safety.

## Project layout

```text
warehouse_sim/
  agents/       customer, order, inventory, robots, fleet, traffic, charging
  algorithms/   A-star, CBS and legacy scoring utilities
  network/      typed messages and deterministic graph transport
  tests/        algorithm, recovery, network and integration tests
  model.py      shared physical world and simulation lifecycle
  dashboard.py  three-area Streamlit experience and controls
  visualization/  Plotly 3D warehouse scene from live model state
  events.py     warehouse and communication disruptions
```

For the judge walkthrough, see [PROJECT_SHOWCASE_GUIDE.md](PROJECT_SHOWCASE_GUIDE.md).
