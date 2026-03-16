from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from enum import Enum
import uuid, asyncio, json
from security.middleware import verify_auth

router = APIRouter(prefix="/a2a")

class TaskState(str, Enum):
    SUBMITTED="submitted"; WORKING="working"; COMPLETED="completed"
    FAILED="failed"; CANCELLED="cancelled"

class TaskSendRequest(BaseModel):
    id: Optional[str] = None
    message: dict
    metadata: Optional[dict] = None

_tasks: dict = {}
_queues: dict = {}

def _extract_input(message: dict) -> tuple:
    texts, files = [], []
    for part in message.get("parts",[]):
        if part.get("type")=="text": texts.append(part["text"])
        elif part.get("type")=="file": files.append({
            "path":part.get("file",{}).get("uri"),
            "mime":part.get("file",{}).get("mimeType"),
            "data_b64":part.get("file",{}).get("bytes")})
        elif part.get("type")=="data": texts.append(json.dumps(part.get("data",{})))
    return " ".join(texts), files

async def _run_task(task_id: str, text: str, files: list):
    from agent.graph import run_agent
    q = _queues[task_id]
    try:
        _tasks[task_id]["status"] = {"state":TaskState.WORKING}
        await q.put({"type":"status","status":{"state":TaskState.WORKING}})
        answer = await asyncio.get_event_loop().run_in_executor(None, run_agent, text, files, task_id)
        artifact = {"index":0,"parts":[{"type":"text","text":answer}]}
        _tasks[task_id].update({"status":{"state":TaskState.COMPLETED},"artifacts":[artifact]})
        await q.put({"type":"artifact","artifact":artifact})
        await q.put({"type":"status","status":{"state":TaskState.COMPLETED}})
    except Exception as e:
        _tasks[task_id]["status"] = {"state":TaskState.FAILED,"message":str(e)}
        await q.put({"type":"status","status":{"state":TaskState.FAILED}})
    finally:
        await q.put(None)

@router.post("/tasks/send", dependencies=[Depends(verify_auth)])
async def send_task(req: TaskSendRequest):
    task_id = req.id or str(uuid.uuid4())
    text, files = _extract_input(req.message)
    _tasks[task_id] = {"id":task_id,"status":{"state":TaskState.SUBMITTED},"artifacts":[]}
    _queues[task_id] = asyncio.Queue()
    asyncio.create_task(_run_task(task_id, text, files))
    return _tasks[task_id]

@router.get("/tasks/{task_id}", dependencies=[Depends(verify_auth)])
async def get_task(task_id: str):
    if task_id not in _tasks: raise HTTPException(404,"Task not found")
    return _tasks[task_id]

@router.post("/tasks/{task_id}/cancel", dependencies=[Depends(verify_auth)])
async def cancel_task(task_id: str):
    if task_id not in _tasks: raise HTTPException(404)
    _tasks[task_id]["status"] = {"state":TaskState.CANCELLED}
    return _tasks[task_id]

@router.get("/tasks/{task_id}/stream", dependencies=[Depends(verify_auth)])
async def stream_task(task_id: str):
    if task_id not in _queues: raise HTTPException(404)
    async def gen():
        while True:
            ev = await _queues[task_id].get()
            if ev is None: break
            yield f"data: {json.dumps(ev)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
