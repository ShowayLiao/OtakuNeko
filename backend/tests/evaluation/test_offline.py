"""Offline gates fail before DNS or a socket can reach an external service."""

import asyncio
import socket

import pytest

from app.evaluation.offline import offline_network


def test_blocks_dns_connections_and_restores_methods():
    original = socket.socket.connect
    with offline_network():
        with pytest.raises(RuntimeError, match="network disabled"):
            socket.getaddrinfo("example.invalid", 443)
        with socket.socket() as connection:
            with pytest.raises(RuntimeError, match="network disabled"):
                connection.connect(("127.0.0.1", 443))
            with pytest.raises(RuntimeError, match="network disabled"):
                connection.connect_ex(("127.0.0.1", 443))
    assert socket.socket.connect is original


def test_local_socketpair_for_asyncio_is_allowed_without_unblocking_clients():
    with offline_network():
        first, second = socket.socketpair()
        try:
            first.send(b"x")
            assert second.recv(1) == b"x"
        finally:
            first.close()
            second.close()


@pytest.mark.asyncio
async def test_blocks_async_connections_without_dns():
    with offline_network():
        with pytest.raises(RuntimeError, match="network disabled"):
            await asyncio.get_running_loop().create_connection(
                asyncio.Protocol, "127.0.0.1", 443
            )
