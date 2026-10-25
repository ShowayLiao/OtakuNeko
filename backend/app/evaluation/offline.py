"""Process-local network guard for sequential, deterministic offline gates."""

import asyncio
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import socket
from unittest.mock import patch


def _blocked(*args, **kwargs):
    raise RuntimeError("network disabled in offline Agent gate")


async def _async_blocked(*args, **kwargs):
    _blocked()


@contextmanager
def offline_network():
    """Block outbound sockets and DNS; ASGI and in-memory SQL need neither.

    This guard is intentionally process-wide; use a dedicated gate process,
    never install it in the application's serving process.
    """
    # Windows implements socketpair() with a private loopback connection.
    # Permit only the stdlib socketpair call, never general loopback clients.
    in_socketpair: ContextVar[bool] = ContextVar("offline_socketpair", default=False)
    original_pair = socket.socketpair
    original_connect = socket.socket.connect

    def private_pair(*args, **kwargs):
        token = in_socketpair.set(True)
        try:
            return original_pair(*args, **kwargs)
        finally:
            in_socketpair.reset(token)

    def connect(connection, address):
        if (
            in_socketpair.get()
            and isinstance(address, tuple)
            and address[0]
            in {
                "127.0.0.1",
                "::1",
            }
        ):
            return original_connect(connection, address)
        return _blocked()

    with ExitStack() as stack:
        stack.enter_context(patch("socket.socketpair", private_pair))
        stack.enter_context(patch("socket.socket.connect", connect))
        for target in (
            "socket.socket.connect_ex",
            "socket.socket.sendto",
            "socket.create_connection",
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyname_ex",
            "socket.gethostbyaddr",
        ):
            stack.enter_context(patch(target, _blocked))
        stack.enter_context(
            patch.object(asyncio.BaseEventLoop, "create_connection", _async_blocked)
        )
        stack.enter_context(
            patch.object(
                asyncio.BaseEventLoop, "create_datagram_endpoint", _async_blocked
            )
        )
        yield
