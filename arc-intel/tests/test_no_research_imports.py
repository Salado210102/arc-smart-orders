import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROD_DIRS = ("bot", "execution")
# Any import of research code (or the old indexer.smart_money) from production modules.
PAT = re.compile(
    r"^\s*(?:from\s+(?:research\b|indexer\.smart_money\b)"
    r"|(?:import|from)\s+[^\n]*\bsmart_money\b)",
    re.M)


def _scan():
    hits = []
    for d in PROD_DIRS:
        base = os.path.join(ROOT, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        txt = fh.read()
                except OSError:
                    continue
                for m in PAT.finditer(txt):
                    hits.append(f"{rel}: {m.group(0).strip()}")
    return sorted(hits)


class NoResearchImportTests(unittest.TestCase):
    def test_bot_and_execution_do_not_import_research(self):
        self.assertEqual(_scan(), [], "production code must not import research code")


if __name__ == "__main__":
    unittest.main()
