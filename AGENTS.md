# paper-reading Agent Guide

This is a central literature library, not a research project. The agent's job here is faithful, traceable reading: convert papers into verified reading corpora, answer questions against those corpora with anchors, and maintain per-paper notes and bibs.

Read `README.md` first for layout, paper identity, and the user-facing commands. Route every recurring workflow through this document's procedures; do not improvise variants.

## Invariants

- **Source layer is immutable.** Never modify anything under `resources/bibliography/<id>/` after intake; corrections land in `reviews/` or `provenance/`, or in a fresh intake.
- **Ids are join keys, never renamed.** `bibliography/<id>/`, `bundles/<id>/`, `provenance/<id>/`, `reviews/<id>.md`, and the BibTeX key must all share the id.
- **Bundles must be verified.** Use a bundle only when its `provenance/<id>/run.json` reports `verification_status` of `reviewed` or `reviewed_with_limitations`; otherwise it is a draft.
- **Notes must be anchored.** Every bullet-point note in a review cites its source: main-text section, SI section, page, figure, or table number, linking into the bundle's `references/paper.md` or a DOI.
- **Generated files are never hand-edited.** `references.bib` and `TAGS.md` are produced by `scripts/`; edit the per-paper sources instead.
- **Records state facts, not defaults.** The model and reasoning level in `run.json` describe what actually ran; never copy a model name from documentation or memory into a record.

## Procedures

### Triage — intake one new paper

Input: a PDF the user has placed (anywhere findable; usually `resources/bibliography/`). Steps:

1. Read the PDF's first page and abstract. Identify the publication year and corresponding-author surname (pinyin initials for Chinese names).
2. Assign the id `YYYY-<author>-<serial>`: list `resources/bibliography/` and `resources/reviews/` for that year+author prefix, and take the next unused lowercase letter. Never reorder or reuse serials.
3. Check for duplicate intake: search existing per-paper bibs and reviews for the paper's DOI or exact title. If the paper is already in the library, stop and report the existing id.
4. Create `resources/bibliography/<id>/` and move sources in, renamed to the id: main paper `<id>.pdf`; every supplement renamed to an `<id>-si` stem with its original extension. Word-format SI is converted with `soffice --headless --convert-to pdf` and the original kept alongside.
5. Read the abstract and skim introduction and conclusions. Assign tags: lowercase hyphenated terms for field, method, reaction, or ligand; one `project:<name>` tag per research project that depends on this paper; a status tag (`status:triaged`).
6. Create the review stub `resources/reviews/<id>.md` from `resources/reviews/TEMPLATE.md`: fill the frontmatter (id, title, tags, triage line, dates); leave the body sections empty.
7. Decide the triage outcome, recorded in the frontmatter `triage` line: `bundle` (meets two or more of: directly tied to an active project; likely to be cited by our own writing; repeated data extraction from its tables/SI expected; method to reproduce), or `hold` (otherwise, one-line reason).
8. If DOI metadata is available, create a per-paper bib stub containing only the self entry (key like `sunoj2022a`); the full bib-extract run happens after bundling.

Report: the assigned id, created files, tags, and the triage decision with its reason.

### Bundle — build the reading corpus for `<id>`

Use the paper2skill route of the installed skill (`.agents/skills/paper2agent/paper2skill/`). The bundle is named exactly `<id>`; upstream's name rule (lowercase hyphenated words, ≤63 chars) is satisfied by construction. Steps:

