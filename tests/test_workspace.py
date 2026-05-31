from reviewpilot.workspace import RepoWorkspace


def test_read_file_returns_numbered_lines(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    ws = RepoWorkspace(str(tmp_path))
    out = ws.read_file("a.py")
    assert "def f():" in out and "1: def f():" in out


def test_read_file_blocks_path_traversal(tmp_path):
    ws = RepoWorkspace(str(tmp_path))
    assert "找不到文件" in ws.read_file("../../../etc/passwd")


def test_read_file_respects_line_range(tmp_path):
    (tmp_path / "b.py").write_text("\n".join(f"line{i}" for i in range(1, 21)))
    ws = RepoWorkspace(str(tmp_path))
    out = ws.read_file("b.py", start=5, end=7)
    assert "5: line5" in out and "7: line7" in out and "line9" not in out


def test_search_finds_match(tmp_path):
    (tmp_path / "a.py").write_text("alpha\nBETA_token here\n")
    ws = RepoWorkspace(str(tmp_path))
    out = ws.search("BETA_token")
    assert "BETA_token" in out and "a.py" in out
