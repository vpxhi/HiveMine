"""The 3D warehouse uses the same positions and network links as the model."""

from warehouse_sim.model import WarehouseModel
from warehouse_sim.visualization.warehouse_3d import build_warehouse_scene
import pytest


def test_3d_scene_tracks_real_robot_positions_routes_and_broken_links():
    model = WarehouseModel(seed=42)
    for _ in range(45):
        model.step()
    robot = model.robots[0]
    fig = build_warehouse_scene(model, selected_robot=0)
    robot_body = next(trace for trace in fig.data if trace.name == "Robot 01")
    assert (sum(robot_body.x) / len(robot_body.x), sum(robot_body.y) / len(robot_body.y)) == pytest.approx(robot.pos_tuple)
    assert any(trace.name == "Shelf A" for trace in fig.data)
    assert any(trace.name == "Packing station" for trace in fig.data)
    if robot.current_path:
        assert any(trace.name == "Robot 01 route" for trace in fig.data)

    model.network.set_partition([[0, 1], [2, 3, 4]])
    partitioned = build_warehouse_scene(model)
    assert any(trace.name == "Connection interrupted" for trace in partitioned.data)
