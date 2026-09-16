#!/usr/bin/env python3
r"""Paper lint. Fails on
  1. hard-coded result numbers outside \pn{...}
  2. \pn{key} references that paper_numbers.json does not define
Design constants (schema caps, thresholds, attempt ids) are allow-listed below.
Escape hatch for a genuine one-off constant: end the line with  % lint-ok
"""
import re
import sys
from pathlib import Path

SECTIONS = sorted(Path("paper/sections").glob("*.tex")) + [Path("paper/abstract.tex")]
KEYS = set(Path("paper/generated/keys.txt").read_text().split())

DESIGN_CONSTANTS = {"250", "400", "800", "1000", "1200", "2,000", "2{,}000", "4,096", "4{,}096",
                    "30", "31", "20", "95\\%"}
STRIP = re.compile(
    r"\\pn\{[^}]*\}|\\(?:cite\w*|[cC]ref|ref|label|input|includegraphics|code|cat)(?:\[[^]]*\])?\{[^}]*\}"
    r"|[Aa]ttempts?~\d+(?:(?:,|~and)~?\d+)*|\\\w+|\{\d+,\d+\}"
)
NUM = re.compile(r"\d[\d,{}]*(?:\.\d+)?\s*(?:\\%|pp\b)|(?<![\w.])\d+(?:\{,\}\d{3})+|(?<![\w.{])\d{2,}(?![\w.}])")
PN = re.compile(r"\\pn\{([^}]*)\}")

bad = 0
for f in SECTIONS:
    for i, line in enumerate(f.read_text().splitlines(), 1):
        code = re.split(r"(?<!\\)%", line)[0] if not line.rstrip().endswith("lint-ok") else ""
        for k in PN.findall(line):
            if k not in KEYS:
                print(f"{f}:{i}: unknown key \\pn{{{k}}}")
                bad += 1
        for m in NUM.finditer(STRIP.sub(" ", code)):
            if m.group().strip() not in DESIGN_CONSTANTS:
                print(f"{f}:{i}: hard-coded number '{m.group()}'")
                bad += 1
print(f"{bad} problem(s)" if bad else "lint OK")
sys.exit(1 if bad else 0)
