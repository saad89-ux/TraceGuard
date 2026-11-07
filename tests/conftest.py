"""Global test configuration and fixtures."""

import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no test accesses the network (K3, S9)."""

    def guarded_connect(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Network access is strictly forbidden in tests (S9).")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