1. Take the main PDF and supplements from `resources/bibliography/<id>/`.
2. Record the start time from the system clock. Run the conversion with the session's current model and reasoning level; do not switch models for the run.
3. Run the paper2skill workflow with the project interpreter `.venv/bin/python` (it provides pymupdf and pillow): `prepare` (work directory `resources/provenance/<id>/review`, main PDF via `--main`), `extract`, `review-aid`, the multi-agent page review, `build` into `resources/bundles/<id>/`, and `verify --strict`, following the skill's review and verification protocol.
4. Run the mechanical verification yourself and report its status, `mechanical_ok`, and issues — the build's own report is never a substitute.
5. Write `resources/provenance/<id>/run.json` with exactly these fields: `schema_version` (integer `1`), `provider` (channel name or `null`), `model` and `reasoning_level` (strings), `started_at` and `finished_at` (UTC ISO-8601), `elapsed_seconds` (integer), `outcome` (`verified` or `failed`), `verification_status` (reported status or `null`). Fill model fields from what actually ran.
6. If `bundles/<id>/` already exists and the current source SHA-256 hashes match the provenance inventory, reuse it: confirm its verification status instead of rebuilding.

Report: bundle path, elapsed time, verification status, limitations. Do not modify anything under `resources/bibliography/<id>/`.

### Review — draft the 研究概述 for `<id>`

1. Read the bundle's `references/index.md`, then only the passages needed for the overview.
2. Create or update `resources/reviews/<id>.md`, preserving existing frontmatter and any existing content.
3. Draft only `研究概述` — `背景`, `问题`, `思路`, `结论` — each one short paragraph, grounded in the source, with source anchors (sections, figures, tables) in parentheses at the paragraph end. Mark interpretations as the reader's. Drafts are 粗稿: honest and short rather than complete.
4. Keep `文献要点` present but empty in new drafts.

Run `.venv/bin/python scripts/md-lint.py resources/reviews/<id>.md` before delivering; fix every reported violation.

### Q&A and notes — read against a bundle

- Read bundles by bounded search: `rg -n` to locate a heading or term, then read 30–60 lines around the hit; never load a whole document to answer a question.
- Cite the section, figure, or table for every claim pulled from a bundle; quote numbers exactly as transcribed.
- Distinguish the paper's reported findings from interpretation; interpretations stay clearly marked as the reader's.
- When the discussion produces a fact worth keeping, append it to the review's `文献要点`: one `### <要点标题>` block per fact — one short paragraph stating the fact, then a `出处` line citing section, figure, table, or page, with a relative link into the bundle's `references/paper.md` or a DOI link. One note = one fact; split compound observations. Never write a note whose evidence you have not located and read. Update the frontmatter `status` tag on the first note (`status:reading`) and refresh `updated`. Run md-lint before delivering.

### Bib — build the per-paper bib for `<id>`

1. Read the verbatim REFERENCES section in the bundle's `references/paper.md`; it is the ground truth.
2. Write the self entry first: key `<author><YYYY><serial-letter>` (e.g. `sunoj2022a`), with title, authors, journal, year, volume, pages, and DOI. Fill fields from the source PDF's first page; resolve the DOI via Crossref when absent from the paper.
3. Write one entry per cited reference: key `<author><YYYY>-ref-<N>` matching the reference number. Transcribe the printed entry; add DOI via Crossref only when the match is unambiguous.
4. Run a reference verification pass (the nature-ref-verifier skill, or an equivalent Crossref field comparison) over every entry; fix mismatches against the printed text, and drop uncertain DOIs rather than guess.
5. Run `.venv/bin/python scripts/bib-aggregate.py` and `.venv/bin/python scripts/tag-index.py`.

When the bib and the bundle's verbatim REFERENCES disagree, the bundle wins. Cited-reference entries stay in the per-paper bib; the aggregate carries self entries alone.

### Session init — realign with the library

At session start: read `README.md`, then `AGENTS.md`; list `resources/reviews/` and read frontmatter tags for a one-line coverage map; for the named paper, check `bibliography/<id>/`, `bundles/<id>/`, `provenance/<id>/run.json`, `reviews/<id>.md` as the request needs; confirm a bundle's verification status before treating it as usable. Read-only. If frontmatter, provenance, and bundle contents disagree, report the mismatch before changing anything.

## Prose rules

One paragraph per line, in any language. Never hard-wrap prose to a fixed width; a line ends only at its paragraph's end. Run `.venv/bin/python scripts/md-lint.py` before delivering any new or edited markdown.
