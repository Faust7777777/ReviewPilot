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

    def exists(self, path: str) -> bool:
        """该路径是否为仓库内真实文件(grounding 用:区分"真读到"与"幻觉路径")。"""
        p = self._safe(path)
        return bool(p and p.is_file())

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


class DictWorkspace:
    """内存工作区(给 eval / 测试用):文件来自 {path: text} 字典,无需真 clone。
    实现与 RepoWorkspace 相同的 read_file / search / exists 接口,供 Review Loop 取证。"""

    def __init__(self, files: dict[str, str]):
        self.files = dict(files or {})

    def exists(self, path: str) -> bool:
        return path in self.files

    def read_file(self, path: str, start: int = 1, end: int | None = None,
                  max_lines: int = 150) -> str:
        if path not in self.files:
            return f"(找不到文件:{path})"
        lines = self.files[path].splitlines()
        start = max(1, int(start or 1))
        end = int(end) if end else start + max_lines - 1
        end = min(end, len(lines), start + max_lines - 1)
        chunk = lines[start - 1:end]
        body = "\n".join(f"{i}: {ln}" for i, ln in enumerate(chunk, start))
        return f"{path} [{start}-{end} / 共{len(lines)}行]:\n{body}" if chunk else f"({path} 该范围为空)"

    def search(self, query: str, max_results: int = 30) -> str:
        q = (query or "").strip()
        if not q:
            return "(空查询)"
        hits = [f"{path}:{i}:{ln}"
                for path, text in self.files.items()
                for i, ln in enumerate(text.splitlines(), 1) if q in ln]
        return "\n".join(hits[:max_results]) if hits else "(无匹配)"
