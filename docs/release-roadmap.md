# Release roadmap

The target product is one cross-platform codebase that produces distributable macOS and Windows
desktop launchers. Each launcher starts the same local web application. The application package
contains code and runtime dependencies only. Survey definitions and the local search database are
created on each user's computer after that user authenticates to a SurveyCTO server.

## P0 — Required before an internal release

### Server onboarding and credentials

- On first launch, prompt for a SurveyCTO server name or URL instead of assuming `jpalmena`.
- Normalize entries such as `example`, `example.surveycto.com`, and
  `https://example.surveycto.com` to the same server identifier.
- Prompt for that server's username and password, verify access, and store credentials in the
  operating-system credential manager keyed by server and username.
- Persist the selected server in per-user application settings, not in distributed source files.
- Let users change servers or credentials later without editing configuration files.

### Partial-update behavior and end-of-run report

- Treat an individual rejected or inaccessible form as a recoverable warning.
- Continue retrieving and processing all other forms.
- Open the library after a partial update when the database is usable.
- Reserve a failing exit status for fatal conditions such as failed authentication, inability to
  list forms, no usable database, or a failed database transaction.
- Show and save an end-of-run report with forms found, downloaded, reused, parsed, unchanged,
  failed, question/module totals, elapsed time, and a form-level failure table.
- Keep the detailed machine-readable report in the run's `run_metadata.json`.

### Distributable application

- Package source- and data-free macOS and Windows applications from the same codebase and release
  tag. Produce separate macOS Apple Silicon, macOS Intel, and Windows x64 artifacts; users download
  the one for their computer.
- Opening the application starts the local server, opens the local website in the default browser,
  and shuts the server down cleanly when appropriate.
- Do not distribute `.venv`, `data/raw`, the SQLite database, exports, logs, or credentials.
- Add first-run checks and clear errors for connectivity, credentials, writable storage, and port
  availability.
- Test installation and first launch on clean macOS and Windows computers.
- Produce a versioned release artifact and installation/uninstallation instructions.
- Sign and notarize the macOS application with an Apple Developer ID, and sign the Windows
  executable with a trusted code-signing certificate. Keep signing credentials only in protected
  repository secrets; unsigned preview artifacts may be used for internal testing.

### Local-data lifecycle and privacy

- Retrieval is authorized by the user's own SurveyCTO credentials and server access.
- Store retrieved definitions and the generated database only in that user's application-data
  directory.
- Explain that definitions remain locally available after download even when the user logs out.
- Provide an explicit action to remove saved credentials and optionally clear downloaded local
  data.
- Never include downloaded definitions or databases in the source repository or release package.

## P1 — Reproducible development and releases

### Dependency locking

- Use `uv` with the existing `pyproject.toml` and commit the generated `uv.lock`, containing the
  exact tested versions of all direct and transitive Python dependencies.
- Make local development and CI use `uv sync --frozen`; make both operating-system release builds
  install from the same lock file.
- Update dependencies deliberately with `uv lock --upgrade`, then run the complete test and package
  matrix before committing the changed lock file.

### GitHub repository

- Initialize Git and create a **public** GitHub repository containing source code, tests,
  configuration templates, and documentation only.
- Verify `.gitignore` excludes virtual environments, raw definitions, databases, exports, logs,
  caches, credentials, and build artifacts.
- Scan the initial commit for credentials and downloaded survey content before pushing.
- Use tagged releases for distributable application artifacts.

### Automated CI and release workflow

- Run linting, unit tests, and package/build validation on every pull request and push.
- Add a clean-install smoke test that launches the application and verifies the local health page.
- Build separate versioned macOS and Windows application artifacts from the same tags using a CI
  build matrix.
- Add checks preventing raw definitions, databases, credentials, or oversized generated files from
  entering the repository.

### Documentation and software licensing

- Add installation, first-run, server-switching, update-report, troubleshooting, and local-data
  deletion instructions.
- Distribute the source code under the MIT License included in `LICENSE`.
- Keep software licensing separate from SurveyCTO data authorization: server access authorizes
  retrieval, while the software license governs reuse and redistribution of the application code.
