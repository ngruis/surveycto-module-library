# SurveyCTO Module Library

## Install a released application

Download one file for your operating system from the repository's Releases page. Python, a
terminal, and the source project are not required:

- **macOS:** download the Apple Silicon or Intel `.dmg`, open it, then double-click
  `SurveyCTO Module Library.app`.
- **Windows:** download the Windows x64 `.exe` and double-click it.

The application starts a private local server and opens the interface in the default browser.
Nothing needs to be installed globally on the computer.

The first-launch **Setup & update** tab asks for a SurveyCTO server, username, and password. The
connection is verified before the server is saved. Credentials are stored in the operating-system
credential manager, and survey definitions and the generated database stay in that user's local
application-data directory.

## Use the source checkout on macOS

1. Double-click **SurveyCTO Module Library.command**.
2. Choose **Update and open library** the first time. A secure popup asks for your SurveyCTO username and password if they have not been saved on this Mac.
3. The library opens in your browser. Use the filters on the left, expand surveys and modules, and click **Export filtered results** when needed.

Choose **Open library** on later visits when you only want to browse the last successful update. Choose **Update library from SurveyCTO** to refresh the database without opening it.

Only deployed survey definitions are retrieved. The application never requests or downloads respondent submissions.

## What the application creates

- `data/raw/<run>/`: newly retrieved form-definition JSON plus `run_metadata.json`, which
  records the complete roster, reused source paths, failures, and processing totals for that run.
- `data/database/module_library.sqlite3`: the searchable library and run history.
- `data/exports/`: Excel files created from the current filters.
- `logs/`: readable update and application logs.

SurveyCTO credentials are stored in the macOS Keychain, not in this project folder. Automatic classification is local and rule-based by default; no form text is sent to an external AI service.

Packaged releases use the corresponding operating-system credential manager. Release packages do
not contain survey definitions, a database, logs, exports, or credentials.

## If something goes wrong

The launcher keeps its window open and shows a readable error. The latest details are also in `logs/`. Opening the library does not require SurveyCTO access once an update has succeeded.

## For maintainers

The package uses an API-first retrieval adapter, a deterministic XLSForm parser, SQLite as the canonical processed store, rule-based taxonomy classification, and Streamlit for the local interface. See [docs/architecture.md](docs/architecture.md) and [docs/data_dictionary.md](docs/data_dictionary.md). Release-readiness work is tracked in [docs/release-roadmap.md](docs/release-roadmap.md).

Useful development commands after activating `.venv`:

```bash
pip install -e '.[dev,browser]'
pytest
surveycto-library demo
surveycto-library update
streamlit run app/streamlit_app.py
```

Updates reuse form IDs already present in the raw JSON archive. This makes routine updates fast
and leaves one canonical downloaded copy of each form. Use `surveycto-library update
--refresh-existing` when every deployed definition must be downloaded again.

## Reproducible builds

Dependencies are locked in `uv.lock`. Install the tested development environment with `uv sync
--frozen --extra dev`; include `--extra release` for PyInstaller builds. GitHub Actions tests the
same code on macOS, Windows, and Linux. Version tags create two single-file macOS disk images—Apple
Silicon and Intel—and one self-contained Windows executable.
