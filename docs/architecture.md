# Architecture

The application is local-first and API-first.

1. `retrieval.py` lists accessible deployed form IDs through SurveyCTO API v2 and retrieves each deployed definition through `pysurveycto`. It never calls a submission endpoint.
2. Before retrieval, the updater builds a roster from prior `run_metadata.json` manifests and raw
   JSON envelopes. Previously archived form IDs are reused; only new IDs are downloaded. Each new
   response is wrapped with retrieval metadata beneath `data/raw/<run_id>/`, and a SHA-256 digest
   identifies exact definition content. A terminal progress bar reports downloaded, reused, and
   failed counts.
3. `parsing.py` deterministically normalizes SurveyCTO rows, multilingual labels, choice lists, nested groups/repeats, and dependencies.
4. `modules.py` stores literal source groups separately from inferred reusable modules and labels obvious administrative blocks as noise.
5. `categorization.py` applies a local seed taxonomy and stores method, confidence, and evidence. A future semantic provider can be added without changing retrieval or source data.
6. `database.py` writes normalized entities to SQLite. Raw source, Python inference, future model inference, and future human decisions have separate tables or provenance fields.
7. `app/streamlit_app.py` queries SQLite, groups results by survey and module, exposes details and source links, and exports current results to XLSX.

Updates are incremental at the form level: unchanged content hashes retain the existing parsed
representation; new or changed definitions are re-parsed and reclassified. Every run has a
validation record in `logs/` and a detailed `data/raw/<run_id>/run_metadata.json` beside its new
downloads. The latter contains the complete rebuild roster, retrieval outcome, processing totals,
failures, and validation summary.

`surveycto-library rebuild` follows the newest run manifest to reapply the current parser and
classifier to both new and reused raw definitions without contacting SurveyCTO again.

Browser automation is an optional fallback boundary and is not part of the normal deployed-definition workflow. The API workflow is authoritative for V1 because it has already retrieved the accessible J-PAL MENA deployed definitions successfully.
