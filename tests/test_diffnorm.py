from reviewpilot.diffnorm import parse_unified_diff, split_diff_by_file, Hunk

TWO_FILE_DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-x
+y
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1 @@
-m
+n
"""

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


def test_split_diff_by_file_separates_each_file():
    blocks = split_diff_by_file(TWO_FILE_DIFF)
    assert [f for f, _ in blocks] == ["a.py", "b.py"]
    assert "+y" in blocks[0][1] and "+n" in blocks[1][1]
    assert "+n" not in blocks[0][1]


def test_split_diff_empty_returns_empty():
    assert split_diff_by_file("") == []


def test_split_extracts_filename_for_deleted_binary_file():
    # 删除/二进制文件没有 +++ b/ 行,此前文件名为空 → 过滤(node_modules)会漏
    diff = ("diff --git a/node_modules/.bin/pbjs b/node_modules/.bin/pbjs\n"
            "deleted file mode 100755\n"
            "Binary files a/node_modules/.bin/pbjs and /dev/null differ\n")
    blocks = split_diff_by_file(diff)
    assert blocks[0][0] == "node_modules/.bin/pbjs"


def test_split_uses_new_path_for_rename():
    diff = ("diff --git a/old.py b/new.py\nsimilarity index 95%\n"
            "rename from old.py\nrename to new.py\n")
    blocks = split_diff_by_file(diff)
    assert blocks[0][0] == "new.py"
