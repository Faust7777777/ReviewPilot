"""只读仓库工作区:给 Review Loop 的 read_file / search 工具用。

来源:本地仓库目录,或浅 clone 的临时目录。所有操作只读 + 路径穿越防护。
"""
import subprocess
import tempfile
from pathlib import Path


class RepoWorkspace:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _safe(self, path: str) -> Path | None:
        p = (self.root / (path or "")).resolve()
        try:
            p.relative_to(self.root)        # 防路径穿越(../ 逃出仓库)
        except ValueError:
            return None
        return p

    def read_file(self, path: str, start: int = 1, end: int | None = None,
                  max_lines: int = 150) -> str:
        p = self._safe(path)
        if p is None or not p.is_file():
            return f"(找不到文件:{path})"
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError as exc:
            return f"(读取失败:{exc})"
        start = max(1, int(start or 1))
        end = int(end) if end else start + max_lines - 1
        end = min(end, len(lines), start + max_lines - 1)
        chunk = lines[start - 1:end]
        body = "\n".join(f"{i}: {ln}" for i, ln in enumerate(chunk, start))
        return f"{path} [{start}-{end} / 共{len(lines)}行]:\n{body}" if chunk else f"({path} 该范围为空)"

    def search(self, query: str, max_results: int = 30) -> str:
        if not (query or "").strip():
            return "(空查询)"
        try:
            out = subprocess.run(
                ["rg", "-n", "--no-heading", "-S", "--", query, "."],
                cwd=self.root, capture_output=True, text=True, timeout=20).stdout
        except FileNotFoundError:
            out = subprocess.run(
                ["grep", "-rn", "--", query, "."],
                cwd=self.root, capture_output=True, text=True).stdout
        hits = [ln.lstrip("./") for ln in out.splitlines()][:max_results]
        return "\n".join(hits) if hits else "(无匹配)"

    @classmethod
    def clone(cls, repo: str, ref: str | None = None) -> "RepoWorkspace":
        """浅 clone owner/repo 到临时目录(只读用)。"""
        tmp = tempfile.mkdtemp(prefix="rp_ws_")
        url = repo if repo.startswith("http") else f"https://github.com/{repo}"
        subprocess.run(
            ["git", "-c", "http.version=HTTP/1.1", "clone", "--depth", "1", "--quiet", url, tmp],
            check=True, capture_output=True, text=True)
        return cls(tmp)
