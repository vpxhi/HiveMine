# HiveMine — Neptune North Challenge Showcase

## Challenge and project thesis

The Neptune North Challenge at GreatUniHack asks teams to demonstrate multiple actors pursuing a shared objective, making independent decisions, and continuing to make progress when communication fails. HiveMine demonstrates those ideas inside a 20 × 20 warehouse digital twin with five robot agents, orders, shelves, a packing station and charging docks.

The project is deliberately explicit about its boundary: agents and communication are simulated in one Python process. It demonstrates distributed decision behavior and network failure modes; it does not operate real warehouse equipment.

## Judge walkthrough (about 4 minutes)

1. **Home:** point out the miniature 3D warehouse, moving robots, routes and the short activity feed. Press **Start Simulation**.
2. **Explore:** select a robot. Explain its current job, destination and battery; open Technical details only if a judge asks how bids or messages work.
3. **Guided walkthrough:** press **Show me how HiveMine works**. Advance through the real task-negotiation and network-failure stages. Use the 20-tick continuation during independent operation to show actual progress.
4. **Experiment:** press **Simulate Network Failure**. The 3D peer links break into two groups while the physical robot routes continue.
5. **Independent operation:** let the simulation run. The activity feed describes local choices; Experiment reports real delivery counts and independent decisions during the outage.
6. **Recovery:** press **Restore Communication**. Keep the simulation running for several ticks so the robots exchange and reconcile their local histories.
7. **Results:** open Advanced settings and show the observed throughput comparison. Export JSON or CSV if judges want run data. Describe only the measurements from this run.

For a deterministic reset, press **Reset**. The model and message-loss random generator use seed 42.

## System roles

### Shared simulation environment

`WarehouseModel` advances the clock and maintains physical position, occupancy, obstacles, inventory ground truth and outcome metrics. It provides sensor observations to the rendered digital twin. It does not allocate ordinary tasks to robots. Physical completion is committed once per task to prevent duplicate messages from decrementing stock twice.

`TrafficControllerAgent` remains a shared traffic safety service for path planning, reservations, CBS conflict resolution and deadlock monitoring. `ChargingAgent` manages shared dock occupancy. Inventory remains the authoritative stock record. These services are shared environmental infrastructure, not peer task-allocation authorities.

### Independent robot agents

Each robot stores its own position, battery, status, current task, local task queue, known task details, bid/claim records, event memory, reachable neighbours, communication status and last decision explanation. In `sense`, it reads local physical state and processes only messages delivered to its inbox. In `decide`, it calculates bids and selects work from locally received bids. In `act`, it follows its route, picks, packs or charges.

The Fleet Manager remains in the code for monitoring compatibility and legacy recovery paths. Ordinary task allocation bypasses it.

## Network and task negotiation

`warehouse_sim/network/messages.py` defines typed message kinds and envelopes. `NetworkSimulator` represents links as a graph, finds a route at send time, queues the message for its delivery tick, and enforces link availability, delay, seeded packet loss and TTL. Messages that have no route or lose a link in transit are dropped. They do not teleport to disconnected peers.

The initial graph connects five robots in a line; Order Agent connects to Robot 0 as the task source. A broadcast is routed only to peers reachable in the current topology. Each network partition has only the announcements, bids, claims and history it actually received.

The task auction is **inspired by CBAA**, not a complete CBBA implementation:

1. Order Agent publishes the task ID, shelf, quantity and urgency.
2. Each eligible robot locally scores distance, battery, urgency and current workload.
3. Robots broadcast bids to reachable peers.
4. After a one-tick collection window, each robot that has received bids selects the minimum score, with robot ID as the stable tie-break.
5. The winner broadcasts a claim with a lease horizon and executes the task.
6. A disconnected group can issue a conflicting claim because it cannot observe the other group. On reconnection, agents exchange state and resolve observed claims by `(bid score, robot ID)`.

The method is a single-task auction. It does not optimize CBBA bundles or guarantee global convergence during arbitrary message loss. A component separated from the Order Agent's source can work on offers it already knows; new offers wait until that component can receive them.

## Recovery semantics

Fault injection and fault recovery are separate. Event injection marks an event as `injected` or `recovery_in_progress`; it does not increment `shocks_recovered`. A recovery is counted only after the model observes the associated condition, such as a safe reroute, completed charging, a pending reassignment or a reconciled partition. Network state synchronization is visible through `state_reconciled` and `reconnection_reconciliation_started` messages.

During a partition, each robot continues its current state machine and may claim tasks from its local view. Perfect consistency is not promised. Task IDs are unique, completion is idempotent, and stock updates occur only once. Duplicate claims and unresolved work are visible so the audience can discuss the tradeoff between availability and global agreement.

## Dashboard map

| Page | Demonstration purpose |
|---|---|
| Home | Watch the 3D warehouse, control the simulation, read the activity feed, launch the guided walkthrough |
| Explore | Inspect each robot's activity and optional local state/message details |
| Experiment | Apply communication failures, restore links, try other warehouse disruptions, and inspect measured outcomes |

The scene uses Plotly 3D meshes and coordinates from `WarehouseModel.get_grid_state()`. Routes, destinations, robot positions and network edges are model state. Camera rotation, zoom, pan and top-down/angled views are interactive; camera reset is available from the Plotly toolbar.

## Measures available

Operational counters include completed and pending tasks, battery, utilization, collision count, deadlocks and verified recovery count. Network counters include messages sent/delivered/dropped/delayed, active links, disconnected robots, components and disconnected ticks. Resilience counters include completed work during partitions, independent decisions, detected claim conflicts and reconciliation activity. These values are read from simulation events and state; the showcase should report the observed run rather than prewritten demo totals.

## Install, run and verify

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run warehouse_sim/dashboard.py
```

CLI and tests:

```powershell
python -m warehouse_sim.main --ticks 200 --shock
python -m pytest -q
```

## Technical limits to explain honestly

- This is a deterministic in-process graph transport. It does not run agents on separate machines or use a production transport.
- The task auction is a small CBAA-inspired peer auction, not a full CBBA bundle consensus implementation.
- The shared traffic controller retains path reservations and CBS safety coordination; that subsystem is not decentralized.
- Inventory is shared ground truth. Idempotent completion avoids double decrements, but physical shelf reservation during a complete partition is not a replicated transactional inventory protocol.
- Concurrent groups may execute before learning of a duplicate claim. The demo exposes that conflict and reconciles observable state; it does not claim perfect consistency.
- Grid routes abstract away physical robot dynamics, human workers, sensors and certified machinery safety.

## Suggested closing statement

“HiveMine's robots do not wait for a fleet authority to select every task. They bid using local knowledge and coordinate over links that can fail. A partition may cause conflicting claims because agents cannot know what isolated peers are doing; after reconnection they exchange histories and resolve the conflicts they can observe. The simulation makes both the progress and the consistency cost visible.”
