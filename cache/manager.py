import json, hashlib, time, os
import redis as redis_lib
import yaml

config = yaml.safe_load(open("config.yaml"))

class CacheManager:
    def __init__(self):
        redis_url = os.getenv(config["databases"]["redis"]["url_env"], "redis://localhost:6379/0")
        self.redis = redis_lib.from_url(redis_url)
        self.cfg   = config.get("cache", {})

    def get_semantic(self, query: str, threshold: float = None) -> str | None:
        cfg = self.cfg.get("semantic_cache", {})
        if not cfg.get("enabled"): return None
        threshold = threshold or cfg.get("similarity_threshold", 0.95)
        from embeddings.adapter import embed_query
        q_vec = embed_query(query)
        import numpy as np
        for key in self.redis.keys("sem_cache:*")[:200]:
            cached = self.redis.get(key)
            if not cached: continue
            entry = json.loads(cached)
            sim = float(np.dot(q_vec, entry["vector"]) /
                        (np.linalg.norm(q_vec) * np.linalg.norm(entry["vector"]) + 1e-8))
            if sim >= threshold:
                return entry["answer"]
        return None

    def set_semantic(self, query: str, answer: str):
        cfg = self.cfg.get("semantic_cache", {})
        if not cfg.get("enabled"): return
        from embeddings.adapter import embed_query
        key  = f"sem_cache:{hashlib.md5(query.encode()).hexdigest()}"
        data = {"query":query,"answer":answer,"vector":embed_query(query),"ts":time.time()}
        self.redis.setex(key, cfg.get("ttl_sec",3600), json.dumps(data))

    def get_embedding(self, text: str) -> list | None:
        cfg = self.cfg.get("embedding_cache", {})
        if not cfg.get("enabled"): return None
        cached = self.redis.get(f"emb:{hashlib.sha256(text.encode()).hexdigest()}")
        return json.loads(cached) if cached else None

    def set_embedding(self, text: str, vector: list):
        cfg = self.cfg.get("embedding_cache", {})
        if not cfg.get("enabled"): return
        self.redis.setex(f"emb:{hashlib.sha256(text.encode()).hexdigest()}",
                         cfg.get("ttl_sec",86400), json.dumps(vector))

    def get_graph(self, cache_key: str) -> dict | None:
        cfg = self.cfg.get("graph_traversal_cache", {})
        if not cfg.get("enabled"): return None
        cached = self.redis.get(f"graph:{cache_key}")
        return json.loads(cached) if cached else None

    def set_graph(self, cache_key: str, data: dict):
        cfg = self.cfg.get("graph_traversal_cache", {})
        if not cfg.get("enabled"): return
        self.redis.setex(f"graph:{cache_key}", cfg.get("ttl_sec",300), json.dumps(data))

cache_mgr = CacheManager()

def patch_embedder_with_cache():
    from embeddings import adapter
    orig_embed = adapter.embedder.embed
    def cached_embed(text: str, mode: str = "document") -> list:
        cached = cache_mgr.get_embedding(f"{mode}:{text}")
        if cached: return cached
        result = orig_embed(text, mode)
        cache_mgr.set_embedding(f"{mode}:{text}", result)
        return result
    adapter.embedder.embed = cached_embed
