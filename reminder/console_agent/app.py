import argparse
import os
from typing import AsyncIterator, Dict, List

import httpx
from dotenv import load_dotenv
from httpx_sse import connect_sse

from .ui import ReminderApp


class MCPClient:
    def __init__(self, messages_url: str, sse_url: str) -> None:
        self.messages_url = messages_url
        self.sse_url = sse_url
        self._client = httpx.AsyncClient(timeout=15)

    async def call_tool(self, tool: str, arguments: Dict) -> Dict:
        response = await self._client.post(self.messages_url, json={"tool": tool, "arguments": arguments})
        response.raise_for_status()
        data = response.json()
        return data.get("content", data)

    async def task_list(self) -> List[dict]:
        return await self.call_tool("task_list", {})

    async def task_add(self, text: str, remind_at: str) -> dict:
        return await self.call_tool("task_add", {"text": text, "remind_at": remind_at})

    async def stream_events(self) -> AsyncIterator:
        async with httpx.AsyncClient(timeout=None) as client:
            async with connect_sse(client, self.sse_url, method="GET") as event_source:
                async for event in event_source.aiter_sse():
                    yield event

    async def aclose(self) -> None:
        await self._client.aclose()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Console MCP reminder agent")
    parser.add_argument("--no-llm", action="store_true", help="disable GigaChat summary")
    args = parser.parse_args()

    messages_url = os.getenv("MCP_MESSAGES_URL", "http://localhost:8000/messages")
    sse_url = os.getenv("MCP_SSE_URL", "http://localhost:8000/sse")

    client = MCPClient(messages_url, sse_url)
    app = ReminderApp(client=client, use_llm=not args.no_llm)
    try:
        app.run()
    finally:
        import asyncio

        asyncio.run(client.aclose())


if __name__ == "__main__":
    main()
