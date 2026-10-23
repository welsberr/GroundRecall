"""Cooperative inter-process locks for canonical store writes and updates."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator

try:  # pragma: no branch - selected by platform
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]

try:  # pragma: no branch - selected by platform
    import msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    msvcrt = None  # type: ignore[assignment]


class StoreLockError(RuntimeError):
    """Raised when the platform cannot safely coordinate store updates."""


def _lock_path(store_dir: str | Path) -> Path:
    store = Path(store_dir).resolve(strict=False)
    return store.parent / f".{store.name}.groundrecall.lock"


@contextmanager
def store_lock(store_dir: str | Path, *, exclusive: bool) -> Iterator[None]:
    """Lock a store against cooperating writers or an update operation.

    POSIX permits concurrent record saves while updates take an exclusive lock.
    Windows uses an exclusive byte-range lock for both modes. GroundRecall
    processes predating this lock must still be stopped before applying updates.
    """

    if fcntl is not None:
        store = Path(store_dir).resolve(strict=True)
        if not store.is_dir():
            raise StoreLockError(f"store lock target is not a directory: {store}")
        descriptor = os.open(store, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        return

    path = _lock_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    handle = os.fdopen(descriptor, "r+b")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        elif msvcrt is not None:  # pragma: no cover - Windows only
            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:  # pragma: no cover - unsupported platform
            raise StoreLockError("this platform has no supported inter-process store lock")
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows only
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()
