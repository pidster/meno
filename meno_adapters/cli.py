"""`meno` — the instance entrypoint and composition root.

This is where the kernel and the integration layer are wired together: `meno run`
builds the instance (kernel) and attaches the adapters its config enables
(meno_adapters), keeping `meno/` itself adapter-blind. `init` / `status` delegate to
the kernel's CLI unchanged.

    meno init <home> [--handle NAME]   # scaffold an instance home
    meno run  <home> [--cycles N]      # run the daemon WITH configured channels/authorities
    meno status <home>                 # print run/status.json
"""
from __future__ import annotations

import argparse

from meno import cli as _kernel_cli

from .loader import load_adapters


def cmd_run(args) -> int:
    attached = []

    def _wire(inst):
        attached.extend(load_adapters(inst))

    inst = _kernel_cli.run_instance(args.home, max_cycles=args.cycles, on_build=_wire)
    print(f"ran {inst.driver.cycles} cycles; adapters={attached or 'none'}; "
          f"status -> {inst.status_path}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="meno", description="a cognitive kernel instance")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="scaffold an instance home")
    p_init.add_argument("home")
    p_init.add_argument("--handle", default=None, help="addressable name (not identity)")
    p_init.set_defaults(func=_kernel_cli.cmd_init)

    p_run = sub.add_parser("run", help="run the daemon with configured channels/authorities")
    p_run.add_argument("home")
    p_run.add_argument("--cycles", type=int, default=None, help="stop after N cycles (default: until signalled)")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="print run/status.json")
    p_status.add_argument("home")
    p_status.set_defaults(func=_kernel_cli.cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
