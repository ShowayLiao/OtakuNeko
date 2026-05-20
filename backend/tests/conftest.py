import os
import tempfile
import pytest


@pytest.fixture(scope="function")
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="checkpoints_")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass
    for suffix in ("-shm", "-wal"):
        wal_path = path + suffix
        try:
            os.unlink(wal_path)
        except OSError:
            pass
