"""MCP client — load enabled tools and execute them via SSE transport."""
import json, logging, asyncio
from database import get_db

logger = logging.getLogger(__name__)


def get_enabled_mcp_tools() -> tuple:
    """Returns (tools_for_llm, tool_map) where tool_map maps tool_name -> server info."""
    db = get_db()
    rows = db.fetch("""
        SELECT t.tool_name, t.description, t.input_schema,
               s.url, s.api_key, s.name as server_name
        FROM mcp_tools t
        JOIN mcp_servers s ON t.server_id = s.id
        WHERE t.enabled = TRUE AND s.enabled = TRUE
    """)

    tools_for_llm = []
    tool_map = {}

    for r in rows:
        name = r["tool_name"]
        schema = r["input_schema"] if isinstance(r["input_schema"], dict) else json.loads(r["input_schema"] or "{}")
        tools_for_llm.append({
            "type": "function",
            "function": {
                "name": name,
                "description": (r.get("description") or "")[:200],
                "parameters": schema
            }
        })
        tool_map[name] = {
            "url": r["url"],
            "api_key": r.get("api_key"),
            "server_name": r["server_name"]
        }

    return tools_for_llm, tool_map


def call_mcp_tool(tool_name: str, arguments: dict, tool_map: dict) -> str:
    """Execute an MCP tool call via SSE transport. Runs async in sync context."""
    server = tool_map.get(tool_name)
    if not server:
        return f"Error: unknown MCP tool '{tool_name}'"

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            _call_mcp_tool_async(server["url"], server.get("api_key"), tool_name, arguments)
        )
        loop.close()
        return result
    except Exception as e:
        logger.error(f"MCP tool {tool_name} failed: {e}")
        return f"Error calling {tool_name}: {e}"


async def _call_mcp_tool_async(url: str, api_key: str, tool_name: str, arguments: dict) -> str:
    """Full MCP SSE handshake + tools/call."""
    import aiohttp

    # Detect SSE transport
    is_sse = url.rstrip("/").endswith("/sse")
    if not is_sse:
        return await _call_mcp_http(url, api_key, tool_name, arguments)

    base_url = url.rsplit("/sse", 1)[0]
    parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
    headers = {"Host": parsed.netloc}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Docker: localhost -> host.docker.internal
    docker_url = url.replace("://localhost", "://host.docker.internal")
    docker_base = docker_url.rsplit("/sse", 1)[0]

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(docker_url) as sse:
            ep = None
            initialized = False

            async for raw_line in sse.content:
                text = raw_line.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue

                # Get session endpoint
                if text.startswith("data: ") and "/messages/" in text and not ep:
                    ep = text[6:].strip()
                    # Initialize
                    await session.post(docker_base + ep, json={
                        "jsonrpc": "2.0", "method": "initialize", "id": 1,
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "graphrag-agent", "version": "1.0.0"}
                        }
                    })

                elif text.startswith("data: ") and ep:
                    data = text[6:].strip()
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    # After initialize, send initialized + tools/call
                    if msg.get("id") == 1 and "result" in msg and not initialized:
                        initialized = True
                        await session.post(docker_base + ep, json={
                            "jsonrpc": "2.0", "method": "notifications/initialized"
                        })
                        # Call the tool
                        await session.post(docker_base + ep, json={
                            "jsonrpc": "2.0", "method": "tools/call", "id": 2,
                            "params": {"name": tool_name, "arguments": arguments}
                        })

                    # Receive tool result
                    elif msg.get("id") == 2:
                        if "result" in msg:
                            content = msg["result"].get("content", [])
                            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                            return "\n".join(texts) if texts else json.dumps(msg["result"])
                        elif "error" in msg:
                            return f"MCP error: {msg['error'].get('message', str(msg['error']))}"

    return "MCP tool call timed out"


async def _call_mcp_http(url: str, api_key: str, tool_name: str, arguments: dict) -> str:
    """Direct HTTP JSON-RPC tool call (non-SSE servers)."""
    import httpx
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        r = await client.post(url, json={
            "jsonrpc": "2.0", "method": "tools/call", "id": 1,
            "params": {"name": tool_name, "arguments": arguments}
        })
        data = r.json()
        if "result" in data:
            content = data["result"].get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(data["result"])
        return json.dumps(data)
