from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone

from .config import load_settings
from .credentials import load_credentials, prompt_and_save
from .database import initialize
from .demo import demo_definitions
from .pipeline import (
    ValidationSummary,
    _finish_run,
    _logger,
    _process_definitions,
    _start_run,
    _write_validation,
    process_raw_files,
    run_update,
)
from .retrieval import definition_paths_for_run


def main() -> int:
    parser = argparse.ArgumentParser(description="J-PAL MENA SurveyCTO Module Library")
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser(
        "update", help="Retrieve deployed definitions and update the library"
    )
    update.add_argument("--limit", type=int)
    update.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Download every form again instead of reusing archived JSON by form ID",
    )
    credentials = commands.add_parser(
        "credentials", help="Save SurveyCTO login in the system keychain"
    )
    credentials.add_argument("--popup", action="store_true")
    commands.add_parser("open", help="Open the local search application")
    commands.add_parser("demo", help="Build a demonstration library without server access")
    commands.add_parser("rebuild", help="Rebuild from the most recent raw archive")
    commands.add_parser("init", help="Initialize an empty database")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "credentials":
        prompt_and_save(settings.server, popup=args.popup)
        print("SurveyCTO login saved securely in the macOS Keychain.")
        return 0
    if args.command == "init":
        initialize(settings.database_path)
        print(f"Database ready: {settings.database_path}")
        return 0
    if args.command == "update":
        saved = load_credentials(settings.server)
        if saved is None:
            print("No saved SurveyCTO login was found. A secure popup will open.")
            saved = prompt_and_save(settings.server, popup=sys.platform == "darwin")
        summary = run_update(
            settings,
            saved,
            limit=args.limit,
            reuse_existing=not args.refresh_existing,
        )
        _print_summary(summary)
        return 0
    if args.command == "demo":
        initialize(settings.database_path)
        run_id = f"demo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        definitions = demo_definitions(settings.raw_directory, run_id)
        summary = ValidationSummary(
            run_id, forms_found=len(definitions), forms_downloaded=len(definitions), failures=[]
        )
        timestamp = datetime.now().astimezone().isoformat()
        _start_run(settings, run_id, timestamp)
        _process_definitions(settings, definitions, summary, timestamp, _logger(settings, run_id))
        _finish_run(settings, summary, "success", timestamp)
        _write_validation(settings, summary)
        _print_summary(summary)
        return 0
    if args.command == "rebuild":
        run_directories = [
            path
            for path in settings.raw_directory.iterdir()
            if path.is_dir() and (settings.log_directory / f"validation_{path.name}.json").exists()
        ]
        if not run_directories:
            raise RuntimeError(
                "No completed raw definition archive exists yet. Run an update first."
            )
        latest = max(run_directories, key=lambda path: path.stat().st_mtime)
        paths = definition_paths_for_run(settings.raw_directory, latest)
        if not paths:
            raise RuntimeError(f"No definitions were found in {latest}.")
        print(f"Rebuilding from {len(paths)} definitions in {latest.name}...")
        _print_summary(process_raw_files(settings, paths))
        return 0
    if args.command == "open":
        initialize(settings.database_path)
        app_path = settings.root / "app" / "streamlit_app.py"
        return subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.headless=false"],
            cwd=settings.root,
        )
    return 1


def _print_summary(summary: ValidationSummary) -> None:
    print("\nUpdate summary")
    print(f"  Forms found: {summary.forms_found}")
    print(f"  Definitions saved: {summary.forms_downloaded}")
    print(f"  Definitions reused: {summary.forms_reused}")
    print(f"  Forms parsed: {summary.parsed_forms}")
    print(f"  Questions: {summary.total_questions}")
    print(f"  Reusable modules: {summary.inferred_modules}")
    print(f"  Categorized questions: {summary.categorized_questions}")
    print(f"  Unchanged forms: {summary.unchanged_forms}")
    print(f"  Duration: {summary.duration_seconds:.1f} seconds")
    if summary.failures:
        print(f"  Warnings: {len(summary.failures)} (see logs/validation_{summary.run_id}.json)")


if __name__ == "__main__":
    raise SystemExit(main())
