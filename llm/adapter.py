import os, yaml
from dataclasses import dataclass

config = yaml.safe_load(open("config.yaml"))

@dataclass
class LLMResponse:
    text: str; model: str; tokens_in: int; tokens_out: int; provider: str

class LLMAdapter:
    def __init__(self, role: str = "main"):
        self.cfg = config["llm"][role]
        self.provider = self.cfg["provider"]
        self.model    = self.cfg["model"]
        self.api_key  = os.getenv(self.cfg.get("api_key_env", ""), "")
        self._client  = None

    @property
    def client(self):
        if self._client: return self._client
        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
        elif self.provider == "ollama":
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.cfg.get("base_url","http://localhost:11434/v1"),
                api_key="ollama")
        return self._client

    def chat(self, messages, system=None, tools=None) -> LLMResponse:
        try:
            return self._call(messages, system, tools)
        except Exception as e:
            fb = config["llm"].get("fallback", {})
            if fb.get("enabled") and self.provider != "fallback":
                import logging
                logging.warning(f"LLM {self.provider} failed: {e}. Fallback.")
                return LLMAdapter("fallback")._call(messages, system, tools)
            raise

    def _call(self, messages, system, tools) -> LLMResponse:
        max_tok = self.cfg.get("max_tokens", 1024)
        temp    = self.cfg.get("temperature", 0.1)
        if self.provider == "anthropic":
            kw = dict(model=self.model, max_tokens=max_tok,
                      messages=messages, temperature=temp)
            if system: kw["system"] = system
            if tools:  kw["tools"]  = tools
            r = self.client.messages.create(**kw)
            return LLMResponse(r.content[0].text, r.model,
                               r.usage.input_tokens, r.usage.output_tokens, "anthropic")
        elif self.provider in ("openai", "ollama"):
            msgs = ([{"role":"system","content":system}] + messages) if system else messages
            kw = dict(model=self.model, messages=msgs,
                      max_tokens=max_tok, temperature=temp)
            if tools: kw["tools"] = tools
            r = self.client.chat.completions.create(**kw)
            return LLMResponse(r.choices[0].message.content, r.model,
                               r.usage.prompt_tokens, r.usage.completion_tokens, self.provider)
        elif self.provider == "gemini":
            prompt = "\n".join(m["content"] for m in messages)
            if system: prompt = f"{system}\n\n{prompt}"
            r = self.client.generate_content(prompt)
            return LLMResponse(r.text, self.model,
                               r.usage_metadata.prompt_token_count,
                               r.usage_metadata.candidates_token_count, "gemini")

    def chat_with_vision(self, text, images_b64, system=None) -> LLMResponse:
        if self.provider == "anthropic":
            content = [{"type":"image","source":{"type":"base64",
                        "media_type":"image/jpeg","data":img}} for img in images_b64]
            content.append({"type":"text","text":text})
            return self.chat([{"role":"user","content":content}], system)
        elif self.provider in ("openai", "ollama"):
            content = [{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{img}"}}
                       for img in images_b64]
            content.append({"type":"text","text":text})
            return self.chat([{"role":"user","content":content}], system)
        else:
            return self.chat([{"role":"user","content":text}], system)

main_llm   = LLMAdapter("main")
batch_llm  = LLMAdapter("batch")
vision_llm = LLMAdapter("vision")
