#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from profile_loader import bootstrap_profile


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python engine/profile_cli.py",
        description="Openspired profile utilities",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Create or bootstrap an external profile")
    init_cmd.add_argument("--path", required=True, help="Absolute or relative profile directory")
    init_cmd.add_argument("--name", required=True, help="Profile display name")
    init_cmd.add_argument("--workspace", default="workspace", help="Workspace path (relative to profile)")
    init_cmd.add_argument("--agents", default="agents", help="Agents overrides path (relative to profile)")

    args = parser.parse_args()

    if args.command == "init":
        result = bootstrap_profile(
            Path(args.path),
            name=args.name,
            workspace_rel=args.workspace,
            agents_rel=args.agents,
        )
        print("Profile ready")
        print(f"  root: {result['profile_root']}")
        print(f"  workspace: {result['workspace_dir']}")
        print(f"  agents: {result['agents_dir']}")
        print(f"  profile.toml: {result['profile_toml']}")


if __name__ == "__main__":
    main()
