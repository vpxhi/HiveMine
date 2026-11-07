# HiveMine — Known Limitations

## Architecture and claims

- HiveMine is a single-process Python simulation. The simulated graph transport is not a real distributed deployment, production network, or multi-machine agent system.
- Task selection is peer-negotiated using a CBAA-inspired **single-task** auction. It is not full CBBA bundle consensus and does not guarantee agreement or global convergence under every partition, asynchronous delay, or packet-loss pattern.
- A disconnected component can only act on work and messages it already knows. Different components may claim the same work. Reconnection reconciles updates that are actually exchanged; it cannot undo work already performed in parallel.
- Physical safety is not fully decentralized. The shared traffic controller maintains reservations and runs CBS/deadlock handling; the model owns the global grid and occupancy. Inventory ground truth and task completion accounting are also shared services. Stock decrement is idempotent, but inventory is not a replicated transactional system during a blackout.
- Robot policies are rule-based scores and state machines. There is no trained machine-learning model, LLM, or general-purpose AI planner in this implementation.
- The model does not control physical robots. Movement omits real sensors, acceleration, turning radius, payload dynamics, human workers, networking hardware, and certified machinery safety.

## Safety, recovery and workload

- Collision avoidance and route reservations passed the included tests and 24 seeded stress cases without recorded collisions. That evidence is bounded to these simulator scenarios; it is not a guarantee of collision-free behavior for every input or in a physical warehouse.
- An immobile failed robot in an aisle is treated as a blocked cell and live routes are replanned. The shared packing station remains usable if a failed robot is on it because the simulator models that work cell as shareable; this is an abstraction, not a physical extraction plan.
- Deadlock injection is deliberately conditional. It needs two idle robots with no current task, no charger reservation, and a clear test corridor. Under heavy work it may return an error instead of teleporting active or charging robots. In the audited seed-42 shock CLI run, the tick-170 deadlock injection was skipped safely for this reason.
- With five robots, two docks, finite battery and changing stock, tasks can remain pending or incomplete within a finite run. The simulator does not promise every order will complete under arbitrary workload or failure.
- When an owner lease expires and no live robot is executing or holding a claim, the shared order queue re-offers the task. This is shared service behavior and does not make the robot auction globally consistent during a partition.
- Reconciliation completion means the modeled active robots processed the expected state-sync messages. It is a finite simulation counter, not a proof of consensus for all possible network executions.

## UI and runtime verification limits

- The system Python available in the audit environment lacked Mesa and pytest, and network access to PyPI was blocked. The project `.venv` already contained the requirements and was used for the passing test, CLI, AppTest and Streamlit checks.
- The Streamlit server and HTTP health/root endpoints returned 200. AppTest covered key interactions, but a real browser screenshot, projector check, and visual overflow review at a measured laptop resolution were unavailable.
- AppTest exercised the export-button paths without opening a browser save dialog or verifying a file on disk.

## Licensing and attribution

- The repository has an MIT `LICENSE` naming `vpxhi`. Do not interpret that as a license grant for Mesa, Streamlit, Plotly, NumPy, pandas, or other third-party dependencies; each dependency retains its own license terms.
- The tracked project tree contains no obvious vendored dependency source, but this audit did not establish provenance or permission for every existing project file and contribution. Existing author/owner comments are attribution clues, not proof of licensing authority.
- Before redistribution, verify contributor permissions for the project code and preserve the relevant third-party license and notice texts required by each dependency.
