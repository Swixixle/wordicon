#!/usr/bin/env python3
"""The data root, resolved once at startup and applied to every subsystem
(workspace-v2, slice A).

Before this module, "where does the store live" had three answers:
wordicon_cli's LOCAL_STATE and the forty-odd module-level paths derived
from it at import time; the modules that read cli.LOCAL_STATE at call time
(notebook, gate, library, moira, inquiry, federation, clinic, recovery,
keeper, vault, speech); and three scripts (export, blind, digest) that read
WORDICON_STATE from the environment on their own. The journeys' scratch
server rebased a hand-kept list of fourteen attribute names; the suite
patched what it knew about. A subsystem that derived its path at import
and was not on the list wrote to the real store.

Now: `apply(root)` sets cli.LOCAL_STATE, rebases EVERY Path attribute of
every already-imported module under scripts/ that pointed under the old
root (no hand-kept list — the attribute is found by where it points), and
exports WORDICON_STATE so a child process resolves the same root. The
server calls `apply_from_env()` at import and prints the resolved root in
its banner; in test mode it refuses to serve the repository's own
local_state. Modules imported after `apply` derive from the new root by
construction, because cli.LOCAL_STATE is already the new root when they
load."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV = "WORDICON_STATE"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


_ROOTS_SEEN: set[Path] = set()


def default_root() -> Path:
    return (repo_root() / "local_state").resolve()


def resolve(explicit: str | os.PathLike | None = None) -> Path:
    """The root this process should use: an explicit argument, else
    WORDICON_STATE, else a root the process already chose by hand (a test
    that set cli.LOCAL_STATE before importing the server keeps it — the
    journeys' seeder did exactly that and the first version of this module
    pointed it back at the real store), else the repository's own
    local_state."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get(ENV, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    cli = sys.modules.get("wordicon_cli")
    if cli is not None:
        current = Path(cli.LOCAL_STATE).resolve()
        if current != default_root():
            return current
    return default_root()


def _scripts_modules():
    here = str(Path(__file__).resolve().parent)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and str(Path(f).resolve().parent) == here:
            yield name, mod


def apply(root: str | os.PathLike) -> dict:
    """Point every subsystem at `root`. Returns {module.ATTR: new path} for
    every attribute that was rebased, so a caller can log what moved."""
    import wordicon_cli as cli
    root = Path(root).resolve()
    # Every root a path may still point at: the repository default (where
    # import-time constants are born), every root applied before, and the
    # one the process set by hand. A path under any of them moves.
    sources = {default_root(), Path(cli.LOCAL_STATE).resolve()} | set(_ROOTS_SEEN)
    sources.discard(root)
    rebased: dict[str, str] = {}
    for modname, mod in _scripts_modules():
        for attr, value in list(vars(mod).items()):
            if attr.startswith("__") or not isinstance(value, Path):
                continue
            v = value if value.is_absolute() else (repo_root() / value)
            try:
                v = v.resolve()
            except OSError:
                continue
            for old in sources:
                if v == old:
                    setattr(mod, attr, root)
                    rebased[f"{modname}.{attr}"] = str(root)
                    break
                if old in v.parents:
                    new = root / v.relative_to(old)
                    setattr(mod, attr, new)
                    rebased[f"{modname}.{attr}"] = str(new)
                    break
    cli.LOCAL_STATE = root
    _ROOTS_SEEN.add(root)
    os.environ[ENV] = str(root)
    return rebased


def apply_from_env(explicit: str | os.PathLike | None = None) -> Path:
    root = resolve(explicit)
    apply(root)
    return root


def is_repository_store(root: str | os.PathLike) -> bool:
    return Path(root).resolve() == (repo_root() / "local_state").resolve()


def describe(root: str | os.PathLike) -> str:
    root = Path(root).resolve()
    kind = "the repository's own local_state" if is_repository_store(root) else "an explicit root (WORDICON_STATE)"
    return f"{root} — {kind}"
