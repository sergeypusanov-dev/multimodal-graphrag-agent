import yaml, uuid
from dataclasses import dataclass
from typing import Optional
from embeddings.adapter import embed_document, embed_query, embedder

config = yaml.safe_load(open("config.yaml"))

@dataclass
class SearchResult:
    id: str; score: float; payload: dict

class VectorStoreAdapter:
    def __init__(self):
        self.provider   = config["vector_store"]["provider"]
        self.cfg        = config["vector_store"][self.provider]
        self.collection = config["vector_store"]["collection_name"]
        self.dims       = embedder.dims
        self._client    = None

    @property
    def client(self):
        if self._client: return self._client
        p = self.provider
        if p == "qdrant":
            from qdrant_client import QdrantClient
            import os
            self._client = QdrantClient(host=self.cfg["host"], port=self.cfg["port"],
                                        api_key=os.getenv(self.cfg.get("api_key_env",""),None),
                                        timeout=self.cfg.get("timeout",30))
            self._init_qdrant()
        elif p == "pgvector":
            import psycopg2, os
            self._client = psycopg2.connect(os.getenv(self.cfg["url_env"]))
        elif p == "pinecone":
            from pinecone import Pinecone
            import os
            self._client = Pinecone(api_key=os.getenv(self.cfg["api_key_env"])).Index(self.cfg["index_name"])
        elif p == "chroma":
            import chromadb
            self._client = chromadb.HttpClient(host=self.cfg["host"], port=self.cfg["port"])
        return self._client

    def _init_qdrant(self):
        from qdrant_client.models import Distance, VectorParams
        existing = [c.name for c in self._client.get_collections().collections]
        if self.collection not in existing:
            d = {"Cosine": Distance.COSINE, "Dot": Distance.DOT, "Euclidean": Distance.EUCLID}
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dims,
                                            distance=d.get(config["vector_store"]["distance"], Distance.COSINE)))
            for field in ["media_type","entity_id","doc_id","chunk_type"]:
                self._client.create_payload_index(self.collection, field, "keyword")

    def upsert(self, text: str, payload: dict, point_id=None) -> str:
        pid    = point_id or str(uuid.uuid4())
        vector = embed_document(text)
        p      = self.provider
        if p == "qdrant":
            from qdrant_client.models import PointStruct
            self.client.upsert(collection_name=self.collection,
                               points=[PointStruct(id=pid, vector=vector,
                                                   payload={**payload,"text":text[:2000]})])
        elif p == "pgvector":
            import json
            with self.client.cursor() as cur:
                cur.execute("""
                    INSERT INTO embeddings (id, embedding, text, payload)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET embedding=%s, text=%s, payload=%s
                """, [pid, vector, text[:2000], json.dumps(payload),
                      vector, text[:2000], json.dumps(payload)])
            self.client.commit()
        elif p == "chroma":
            self.client.get_or_create_collection(self.collection).upsert(
                ids=[pid], embeddings=[vector], documents=[text[:2000]], metadatas=[payload])
        return pid

    def search(self, query: str, top_k: int = 10, filters: dict = None) -> list:
        q_vec = embed_query(query)
        p     = self.provider
        if p == "qdrant":
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qf = Filter(must=[FieldCondition(key=k, match=MatchValue(value=v))
                               for k,v in filters.items()]) if filters else None
            result = self.client.query_points(collection_name=self.collection, query=q_vec,
                                              limit=top_k, query_filter=qf, with_payload=True)
            hits = result.points if hasattr(result, 'points') else result
            return [SearchResult(id=str(h.id), score=h.score, payload=h.payload or {}) for h in hits]
        elif p == "pgvector":
            with self.client.cursor() as cur:
                cur.execute("""SELECT id, 1-(embedding<=>%s), text, payload
                               FROM embeddings ORDER BY embedding<=>%s LIMIT %s""",
                            [q_vec, q_vec, top_k])
                return [SearchResult(id=r[0],score=r[1],payload={"text":r[2],**r[3]})
                        for r in cur.fetchall()]
        elif p == "chroma":
            col = self.client.get_or_create_collection(self.collection)
            r = col.query(query_embeddings=[q_vec], n_results=top_k)
            return [SearchResult(id=i,score=1-d,payload=m)
                    for i,d,m in zip(r["ids"][0],r["distances"][0],r["metadatas"][0])]
        raise ValueError(f"Unknown vector store: {p}")

vector_store  = VectorStoreAdapter()
store_chunk   = lambda text, payload, pid=None: vector_store.upsert(text, payload, pid)
search_chunks = lambda query, top_k=10, filters=None: vector_store.search(query, top_k, filters)
