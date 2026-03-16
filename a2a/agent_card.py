from fastapi import APIRouter
from fastapi.responses import JSONResponse
import yaml

config = yaml.safe_load(open("config.yaml"))
router = APIRouter()

def build_agent_card() -> dict:
    cfg = config["a2a"]
    return {
        "name": cfg["agent_name"],
        "description": cfg["description"],
        "url": cfg["agent_url"],
        "version": cfg["agent_version"],
        "provider": {"organization":"Custom","url":cfg["agent_url"]},
        "defaultInputModes": ["text","image","audio","video"],
        "defaultOutputModes": ["text","file","data"],
        "capabilities": {
            "streaming": cfg["capabilities"]["streaming"],
            "pushNotifications": cfg["capabilities"]["push_notifications"],
            "stateTransitionHistory": cfg["capabilities"]["state_transition_history"],
        },
        "skills": [{"id":s["id"],"name":s["name"],"description":s["description"],
                    "inputModes":s["input_modes"],"outputModes":s["output_modes"],
                    "tags":s["tags"]} for s in cfg["skills"]],
        "authentication": {"schemes":["apiKey"]} if cfg["auth"]["enabled"] else None,
    }

@router.get("/.well-known/agent.json")
async def get_agent_card():
    return JSONResponse(build_agent_card())
