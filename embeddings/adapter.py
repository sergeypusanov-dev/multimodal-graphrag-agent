import os, yaml
config = yaml.safe_load(open("config.yaml"))

class EmbeddingAdapter:
    def __init__(self):
        self.provider = config["embeddings"]["provider"]
        self.cfg      = config["embeddings"][self.provider]
        self.dims     = self.cfg.get("dimensions", 1536)
        self._client  = None

    @property
    def client(self):
        if self._client: return self._client
        p = self.provider
        if p == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=os.getenv(self.cfg["api_key_env"]))
            self._client = genai
        elif p == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=os.getenv(self.cfg["api_key_env"]))
        elif p == "cohere":
            import cohere
            self._client = cohere.Client(os.getenv(self.cfg["api_key_env"]))
        elif p == "voyage":
            import voyageai
            self._client = voyageai.Client(api_key=os.getenv(self.cfg["api_key_env"]))
        elif p == "local":
            from sentence_transformers import SentenceTransformer
            self._client = SentenceTransformer(self.cfg["model"],
                                               device=self.cfg.get("device","cpu"))
        elif p == "ollama":
            from openai import OpenAI
            self._client = OpenAI(base_url=f"{self.cfg['base_url']}/v1", api_key="ollama")
        return self._client

    def embed(self, text: str, mode: str = "document") -> list:
        return self.embed_batch([text], mode)[0]

    def embed_batch(self, texts: list, mode: str = "document") -> list:
        p = self.provider
        if p == "gemini":
            task = self.cfg["task_types"].get(mode, "RETRIEVAL_DOCUMENT")
            r = self.client.embed_content(model=f"models/{self.cfg['model']}",
                                          content=texts, task_type=task,
                                          output_dimensionality=self.dims)
            vecs = r["embedding"]
            return vecs if isinstance(vecs[0], list) else [vecs]
        elif p == "openai":
            r = self.client.embeddings.create(model=self.cfg["model"],
                                              input=texts, dimensions=self.dims)
            return [e.embedding for e in r.data]
        elif p == "cohere":
            it = self.cfg["input_types"].get(mode, "search_document")
            return self.client.embed(texts=texts, model=self.cfg["model"], input_type=it).embeddings
        elif p == "voyage":
            it = self.cfg["input_types"].get(mode, "document")
            return self.client.embed(texts, model=self.cfg["model"], input_type=it).embeddings
        elif p == "local":
            return self.client.encode(texts, normalize_embeddings=True).tolist()
        elif p == "ollama":
            return [self.client.embeddings.create(model=self.cfg["model"], input=t).data[0].embedding
                    for t in texts]

embedder       = EmbeddingAdapter()
embed_document = lambda t: embedder.embed(t, "document")
embed_query    = lambda t: embedder.embed(t, "query")
embed_batch    = lambda ts, m="document": embedder.embed_batch(ts, m)
