from __future__ import annotations

from drift_communities import graph_viz as gv
from drift_communities import neo


def test_graph_viz_band_and_colors():
    assert gv.drift_band(0.1) == "GREEN"
    assert gv.drift_band(0.5) == "YELLOW"
    assert gv.drift_band(0.9) == "RED"

    assert gv.band_color("GREEN") == gv.GREEN
    assert gv.band_color("YELLOW") == gv.YELLOW
    assert gv.band_color("RED") == gv.RED


def test_edge_color_for_drift_and_scale():
    # Red edge expected for high-drift averages; alpha should be clamped to <= 0.95.
    color = gv.edge_color_for_drift(avg_drift=0.8, alpha=5.0)
    assert "231, 76, 60" in color  # red family
    assert "0.950" in color  # alpha clamped

    assert gv._scale(5.0, 0.0, 10.0, 0.0, 100.0) == 50.0
    assert gv._scale(-1.0, 0.0, 10.0, 0.0, 100.0) == 0.0
    assert gv._scale(11.0, 0.0, 10.0, 0.0, 100.0) == 100.0


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.received = None

    def run(self, q, **params):
        self.received = (q, params)
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def __init__(self, rows):
        self.session_obj = _FakeSession(rows)

    def session(self):
        return self.session_obj


def test_run_cypher_uses_driver(monkeypatch):
    # Ensure params are forwarded and rows are returned unchanged from Neo layer.
    fake_rows = [{"x": 1}, {"x": 2}]
    fake = _FakeDriver(fake_rows)
    monkeypatch.setattr(neo, "neo_driver", lambda: fake)

    out = neo.run_cypher("RETURN 1 AS x", a=1)
    assert out == fake_rows
    assert fake.session_obj.received[1]["a"] == 1
