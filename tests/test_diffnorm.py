from reviewpilot.diffnorm import parse_unified_diff, Hunk

DIFF = """diff --git a/calc.py b/calc.py
index e69de29..0d1f2c3 100644
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@ def add(a, b):
-    return a - b
+    return a + b
"""

def test_parses_file_and_new_start_and_lines():
    hunks = parse_unified_diff(DIFF)
    assert len(hunks) == 1
    h = hunks[0]
    assert isinstance(h, Hunk)
    assert h.file == "calc.py"
    assert h.new_start == 1
    assert "+    return a + b" in h.lines
    assert "-    return a - b" in h.lines

def test_empty_diff_returns_no_hunks():
    assert parse_unified_diff("") == []
