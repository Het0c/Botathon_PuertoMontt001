import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(url: str, token: str | None = None, payload: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=raw, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_real_http_openapi_auth_and_idempotent_import():
    port = free_port()
    rpa_key = "test-rpa-key-with-24-characters"
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env.update(
            APP_ENV="development",
            DATABASE_URL=f"sqlite:///{Path(tmp) / 'api.db'}",
            RPA_API_KEY=rpa_key,
            USER_API_KEY="test-user-key-with-24-chars",
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(50):
                try:
                    status, health = request(base + "/health")
                    if status == 200:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("La API no inició")
            assert health["excelProcessing"] is False
            assert request(base + "/api/v1/rpa/contracts/snapshot")[0] == 401
            status, schema = request(base + "/api/v1/openapi.json")
            assert status == 200 and "/api/v1/rpa/imports" in schema["paths"]
            payload = {
                "source": "BUK",
                "filename": "Nac - Base contratos x mes.xlsx",
                "fileHash": "a" * 64,
                "idempotencyKey": "http-import-001",
            }
            first_status, first = request(base + "/api/v1/rpa/imports", rpa_key, payload)
            second_status, second = request(base + "/api/v1/rpa/imports", rpa_key, payload)
            assert first_status == 201 and second_status == 200
            assert first["importacionId"] == second["importacionId"] and second["reutilizada"]
        finally:
            process.terminate()
            process.wait(timeout=10)
