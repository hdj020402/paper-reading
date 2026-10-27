# paper-reading

Central literature library and AI-assisted reading workflow, built on [Paper2Agent](https://github.com/jmiao24/Paper2Agent) (paper-only Paper2Skill route). This repository holds every paper, its reading corpus, provenance, and reading notes. Research projects reference papers here by id and tag; they do not keep their own copies.

## Layout

```txt
paper-reading/
├── resources/
│   ├── bibliography/       # Source layer: one <id>/ subdirectory per paper
│   │   ├── <id>/
│   │   │   ├── <id>.pdf        # Main paper
│   │   │   ├── <id>-si*.pdf    # Supplementary information (PDF)
│   │   │   └── <id>.bib        # Per-paper bib: self entry + cited refs
│   │   └── references.bib      # Aggregate of all self entries (generated)
│   ├── bundles/            # Reading corpora: one <id>/ per bundled paper
│   ├── provenance/         # Build records: <id>/run.json + review evidence
│   └── reviews/            # Reading notes: <id>.md (the human-read layer) + TEMPLATE.md
├── scripts/                # bib-aggregate.py, tag-index.py, md-lint.py
└── .agents/skills/         # Installed paper2agent skill (Paper2Skill route)
```

## Paper identity

- **id** = `YYYY-<author>-<serial>`, e.g. `2022-sunoj-a`: `YYYY` publication year, `<author>` corresponding-author surname or pinyin initials, `<serial>` a lowercase letter assigned in intake order within that year+author prefix. Serials carry no meaning, are never reordered, and never reused.
- The id is the join key across `bibliography/`, `bundles/`, `provenance/`, and `reviews/`. Ids are never renamed; identity is verified by DOI (in `<id>.bib`) and source SHA-256 (in provenance), not by the id.
- Bundle directories are named exactly `<id>/` (no model or `-paper` suffix). The model and reasoning level of each build are facts recorded in `provenance/<id>/run.json`, never prescribed in documentation.

## How to use

You normally just talk to the assistant in this directory. The workflows live in `AGENTS.md`; four commands cover them:

- **Intake a new paper** (place the PDF, then say "triage this paper"): the assistant reads the PDF's abstract, assigns an id, creates `bibliography/<id>/` with renamed sources, writes the review stub `reviews/<id>.md` (tags, one-line triage decision: bundle or hold), and a bib stub when the DOI is known.
- **Build the reading corpus** (say "bundle <id>"): runs the paper2skill conversion (~an hour of agent time), producing `bundles/<id>/` (searchable full text + figure/table assets) and `provenance/<id>/run.json`. Only verified bundles are used for reading.
- **First read** (say "review <id>"): drafts the research overview (in Chinese as the notes' working language) into the review file from the bundle.
- **Daily Q&A** (just ask, e.g. "what is the Set-2 RMSE in <id>?"): the assistant searches the bundle, reads the relevant passage, and answers with section/figure/table anchors; confirmed facts get appended to the review.

Maintenance scripts (see below): regenerate the aggregate bib and tag index, check markdown formatting.

## Maintenance

- `python3 scripts/bib-aggregate.py` — regenerate `references.bib` from per-paper bibs; fails on duplicate keys or DOIs (`--check` verifies only).
- `python3 scripts/tag-index.py` — regenerate `TAGS.md` from review frontmatter (`--check` verifies only).
- `python3 scripts/md-lint.py` — check markdown for hard-wrapped prose; run before delivering any new markdown.

## Status

Bootstrapped 2026-10-26. Two PDFs sit in `resources/bibliography/` awaiting triage (not yet renamed into `<id>/` directories).
