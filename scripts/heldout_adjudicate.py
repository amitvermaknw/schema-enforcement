#!/usr/bin/env python3
"""Post hoc, mechanical check of the held-out disagreements (read-only).

For every item where the human label differs from the classifier, print the
facts the codebook turns on, computed directly from the stored raw output:

  - first characters of the output (repr), whether it starts with a fence,
    the length of any prose before the first embedded JSON object;
  - whether the output parses as JSON after removing fences;
  - every error the node schema reports for the fence-stripped payload
    (type, location, message), with the actual length of any too-long string.

Nothing here changes labels or the primary result. Output goes to the screen
and to results/heldout/adjudication.md.

Run from the repo root:  .venv/bin/python scripts/heldout_adjudicate.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pydantic import ValidationError  # noqa: E402
from schemaeval.errors import _EMBEDDED_JSON_RE, _strip_code_fences  # noqa: E402
from schemaeval.schemas import get_schemas  # noqa: E402

DB = ROOT / "results/archive/paper1_FINAL_DATA_locked_v4_20260913.db"
SCORE = ROOT / "results/heldout/score.json"
OUT = ROOT / "results/heldout/adjudication.md"


def dig(obj, loc):
    for k in loc:
        try:
            obj = obj[k]
        except (KeyError, IndexError, TypeError):
            return None
    return obj


def main() -> None:
    dis = json.loads(SCORE.read_text())["disagreements"]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    lines = ["# Held-out disagreements: mechanical facts (post hoc)", ""]
    for d in sorted(dis, key=lambda d: (d["classifier"], d["human"], d["attempt_id"])):
        x = con.execute(
            "SELECT a.raw_output raw, a.node_name node, r.schema_tier tier, r.model "
            "FROM node_attempts a JOIN runs r USING (run_id) WHERE a.id = ?", (d["attempt_id"],)).fetchone()
        raw = x["raw"] or ""
        s = raw.lstrip()
        m = _EMBEDDED_JSON_RE.search(raw)
        stripped = _strip_code_fences(raw)
        try:
            payload = json.loads(stripped)
            parses = True
        except ValueError:
            payload, parses = None, False
        schema = dict(zip(("identify", "gather", "answer"), get_schemas(x["tier"])))[x["node"]]
        errs = []
        try:
            schema.model_validate_json(stripped)
        except ValidationError as e:
            for err in e.errors():
                loc = [p for p in err["loc"]]
                extra = ""
                if err["type"] in ("string_too_long", "too_long") and payload is not None:
                    v = dig(payload, loc)
                    if v is not None and hasattr(v, "__len__"):
                        extra = f"  [actual length {len(v)}]"
                errs.append(f"{err['type']} @ {'.'.join(map(str, loc)) or '(root)'}: "
                            f"{str(err['msg'])[:110]}{extra}")
        block = [
            f"## {d['attempt_id']}  classifier={d['classifier']}  human={d['human']}",
            f"- {x['model']} / {x['tier']} / {x['node']}; output {len(raw)} chars",
            f"- starts: {s[:30]!r}",
            f"- starts with fence: {s.startswith('```')}; prose before first JSON object: "
            f"{m.start() if m else 'n/a'} chars; parses after fence strip: {parses}",
            "- validator errors on fence-stripped payload:" if errs else "- validator errors: none",
            *[f"    - {e}" for e in errs],
            "",
        ]
        print("\n".join(block))
        lines += block
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
