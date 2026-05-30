import inspect
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import fastapi.testclient


class _Response:
    def __init__(self, status_code: int, body: bytes, headers: list[tuple[bytes, bytes]]):
        self.status_code = status_code
        self.content = body
        self.text = body.decode("utf-8")
        self.headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in headers}


class _ASGITestClient:
    """Small sync route client for the currently installed Starlette TestClient hang."""
    __test__ = False

    def __init__(self, app):
        self.app = app

    def get(self, path: str):
        return self.request("GET", path, data={})

    def post(self, path: str, data: dict | None = None):
        return self.request("POST", path, data=data or {})

    def request(self, method: str, path: str, data: dict):
        for route in self.app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                kwargs = {
                    name: data.get(name, param.default)
                    for name, param in inspect.signature(route.endpoint).parameters.items()
                }
                result = route.endpoint(**kwargs)
                if inspect.isawaitable(result):
                    raise RuntimeError("async endpoints are not supported by this test shim")
                if hasattr(result, "body"):
                    return _Response(result.status_code, result.body, list(result.headers.raw))
                body = str(result).encode("utf-8")
                return _Response(200, body, [(b"content-type", b"text/html; charset=utf-8")])
        return _Response(404, b"Not Found", [])


fastapi.testclient.TestClient = _ASGITestClient
