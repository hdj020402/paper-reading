#!/usr/bin/env python3
"""Parse printed reference lines from a bundle into structured BibTeX entries.

Input: the verbatim REFERENCES section already transcribed in a per-paper bib
as `note = {Transcribed from the printed REFERENCES of <self>: <raw text>}`
entries (`@misc{<self>-ref-<N>, ...}`). This tool re-parses each raw text into
author, title, venue, year, volume, and pages fields, promotes entries with a
venue to @article (or @inproceedings for "In ..." lines), and keeps the raw
transcription as the note for verification.

Rules (deliberate conservatism):
- Only split what is printed: Nature-style "Author(s). Title. _Venue_ **vol**,
  pages, https://doi.org/... (year)." patterns. Unrecognized shapes stay @misc
  with the transcription note unchanged.
- Never guess fields. A missing volume stays missing; an entry type is chosen
  only from what was parsed (journal-like venue -> @article, "In <venue>" ->
  @inproceedings, else @misc).
- Self entries are left untouched; only `-ref-N` entries are rewritten.
- Emphasis markers (``_..._``) and bold markers (``**...**``) in the raw text
  map to venue and volume respectively; both are stripped in output.
- Optional Crossref completion by DOI: fetches official metadata by the DOI
  printed in the transcription (exact identifier lookup, never title search),
  fills only empty fields, and discards any fetched value that conflicts with
  a value already parsed from the print. Network failures leave the entry as
  parsed. Enable with --crossref.

Usage:
  .venv/bin/python scripts/bib-parse.py resources/bibliography/<id>/<id>.bib
  .venv/bin/python scripts/bib-parse.py <file> --crossref [--write]
Without --write, prints a report and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

CROSSREF_API = "https://api.crossref.org/works/"
NOTE_RE = re.compile(
    r"^@misc\{(?P<key>\S+?),\s*\n\s*note\s*=\s*\{Transcribed from the printed REFERENCES of "
    r"(?P<self>[^:]+): (?P<raw>.*?)\}\s*,?\s*\n"
    r"(?P<rest>(?:\s*[a-zA-Z]+\s*=\s*\{[^{}]*\}\s*,?\s*\n?)*)\}\s*$",
    re.DOTALL,
)
DOI_URL = re.compile(r"https?://(?:dx\.)?doi\.\s?org/(?P<doi>10\.\d{4,9}/[^\s,;)]+)")
YEAR_TAIL = re.compile(r"\((?P<year>\d{4})\)\s*\.?\s*$")
ET_AL = re.compile(r"_et al_\.?|_et al_\s*\.", re.IGNORECASE)


def strip_markers(text: str) -> str:
    text = text.replace("**", "").replace("_", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_first_period(text: str) -> tuple[str, str]:
    """Split authors from title at the first sentence-ending period.

    Author blocks are surname-initial chains ("Rupp, M., Tkatchenko, A. &
    Lilienfeld, O."), so periods inside initials, "et al.", and "Jr." must
    not split. A period ends the author block when the next token starts
    the title: a capitalized multi-letter word, a number, or a single
    capital letter followed by a longer word ("A look at...", "A QUADRATURE
    ..."). A token pair like "Isayev, O." (surname comma initial) continues
    the author chain instead.
    """
    for i, ch in enumerate(text):
        if ch != ".":
            continue
        tail = text[i + 1 :]
        m = re.match(r"\s+(\S+)(?:\s+(\S+))?", tail)
        if not m:
            continue
        w1 = m.group(1)
        w2 = m.group(2)
        if w1.endswith(",") and w2 and re.fullmatch(r"[A-Z]\.?", w2):
            continue  # author chain: "Isayev, O."
        if len(w1) > 1 and w1[0].isupper() and w1[1].isalpha():
            return text[:i], tail.strip()
        if w1[0].isdigit():
            return text[:i], tail.strip()
        if len(w1) == 1 and w1[0].isupper() and w2 and len(w2) > 1:
            return text[:i], tail.strip()  # "A look", "A QUADRATURE"
    return "", text  # cannot split: keep everything as the remainder


def parse_raw(raw: str) -> dict[str, str] | None:
    """Parse one printed reference line into fields, or None if unrecognized."""
    text = raw.strip().rstrip(".")
    # Year at the tail: either a bare parenthesized year "(2012)." or a
    # publisher parenthetical ending in a year "(MIT Press, 2006)".
    year = ""
    pub_tail = re.search(r"\((?P<pub>[^()]+?),?\s*(?P<y>\d{4})\)\s*$", text)
    if pub_tail:
        year = pub_tail.group("y")
        publisher_tail = pub_tail.group("pub").strip()
        text = text[: pub_tail.start()].strip().rstrip(".,")
    else:
        publisher_tail = ""
        year_m = YEAR_TAIL.search(text)
        if not year_m:
            return None
        year = year_m.group("year")
        text = text[: year_m.start()].strip().rstrip(",")

    doi_m = DOI_URL.search(text)
    doi = doi_m.group("doi") if doi_m else ""
    if doi_m:
        text = (text[: doi_m.start()] + text[doi_m.end() :]).strip().rstrip(",")

    authors, remainder = split_first_period(text)
    if not authors:
        return None

    # Venue: emphasized segment _..._ (Nature style) or "In _..._".
    in_venue = None
    pages = ""
    volume = ""
    m = re.search(r"\bIn\s+(_[^_]+_)", remainder)
    if m:
        in_venue = strip_markers(m.group(1))
        remainder = (remainder[: m.start()] + remainder[m.end() :]).strip().strip(" ,")
        # After removing "In _venue_", the remainder is "title , pages":
        # pages are the trailing bare number or range after the last comma.
        page_m = re.search(r",?\s*([\d]+(?:[–—-][\d]+)?|[A-Za-z]\d+)\s*$", remainder)
        if page_m:
            pages = page_m.group(1)
            remainder = remainder[: page_m.start()].strip().rstrip("., ")
        title = strip_markers(remainder)
    else:
        venue_m = re.search(r"_([^_]+)_", remainder)
        venue = ""
        volume = ""
        if venue_m:
            venue = strip_markers(venue_m.group(1))
            pre = remainder[: venue_m.start()].strip().rstrip(".,")
            title = strip_markers(pre)
            post = remainder[venue_m.end() :].strip().lstrip(".,")
            # Volume: bold segment **...** right after the venue.
            vol_m = re.match(r"\s*\*\*(\d+)\*\*\s*,?", post)
            if vol_m:
                volume = vol_m.group(1)
                post = post[vol_m.end() :].strip().lstrip(",")
            # Pages: first bare number or range before a comma or end.
            page_m = re.match(r"([\d]+(?:[–—-][\d]+)?|[A-Za-z]\d+)\s*(?=,|$)", post)
            if page_m:
                pages = page_m.group(1)
            # Leftover post text (publisher/series noise) stays in the note.
        else:
            title = strip_markers(remainder)

    if not title:
        return None
    entry = {
        "author": strip_markers(authors).rstrip(","),
        "title": title,
        "year": year,
    }
    if in_venue:
        entry["booktitle"] = in_venue
        entry["type"] = "inproceedings"
    elif venue:
        entry["journal"] = venue
        entry["type"] = "article"
    else:
        entry["type"] = "misc"
        if publisher_tail:
            entry["howpublished"] = publisher_tail
    if volume:
        entry["volume"] = volume
    if pages:
        entry["pages"] = pages
    if doi:
        entry["doi"] = doi
    return entry


def fetch_crossref(doi: str) -> dict[str, str] | None:
    try:
        req = urllib.request.Request(
            CROSSREF_API + doi, headers={"User-Agent": "paper-reading-bib-parse/1.0 (mailto:hudejun2002@gmail.com)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data.get("message", {})
        fields = {}
        if msg.get("container-title"):
            fields["journal"] = msg["container-title"][0]
        if msg.get("volume"):
            fields["volume"] = msg["volume"]
        if msg.get("page"):
            fields["page"] = msg["page"]
        if msg.get("issued", {}).get("date-parts"):
            fields["year"] = str(msg["issued"]["date-parts"][0][0])
        return fields
    except Exception:
        return None


def journal_equivalent(printed: str, fetched: str) -> bool:
    """True when two journal strings plausibly name the same journal.

    Crossref holds full journal names ("Chemical Science") while prints use
    abbreviations ("Chem. Sci."), and capitalization varies. Treat case and
    abbreviation periods as equivalent, and compare the initial letters of
    each word.
    """
    def initials(name: str) -> str:
        words = [w for w in re.split(r"[\s]+", name.replace(".", " ").strip()) if w]
        return "".join(w[0].lower() for w in words)
    p = printed.replace(".", " ").lower()
    f = fetched.lower()
    return p == f or initials(printed) == initials(fetched)


def complete(entry: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Fill empty fields from Crossref by DOI; discard conflicting fetches."""
    notes = []
    if not entry.get("doi"):
        return entry, notes
    fetched = fetch_crossref(entry["doi"])
    if fetched is None:
        notes.append("crossref fetch failed (kept parsed fields)")
        return entry, notes
    for key, value in fetched.items():
        if key not in entry or not entry[key]:
            if key == "year":
                continue  # parsed year always present; fill only other fields
            entry[key] = value
            notes.append(f"crossref filled {key}={value!r}")
            continue
        existing = entry[key]
        if key in ("page", "volume"):
            same = existing.replace("–", "-").replace("—", "-") == value.replace("–", "-").replace("—", "-")
        elif key == "journal":
            same = journal_equivalent(existing, value)
        else:
            same = existing == value
        if key == "year":
            continue  # print year and Crossref issue-year may differ; print wins silently
        if not same:
            notes.append(f"crossref {key}={value!r} conflicts with print {existing!r}; kept print")
    return entry, notes


def format_entry(key: str, entry: dict[str, str], raw: str, old_extra: str) -> str:
    """Format a parsed entry. Fields from the old entry that the parser did
    not reproduce (for example a DOI the print supplied out-of-band) are
    preserved verbatim, except duplicates of parsed fields."""
    bib_type = entry.get("type", "misc")
    lines = [f"@{bib_type}{{{key},"]
    order = ["author", "title", "journal", "booktitle", "year", "volume", "pages", "howpublished", "doi"]
    for field in order:
        if entry.get(field):
            lines.append(f"  {field} = {{{entry[field]}}},")
    # Preserve any old field the parser does not emit (verbatim), skipping
    # fields already covered above.
    for extra in re.finditer(r"([a-zA-Z]+)\s*=\s*\{[^{}]*\}", old_extra):
        field = extra.group(1).lower()
        if field not in order and field != "note":
            lines.append("  " + extra.group(0) + ",")
    lines.append(f"  note = {{Transcribed from the printed REFERENCES: {raw.strip()}}},")
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bib", type=Path, help="per-paper bib file to parse")
    parser.add_argument("--crossref", action="store_true", help="complete empty fields via Crossref by DOI")
    parser.add_argument("--write", action="store_true", help="rewrite the file; default is a dry run")
    args = parser.parse_args()

    text = args.bib.read_text(encoding="utf-8")
    entries = re.findall(r"@misc\{[^@]*?\n\}", text, re.DOTALL)
    out_parts: list[str] = []
    stats = {"parsed": 0, "unparsed": 0, "completed": 0, "conflicts": 0}

    for chunk in entries:
        m = NOTE_RE.match(chunk)
        if not m:
            out_parts.append(chunk)
            continue
        key = m.group("key")
        if "-ref-" not in key:
            out_parts.append(chunk)
            continue
        raw = m.group("raw")
        old_extra = m.group("rest")
        entry = parse_raw(raw)
        if entry is None:
            stats["unparsed"] += 1
            out_parts.append(chunk)
            print(f"KEEP  {key}: pattern not recognized")
            continue
        stats["parsed"] += 1
        notes = []
        if args.crossref:
            entry, notes = complete(entry)
            stats["completed"] += sum(1 for n in notes if n.startswith("crossref filled"))
            stats["conflicts"] += sum(1 for n in notes if "conflict" in n)
        out_parts.append(format_entry(key, entry, raw, old_extra))
        kind = entry.get("type", "misc")
        print(f"PARSE {key}: {kind}, journal={entry.get('journal', '')!r}, vol={entry.get('volume', '')!r}, "
              f"pages={entry.get('pages', '')!r}, year={entry['year']}")
        for n in notes:
            print(f"      {n}")

    # Reassemble: replace each matched chunk in the original text order.
    result = text
    for chunk, replacement in zip(entries, out_parts):
        if chunk != replacement:
            result = result.replace(chunk, replacement, 1)

    print(f"\n{stats['parsed']} parsed, {stats['unparsed']} kept unparsed, "
          f"{stats['conflicts']} crossref conflicts (print kept)")
    if args.write:
        args.bib.write_text(result, encoding="utf-8")
        print(f"Wrote {args.bib}")
    else:
        print("Dry run; use --write to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
