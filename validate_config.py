import os, yaml
from pathlib import Path

config = yaml.safe_load(open("config.yaml"))

def validate_llm():
    errors = []
    ollama_checked = False
    for role in ["main","batch","vision"]:
        c = config["llm"].get(role,{})
        env = c.get("api_key_env","")
        if c.get("provider") == "ollama":
            if not ollama_checked:
                _check_ollama(c.get("base_url","http://localhost:11434/v1"))
                ollama_checked = True
        elif env and not os.getenv(env):
            errors.append(f"  LLM [{role}]: {env} not set")
    if errors: raise EnvironmentError("Missing LLM API keys:\n"+"\n".join(errors))
    for role in ["main","batch","vision"]:
        c = config["llm"][role]
        print(f"  LLM [{role}]: {c['provider']}/{c['model']} OK")

def _check_ollama(base_url: str):
    import httpx
    api_url = base_url.replace("/v1", "").rstrip("/")
    try:
        r = httpx.get(f"{api_url}/api/tags", timeout=10)
        assert r.status_code == 200
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"  Ollama: connected, {len(models)} models available")
        if models:
            print(f"    Models: {', '.join(models[:10])}")
    except Exception as e:
        raise RuntimeError(f"Ollama not reachable at {api_url}: {e}\n"
                           f"  Run: docker compose up -d ollama && make pull-models")

def validate_embeddings():
    p = config["embeddings"]["provider"]
    c = config["embeddings"][p]
    env = c.get("api_key_env","")
    if p not in ("local","ollama") and env and not os.getenv(env):
        raise EnvironmentError(f"Embedding [{p}]: {env} not set")
    print(f"  Embeddings: {p}/{c.get('model','?')} OK")

def validate_vector_store():
    p = config["vector_store"]["provider"]
    c = config["vector_store"][p]
    if p == "qdrant":
        import httpx
        try:
            r = httpx.get(f"http://{c['host']}:{c['port']}/readyz",timeout=5)
            assert r.status_code == 200
            print(f"  VectorStore: qdrant @ {c['host']}:{c['port']} OK")
        except Exception as e:
            raise RuntimeError(f"Qdrant not reachable: {e}")
    else:
        print(f"  VectorStore: {p} configured")

def validate_databases():
    pg_url = os.getenv("POSTGRES_URL","")
    if not pg_url: raise EnvironmentError("POSTGRES_URL not set")
    import psycopg2
    try:
        conn = psycopg2.connect(pg_url); conn.close()
        print("  PostgreSQL: connected OK")
    except Exception as e:
        raise RuntimeError(f"PostgreSQL connection failed: {e}")
    redis_url = os.getenv("REDIS_URL","redis://localhost:6379/0")
    import redis as r
    try:
        r.from_url(redis_url).ping()
        print("  Redis: connected OK")
    except Exception as e:
        raise RuntimeError(f"Redis connection failed: {e}")

def validate_watch_folder():
    from utils.paths import get_watch_folder, is_windows_mount
    folder = get_watch_folder()
    print(f"  Watch folder: {folder}")
    if is_windows_mount(str(folder)):
        import warnings
        warnings.warn("Watch folder is on Windows FS (/mnt/c/...). Move to ~/data/ for better performance.")
    try:
        watches = int(open("/proc/sys/fs/inotify/max_user_watches").read())
        if watches < 524288:
            print(f"  WARNING: inotify watches={watches} < 524288")
    except Exception:
        pass

def validate_all():
    print("\n=== Validating configuration ===")
    validate_llm()
    validate_embeddings()
    validate_vector_store()
    validate_databases()
    validate_watch_folder()
    print("=== All checks passed ===\n")

if __name__ == "__main__":
    validate_all()
