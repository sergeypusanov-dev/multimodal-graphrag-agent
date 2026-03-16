import httpx, asyncio, json, yaml, os
from dataclasses import dataclass

config  = yaml.safe_load(open("config.yaml"))
API_KEY = os.getenv(config["a2a"]["auth"].get("api_key_env","A2A_API_KEY"),"")

@dataclass
class AgentInfo:
    url: str; name: str; skills: list; input_modes: list

class A2AClient:
    def __init__(self):
        self._agents: dict = {}
        for peer in config["a2a"].get("registry",{}).get("peer_agents",[]):
            self._agents[peer["name"].lower()] = AgentInfo(
                url=peer["url"],name=peer["name"],skills=[],input_modes=["text"])

    def _headers(self):
        return {"Authorization":f"Bearer {API_KEY}"} if config["a2a"]["auth"]["enabled"] else {}

    async def discover(self, url: str) -> AgentInfo:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{url}/.well-known/agent.json", timeout=10)
            card = r.json()
        info = AgentInfo(url=url,name=card["name"],
                         skills=[s["id"] for s in card.get("skills",[])],
                         input_modes=card.get("defaultInputModes",["text"]))
        self._agents[card["name"].lower()] = info
        return info

    async def send_task(self, agent_name_or_url: str, text: str,
                        files: list = None, timeout: int = 120) -> str:
        key   = agent_name_or_url.lower()
        agent = self._agents.get(key) or await self.discover(agent_name_or_url)
        parts = [{"type":"text","text":text}]
        for f in (files or []):
            parts.append({"type":"file","file":{"name":f.get("name"),
                          "mimeType":f.get("mime"),"bytes":f.get("data_b64")}})
        async with httpx.AsyncClient(timeout=timeout, headers=self._headers()) as c:
            r   = await c.post(f"{agent.url}/a2a/tasks/send",
                               json={"message":{"role":"user","parts":parts}})
            tid = r.json()["id"]
            while True:
                await asyncio.sleep(1)
                r  = await c.get(f"{agent.url}/a2a/tasks/{tid}")
                st = r.json()["status"]["state"]
                if st == "completed":
                    arts = r.json().get("artifacts",[])
                    return arts[0]["parts"][0].get("text","") if arts else ""
                elif st in ("failed","cancelled"):
                    raise RuntimeError(f"Agent task {st}")

a2a_client = A2AClient()

DELEGATE_TOOL = {
    "name":"delegate_to_agent",
    "description":"""Delegate to a specialist agent via A2A.
Available: DataAnalyst, Translator.
Use when task is outside your knowledge base scope.""",
    "input_schema":{"type":"object","properties":{
        "agent_name":{"type":"string"},"task":{"type":"string"}},
    "required":["agent_name","task"]}
}
