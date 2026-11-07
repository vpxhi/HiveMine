"""Interactive Plotly 3D warehouse scene built from live simulation state."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import plotly.graph_objects as go


PALETTE = {
    "blue": "#76A9FF",
    "green": "#68D8A2",
    "amber": "#F0BD68",
    "red": "#EF7884",
    "purple": "#B5A0FF",
    "muted": "#738096",
    "floor": "#1B2330",
    "line": "#354153",
    "rack": "#68788A",
    "product": "#C5A575",
}


def _box(
    fig: go.Figure,
    center: Tuple[float, float, float],
    size: Tuple[float, float, float],
    color: str,
    name: str,
    hover: str,
    opacity: float = 1.0,
) -> None:
    """Add a shaded cuboid as a mesh."""
    cx, cy, cz = center
    dx, dy, dz = size
    x = [cx-dx/2, cx+dx/2, cx+dx/2, cx-dx/2, cx-dx/2, cx+dx/2, cx+dx/2, cx-dx/2]
    y = [cy-dy/2, cy-dy/2, cy+dy/2, cy+dy/2, cy-dy/2, cy-dy/2, cy+dy/2, cy+dy/2]
    z = [cz-dz/2, cz-dz/2, cz-dz/2, cz-dz/2, cz+dz/2, cz+dz/2, cz+dz/2, cz+dz/2]
    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4]
    k = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7]
    fig.add_trace(go.Mesh3d(x=x, y=y, z=z, i=i, j=j, k=k, color=color,
                            opacity=opacity, flatshading=True, name=name,
                            hovertemplate=hover + "<extra></extra>", lighting={"ambient": 0.72, "diffuse": 0.68, "specular": 0.12, "roughness": 0.9},
                            showlegend=False))


def _line_trace(fig: go.Figure, points: List[Tuple[float, float, float]], color: str,
                width: float = 1, dash: str = "solid", name: str = "") -> None:
    xs: List[Any] = []
    ys: List[Any] = []
    zs: List[Any] = []
    for x, y, z in points:
        xs.append(x); ys.append(y); zs.append(z)
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", name=name,
                               line={"color": color, "width": width, "dash": dash},
                               hoverinfo="skip", showlegend=False))


def build_warehouse_scene(model: Any, selected_robot: int = 0, top_down: bool = False) -> go.Figure:
    """Build a navigable 3D scene from current robot, route and network state."""
    state = model.get_grid_state()
    network = model.network
    fig = go.Figure()

    # Warehouse floor and fine aisle guides.
    _box(fig, (9.5, 9.5, -0.12), (20, 20, 0.24), PALETTE["floor"], "Warehouse floor", "Warehouse floor")
    grid_points = []
    for cell in range(21):
        grid_points.extend([(cell - 0.5, -0.5, 0.015), (cell - 0.5, 19.5, 0.015), (None, None, None)])
        grid_points.extend([(-0.5, cell - 0.5, 0.015), (19.5, cell - 0.5, 0.015), (None, None, None)])
    _line_trace(fig, grid_points, "#283443", 1, name="Aisle grid")
    boundary = [(-0.5,-0.5,0.04),(19.5,-0.5,0.04),(19.5,19.5,0.04),(-0.5,19.5,0.04),(-0.5,-0.5,0.04),
                (-0.5,-0.5,3.4),(19.5,-0.5,3.4),(19.5,19.5,3.4),(-0.5,19.5,3.4),(-0.5,-0.5,3.4),
                (None,None,None),(-0.5,-0.5,0.04),(-0.5,-0.5,3.4),(None,None,None),
                (19.5,-0.5,0.04),(19.5,-0.5,3.4),(None,None,None),
                (19.5,19.5,0.04),(19.5,19.5,3.4),(None,None,None),
                (-0.5,19.5,0.04),(-0.5,19.5,3.4)]
    _line_trace(fig, boundary, "#455164", 2, name="Warehouse boundary")

    # Storage racks: a clear dark frame with warm product bins.
    for index, (x, y) in enumerate(state["shelf_locations"]):
        label = chr(65 + index)
        _box(fig, (x, y, 0.76), (0.88, 0.92, 1.5), PALETTE["rack"], f"Shelf {label}", f"Shelf {label} · stocked items")
        _box(fig, (x, y - 0.49, 0.68), (0.52, 0.07, 0.36), PALETTE["product"], f"Shelf {label} bin", f"Shelf {label} product bin")
        if index % 2 == 0:
            _box(fig, (x, y - 0.49, 1.14), (0.52, 0.07, 0.24), "#90A3B6", f"Shelf {label} upper bin", f"Shelf {label} product bin")

    # Pack-and-charge stations are distinct and raised from the floor.
    px, py = state["packing_station"]
    _box(fig, (px, py, 0.33), (1.6, 1.3, 0.65), PALETTE["green"], "Packing station", "Packing station · delivery handoff")
    fig.add_trace(go.Scatter3d(x=[px], y=[py], z=[0.78], mode="text", text=["PACK"],
                               textfont={"size": 11, "color": "#DDF8EA"}, hoverinfo="skip", showlegend=False))
    for index, (x, y) in enumerate(state["charging_docks"]):
        _box(fig, (x, y, 0.18), (1.25, 1.0, 0.36), PALETTE["amber"], f"Charging dock {index+1}", f"Charging dock {index+1}")
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[0.43], mode="text", text=["CHARGE"],
                                   textfont={"size": 9, "color": "#FFF0D2"}, hoverinfo="skip", showlegend=False))

    for x, y in state["blocked_cells"]:
        _box(fig, (x, y, 0.35), (0.9, 0.9, 0.7), PALETTE["red"], "Blocked aisle", "Blocked aisle · route unavailable")

    # Robot positions, routes and destinations are taken from the real model.
    robot_positions = {rid: tuple(robot["pos"]) for rid, robot in state["robots"].items()}
    active_edges = {frozenset((int(a.split("-")[1]), int(b.split("-")[1])))
                    for a, b in ((a, b) for a, peers in network.adjacency.items()
                                 for b in peers if a.startswith("Robot-") and b.startswith("Robot-") and a < b)}
    for rid in range(len(robot_positions) - 1):
        edge = frozenset((rid, rid + 1))
        a = robot_positions[rid]; b = robot_positions[rid + 1]
        if edge in active_edges:
            _line_trace(fig, [(a[0], a[1], 1.35), (b[0], b[1], 1.35)], "#78C6B5", 3, name="Robots connected")
        elif network.partition_count > 1:
            _line_trace(fig, [(a[0], a[1], 1.35), (b[0], b[1], 1.35)], PALETTE["red"], 2, "dash", "Connection interrupted")

    group_colors = [PALETTE["blue"], PALETTE["purple"], PALETTE["amber"], "#DB9BEA", "#7DD4D0"]
    for rid, robot in state["robots"].items():
        x, y = robot["pos"]
        group = sorted(network.connected_robot_ids(rid))
        group_index = min(group) if group else rid
        color = group_colors[group_index % len(group_colors)] if network.partition_count > 1 else PALETTE["blue"]
        if robot["status"] == "FAILED": color = PALETTE["red"]
        elif robot["status"] in ("CHARGING", "NEEDS_CHARGE"): color = PALETTE["amber"]
        elif robot["status"] in ("PICKING", "DROPPING"): color = PALETTE["green"]
        _box(fig, (x, y, 0.4), (0.78, 0.62, 0.4), color, f"Robot {rid+1:02d}",
             f"Robot {rid+1:02d} · {robot['status'].replace('_', ' ').title()} · Battery {robot['battery']:.0f}%")
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[0.68], mode="text", text=[f"R{rid+1:02d}"],
                                   textfont={"size": 12, "color": "#F4F6FA"}, hoverinfo="skip", showlegend=False))
        path = robot["path"]
        if path:
            _line_trace(fig, [(p[0], p[1], 0.16) for p in path], color, 4,
                        "dash" if robot["communication"] == "ISOLATED" else "solid", f"Robot {rid+1:02d} route")
            if len(path) > 1:
                dx, dy = path[1][0] - x, path[1][1] - y
                fig.add_trace(go.Cone(x=[x], y=[y], z=[0.88], u=[dx], v=[dy], w=[0],
                                      anchor="tail", sizemode="absolute", sizeref=0.45,
                                      colorscale=[[0, color], [1, color]], showscale=False,
                                      hoverinfo="skip", showlegend=False))
        if robot["destination"]:
            dx, dy = robot["destination"]
            fig.add_trace(go.Scatter3d(x=[dx], y=[dy], z=[0.18], mode="markers",
                                       marker={"symbol": "x", "size": 9, "color": color, "line": {"width": 3}},
                                       name=f"Robot {rid+1:02d} destination",
                                       hovertemplate=f"Robot {rid+1:02d} destination<extra></extra>", showlegend=False))
        if rid == selected_robot:
            fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[0.93], mode="markers",
                                       marker={"size": 21, "color": color, "opacity": 0.18},
                                       hoverinfo="skip", showlegend=False))

    eye = {"x": 0.0, "y": 0.02, "z": 2.7} if top_down else {"x": 1.55, "y": -1.85, "z": 1.45}
    fig.update_layout(
        height=650,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="#111722",
        scene={
            "bgcolor": "#111722",
            "xaxis": {"range": [-1.2, 20.2], "visible": False},
            "yaxis": {"range": [-1.2, 20.2], "visible": False},
            "zaxis": {"range": [-0.4, 3.6], "visible": False},
            "aspectmode": "manual", "aspectratio": {"x": 1, "y": 1, "z": 0.26},
            "camera": {"eye": eye, "center": {"x": 0, "y": 0, "z": -0.16}},
            "uirevision": "hivemine-camera-top" if top_down else "hivemine-camera-angle",
        },
        transition={"duration": 420, "easing": "cubic-in-out"},
        showlegend=False,
    )
    return fig
