"""`meno` — the instance entrypoint (I0b). Scaffold, run, and inspect a home-bound
instance. Wired as `[project.scripts] meno = "meno.cli:main"`.

    meno init <home> [--handle NAME]   # scaffold an instance home
    meno run  <home> [--cycles N]      # run the daemon (bound to the home)
    meno status <home>                 # print run/status.json
"""
from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path
from typing import List, Optional

from .home import build_instance, init_home


def run_instance(home, *, max_cycles: Optional[int] = None, status_every: int = 4,
                 save_every: int = 32, feed: Optional[List[str]] = None,
                 sleep=time.sleep, idle_sleep: float = 0.2):
    """Bind to a home and drive its loop. Holds the home's advisory lock (two daemons
    must not race on one substrate). Persists `run/status.json` periodically AND the
    substrate periodically (`save_every`) — not only on shutdown — so a crash/kill
    resumes from a recent point, not the seed (D12). Stops on `max_cycles`, SIGINT, or
    SIGTERM.

    Two modes (D27): a bounded run (`max_cycles`) uses the deterministic single-thread
    step loop (tests, one-shots). The UNBOUNDED daemon uses `driver.start()` — the
    background loop + the off-thread outbound worker — so a slow network call from an
    efferent adapter never blocks cognition (the reason I0a built the worker)."""
    inst = build_instance(home)
    if not inst.acquire_lock():
        raise RuntimeError(f"{inst.lock_path} is held by another live instance — refusing to start")
    for text in (feed or []):
        inst.mind.feed(text)
        inst.mind.run_until_quiescent()

    stop = {"flag": False}

    def _handler(*_):
        stop["flag"] = True
    try:                              # signals only install in the main thread
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        pass

    try:
        if max_cycles is None:
            # unbounded daemon: background loop + off-thread outbound worker
            inst.driver.start()
            try:
                while not stop["flag"]:
                    sleep(idle_sleep)
                    inst.write_status()
            finally:
                inst.driver.stop()
        else:
            n = 0                     # bounded: deterministic single-thread step loop
            while not stop["flag"] and n < max_cycles:
                inst.driver.step()
                n += 1
                if status_every and n % status_every == 0:
                    inst.write_status()
                if save_every and n % save_every == 0:
                    inst.save()
    finally:
        inst.write_status()
        inst.save()                   # sleep, not amnesia
        inst.release_lock()
    return inst


def cmd_init(args) -> int:
    home = init_home(args.home, handle=args.handle)
    print(f"initialised meno home at {home}")
    return 0


def cmd_run(args) -> int:
    inst = run_instance(args.home, max_cycles=args.cycles)
    print(f"ran {inst.driver.cycles} cycles; status -> {inst.status_path}")
    return 0


def cmd_status(args) -> int:
    p = Path(args.home).expanduser() / "run" / "status.json"
    print(p.read_text() if p.exists() else "(no status yet — run the instance first)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="meno", description="a cognitive kernel instance")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="scaffold an instance home")
    p_init.add_argument("home")
    p_init.add_argument("--handle", default=None, help="addressable name (not identity)")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="run the home-bound daemon")
    p_run.add_argument("home")
    p_run.add_argument("--cycles", type=int, default=None, help="stop after N cycles (default: until signalled)")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="print run/status.json")
    p_status.add_argument("home")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
