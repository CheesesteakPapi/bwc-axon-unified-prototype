"""Bounded, process-local support diagnostics. No payloads, paths or identities."""
from collections import deque
from datetime import datetime, timezone
import threading
import time
import uuid


class LocalDiagnostics:
    def __init__(self):
        self._rows = deque(maxlen=200)
        self._lock = threading.Lock()

    def record(self, request_id, method, status, duration_ms):
        with self._lock:
            self._rows.append({"requestId": request_id, "method": method if method in {"GET", "POST", "DELETE"} else "OTHER",
                               "status": int(status), "durationMs": round(max(0, duration_ms), 1),
                               "at": datetime.now(timezone.utc).isoformat()})

    def snapshot(self):
        with self._lock:
            rows = list(self._rows)
        return {"retention": "Last 200 requests in this process; cleared on exit. No credentials, URLs or personnel records.",
                "requests": rows, "count": len(rows), "failed": sum(row["status"] >= 400 for row in rows)}


class DiagnosticHandlerMixin:
    def handle_one_request(self):
        self._diagnostic_id = uuid.uuid4().hex
        self._diagnostic_status = 0
        started = time.monotonic()
        try:
            return super().handle_one_request()
        finally:
            if self._diagnostic_status:
                try:
                    self.state.diagnostics.record(self._diagnostic_id, self.command, self._diagnostic_status,
                                                  (time.monotonic() - started) * 1000)
                except Exception:
                    pass  # Diagnostics cannot fail a business operation.

    def send_response(self, code, message=None):
        self._diagnostic_status = int(code)
        super().send_response(code, message)
        self.send_header("X-BWC-Request-ID", getattr(self, "_diagnostic_id", ""))

    def log_message(self, *args):
        pass  # Never print request paths or user-controlled exception content.
