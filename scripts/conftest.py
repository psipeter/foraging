import pytest

import costs


@pytest.fixture(autouse=True)
def free_motion(request, monkeypatch):
    """The simulator tests state their timing in walking and fruit seconds, so by default turning and key presses are free
    (an infinite turn rate, no overhead, no presses; an action that then takes no time is refused). A test of the motor costs themselves is marked `motor_costs` and runs
    with the real constants in costs.py."""
    if request.node.get_closest_marker("motor_costs") is None:
        monkeypatch.setattr(costs, "TURN_RATE", float("inf"))
        monkeypatch.setattr(costs, "TURN_OVERHEAD", 0.0)
        monkeypatch.setattr(costs, "WALK_PRESS_TIME", 0.0)
        monkeypatch.setattr(costs, "HARVEST_PRESS_TIME", 0.0)


def pytest_configure(config):
    config.addinivalue_line("markers", "motor_costs: run with the real turning and key-press costs (costs.py)")
