import pytest


@pytest.fixture(autouse=True)
def keine_wartezeit(monkeypatch):
    """Pausen zwischen Märkten und Wiederholungen sind in Tests ohne Wirkung."""
    monkeypatch.setattr("buchbot.pipeline.time.sleep", lambda seconds: None)
