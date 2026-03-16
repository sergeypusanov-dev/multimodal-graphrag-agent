from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os, time, yaml, threading

config = yaml.safe_load(open("config.yaml"))
security_cfg = config.get("security", {})
bearer = HTTPBearer(auto_error=False)

API_KEY = os.getenv(config["a2a"]["auth"].get("api_key_env", "A2A_API_KEY"), "")

async def verify_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer)
):
    if not config["a2a"]["auth"].get("enabled", False):
        return True
    if not creds:
        raise HTTPException(401, "Missing Authorization header")
    if creds.credentials != API_KEY:
        raise HTTPException(403, "Invalid API key")
    return True

class CircuitBreaker:
    CLOSED = "closed"; OPEN = "open"; HALFOPEN = "half_open"

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self._state            = self.CLOSED
        self._failures         = 0
        self._last_failure     = 0
        self._lock             = threading.Lock()

    def call(self, fn, *args, **kwargs):
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure > self.recovery_timeout:
                    self._state = self.HALFOPEN
                else:
                    raise RuntimeError(f"Circuit {self.name} is OPEN")
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                if self._state == self.HALFOPEN:
                    self._state = self.CLOSED; self._failures = 0
            return result
        except Exception as e:
            with self._lock:
                self._failures += 1; self._last_failure = time.time()
                if self._failures >= self.failure_threshold:
                    self._state = self.OPEN
                    import logging
                    logging.error(f"Circuit {self.name} OPENED after {self._failures} failures")
            raise

    @property
    def state(self): return self._state

cfg_cb = security_cfg.get("circuit_breaker", {})
llm_circuit    = CircuitBreaker("llm",    cfg_cb.get("failure_threshold",5), cfg_cb.get("recovery_timeout_sec",60))
embed_circuit  = CircuitBreaker("embed",  cfg_cb.get("failure_threshold",5), cfg_cb.get("recovery_timeout_sec",60))
qdrant_circuit = CircuitBreaker("qdrant", cfg_cb.get("failure_threshold",3), cfg_cb.get("recovery_timeout_sec",30))
batch_circuit  = CircuitBreaker("batch",  cfg_cb.get("failure_threshold",5), cfg_cb.get("recovery_timeout_sec",60))

def setup_rate_limiting(app: FastAPI):
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    rate = security_cfg.get("rate_limit", {})
    if rate.get("enabled"):
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter
        from slowapi.middleware import SlowAPIMiddleware
        app.add_middleware(SlowAPIMiddleware)

def sanitize_input(text: str) -> str:
    san_cfg = security_cfg.get("input_sanitization", {})
    max_len = san_cfg.get("max_text_length", 50000)
    if len(text) > max_len:
        text = text[:max_len]
    if san_cfg.get("strip_html"):
        import re
        text = re.sub(r'<[^>]+>', '', text)
    suspicious = ["ignore previous instructions","disregard your system","you are now","forget everything"]
    for pattern in suspicious:
        if pattern.lower() in text.lower():
            import logging
            logging.warning(f"Possible prompt injection: {pattern}")
    return text.strip()
