import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Only the signer is allowed to decrypt secrets; sessions defines the primitive.
ALLOWED = {"execution/signer.py", "execution/sessions.py"}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache", "tests"}


def _scan_decrypt_secret():
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    txt = fh.read()
            except OSError:
                continue
            if "decrypt_secret" in txt and rel not in ALLOWED:
                hits.append(rel)
    return sorted(hits)


class SignerOnlyTests(unittest.TestCase):
    def test_only_signer_touches_decrypt_secret(self):
        self.assertEqual(_scan_decrypt_secret(), [])


if __name__ == "__main__":
    unittest.main()
