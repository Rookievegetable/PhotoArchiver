"""Atomic export file writes (Phase D, P2-5)."""

import os
from collections.abc import Callable
from pathlib import Path


def write_atomic(target: Path, write_to: Callable[[Path], object]) -> None:
    """Run ``write_to`` against a sibling temp path, then atomically swap it in.

    An interrupted export (crash, power loss, killed process) leaves the
    previous export intact — never a half-written file at the target path.
    The ``.part`` sibling lives on the same volume so ``os.replace`` is
    atomic, and is removed if the write fails.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    try:
        write_to(temp)
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise