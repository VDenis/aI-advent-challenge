import asyncio
import json
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from . import storage
from .models import MessageRequest, MessageResponse, Task, TaskCreate, TaskIdRequest


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    async def connect(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    async def disconnect(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def broadcast(self, event: str, data: Any) -> None:
        payload = {"event": event, "data": data}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop if backpressure to keep things simple
                pass


broadcaster = Broadcaster()
storage.ensure_data_files()

app = FastAPI(title="MCP Scheduler Server", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def task_to_dict(task: Task) -> Dict[str, Any]:
    return task.dict()


@app.get("/sse")
async def sse(request: Request):
    queue = await broadcaster.connect()
    initial_tasks = [task_to_dict(t) for t in storage.list_tasks()]

    async def event_generator():
        try:
            yield {"event": "tasks_snapshot", "data": json.dumps(initial_tasks)}
            while True:
                payload = await queue.get()
                if await request.is_disconnected():
                    break
                yield {"event": payload["event"], "data": json.dumps(payload["data"])}
        finally:
            await broadcaster.disconnect(queue)

    return EventSourceResponse(event_generator())


def _handle_tool_call(message: MessageRequest) -> Any:
    if message.tool == "task_add":
        data = TaskCreate(**message.arguments)
        task = storage.create_task(data.text, data.remind_at)
        return {"event": "task_added", "payload": task_to_dict(task)}
    if message.tool == "task_list":
        tasks = [task_to_dict(t) for t in storage.list_tasks()]
        return {"event": "task_list", "payload": tasks}
    if message.tool == "task_done":
        req = TaskIdRequest(**message.arguments)
        try:
            task = storage.set_task_status(req.id, "done")
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        return {"event": "task_done", "payload": task_to_dict(task)}
    if message.tool == "task_delete":
        req = TaskIdRequest(**message.arguments)
        storage.delete_task(req.id)
        return {"event": "task_deleted", "payload": {"id": req.id}}
    raise HTTPException(status_code=400, detail="Unsupported tool")


@app.post("/messages", response_model=MessageResponse)
async def messages(message: MessageRequest):
    try:
        result = _handle_tool_call(message)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result["event"] in {"task_added", "task_done", "task_deleted"}:
        await broadcaster.broadcast(result["event"], result["payload"])

    return MessageResponse(type="result", content=result["payload"])


@app.get("/health")
async def health():
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    uvicorn.run(
        "mcp_scheduler_server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
