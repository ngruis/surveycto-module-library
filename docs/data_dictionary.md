# Data Dictionary

- `forms`: current deployed form metadata and content hash.
- `raw_form_definitions`: immutable retrieval provenance and raw file path.
- `survey_questions`: normalized survey rows, labels, logic, group path, and raw row JSON.
- `choice_lists`, `choices`: static SurveyCTO answer options and translations.
- `source_groups`: literal nested `begin group`/`begin repeat` structures.
- `inferred_modules`, `module_questions`: reusable candidates and their ordered questions.
- `dependencies`: field references, attached datasets/files, search sources, and plug-ins.
- `taxonomy_terms`: current seed taxonomy vocabulary.
- `question_categories`, `module_categories`: inferred labels, confidence, method, and evidence.
- `projects`, `form_projects`, `population_metadata`: empty V1 structures for later team metadata.
- `scrape_runs`, `classification_runs`: update and classification provenance.
- `semantic_embeddings`: provider-neutral storage reserved for later question/module similarity.
