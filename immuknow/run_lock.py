"""Keep one writer at a time in each run, with automatic release on process exit."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, SoftFileLock, Timeout


@contextmanager
def run_lock(run_dir: Path) -> Iterator[None]:
    """Refuse a busy run immediately using an operating-system file lock.

    The operating system owns the lock, so an interrupted process cannot leave
    a stale claim. An operation that changes a run must keep its reads and writes
    inside this context.
    """
    if not run_dir.is_dir():
        raise ValueError(f"Run directory does not exist: {run_dir}")
    lock = FileLock(run_dir / ".run.lock", timeout=0, mode=0o600)
    if isinstance(lock, SoftFileLock):
        raise ValueError("This system does not support locking saved runs")
    try:
        lock.acquire()
    except Timeout:
        raise ValueError(
            "This run is in use. Try again when it has finished."
        ) from None
    except NotImplementedError:
        raise ValueError(
            "This filesystem does not support locking saved runs"
        ) from None
    try:
        yield
    finally:
        lock.release()
