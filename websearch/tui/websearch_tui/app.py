from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Iterable, List

from dotenv import load_dotenv
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from .clients.brave import BraveClient
from .clients.desktop_commander import DesktopCommanderClient
from .clients.gigachat_summary import GigaChatSummaryClient
from .clients.types import SearchResult


def _dedup(seq: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in seq:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _build_urls(env_value: str | None, service_host: str, service_port: int, host_port: int) -> List[str]:
    def _ensure_mcp_path(url: str) -> str:
        url = url.strip()
        if not url:
            return ""
        if url.rstrip("/").endswith("/mcp"):
            return url.rstrip("/")
        return url.rstrip("/") + "/mcp"

    manual = [_ensure_mcp_path(part) for part in (env_value or "").split(",") if part.strip()]
    defaults = [
        _ensure_mcp_path(f"http://localhost:{host_port}"),  # порт проброшен наружу compose
        _ensure_mcp_path(f"http://{service_host}:{service_port}"),  # имя сервиса внутри docker‑сети
        _ensure_mcp_path(f"http://host.docker.internal:{host_port}"),  # доступ к проброшенному порту из контейнера
    ]
    return _dedup([u for u in manual if u] + defaults)


def _normalize_workspace_path(path: str) -> str:
    """
    Map legacy `/mnt/workspace` to `/workspace` to match desktop-commander root.
    Keeps other paths intact.
    """
    legacy_prefix = "/mnt/workspace"
    if path.startswith(legacy_prefix):
        return path.replace(legacy_prefix, "/workspace", 1)
    return path


class WebSearchApp(App):
    CSS = """
    Screen {
        align: center top;
        padding: 1 2;
    }
    #controls {
        width: 100%;
        padding: 0 1;
    }
    #status {
        color: yellow;
    }
    #error {
        color: red;
    }
    #summary {
        width: 100%;
        border: round $primary;
        padding: 1;
        min-height: 6;
    }
    #results {
        height: 24;
    }
    """

    BINDINGS = [
        Binding("s", "summarize", "Саммари"),
        Binding("w", "save", "Сохранить"),
        Binding("q", "quit", "Выход"),
    ]

    def __init__(self) -> None:
        super().__init__()
        load_dotenv()

        project_root = _normalize_workspace_path(os.getenv("PROJECT_ROOT", "/workspace"))
        self.output_dir = _normalize_workspace_path(os.getenv("OUTPUT_DIR", f"{project_root}/output"))

        brave_urls = _build_urls(os.getenv("MCP_BRAVE_URL"), "brave-search", 3000, 3001)
        desktop_urls = _build_urls(os.getenv("MCP_DESKTOP_URL"), "desktop-commander", 3000, 3002)
        summary_urls = _build_urls(os.getenv("MCP_SUMMARY_URL"), "gigachat-summary", 3000, 3003)

        self._log_endpoints("Brave", brave_urls)
        self._log_endpoints("Desktop Commander", desktop_urls)
        self._log_endpoints("Summary", summary_urls)

        self.brave = BraveClient(brave_urls)
        self.desktop = DesktopCommanderClient(desktop_urls)
        self.summarizer = GigaChatSummaryClient(summary_urls)

        self.results: List[SearchResult] = []
        self.last_query: str = ""
        self.last_summary: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Веб-поиск (Brave MCP)", classes="title"),
            Input(placeholder="Введите запрос и нажмите Enter", id="query"),
            Horizontal(
                Button("Поиск", id="search", variant="primary"),
                Button("Саммари (s)", id="summarize", variant="success"),
                Button("Сохранить (w)", id="save", variant="warning"),
                id="controls",
            ),
            Static("", id="status"),
            Static("", id="error"),
            VerticalScroll(DataTable(id="results")),
            Static("Саммари появится здесь", id="summary"),
        )
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#results", DataTable)
        table.add_columns("№", "Заголовок", "URL", "Сниппет")

    @on(Input.Submitted)
    async def handle_submit(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            asyncio.create_task(self._run_search(query))

    @on(Button.Pressed)
    async def handle_button(self, event: Button.Pressed) -> None:
        if event.button.id == "search":
            query_input = self.query_one("#query", Input)
            query = query_input.value.strip()
            if query:
                asyncio.create_task(self._run_search(query))
        elif event.button.id == "summarize":
            asyncio.create_task(self.action_summarize())
        elif event.button.id == "save":
            asyncio.create_task(self.action_save())

    async def _run_search(self, query: str) -> None:
        self._set_status("Поиск...", error=None)
        table = self.query_one("#results", DataTable)
        table.clear()
        self.query_one("#summary", Static).update("Саммари появится здесь")
        try:
            self.results = await self.brave.search(query, count=10, safesearch="moderate")
            self.last_query = query
            for idx, item in enumerate(self.results, start=1):
                table.add_row(str(idx), item.title, item.url, item.snippet)
            if not self.results:
                self._set_status("Ничего не найдено", error=None)
            else:
                self._set_status(f"Нашли {len(self.results)} результатов", error=None)
        except Exception as exc:  # noqa: BLE001
            self._set_status("", error=f"Ошибка поиска: {exc}")

    async def action_summarize(self) -> None:
        if not self.results:
            self._set_status("", error="Нет результатов для саммари")
            return
        self._set_status("Саммаризируем...", error=None)
        combined = "\n\n".join(
            f"{item.title}\n{item.url}\n{item.snippet}" for item in self.results[:8]
        )
        try:
            summary = await self.summarizer.summarize(combined, style="concise", max_chars=1200)
            self.last_summary = summary
            self.query_one("#summary", Static).update(summary or "Пустой ответ")
            self._set_status("Готово", error=None)
        except Exception as exc:  # noqa: BLE001
            self._set_status("", error=f"Ошибка саммари: {exc}")

    async def action_save(self) -> None:
        if not self.results:
            self._set_status("", error="Сначала выполните поиск")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_path = os.path.join(self.output_dir, f"{timestamp}_results.json")
        summary_path = os.path.join(self.output_dir, f"{timestamp}_summary.md")

        payload = {
            "query": self.last_query,
            "results": [item.__dict__ for item in self.results],
            "summary": self.last_summary,
        }

        try:
            await self.desktop.write_file(results_path, json.dumps(payload, ensure_ascii=False, indent=2))
            await self.desktop.write_file(summary_path, self._format_summary_markdown())
            self._set_status(f"Сохранено в {results_path} и {summary_path}", error=None)
        except Exception as exc:  # noqa: BLE001
            self._set_status("", error=f"Не удалось сохранить: {exc}")

    def _format_summary_markdown(self) -> str:
        lines = [
            f"# Результаты поиска: {self.last_query}",
            "",
            "## Топ-результаты",
        ]
        for idx, item in enumerate(self.results, start=1):
            lines.append(f"{idx}. [{item.title}]({item.url})" if item.url else f"{idx}. {item.title}")
            if item.snippet:
                lines.append(f"   {item.snippet}")
        lines.append("")
        lines.append("## Саммари")
        lines.append(self.last_summary or "_саммари не получено_")
        return "\n".join(lines)

    def _set_status(self, status: str, error: str | None) -> None:
        self.query_one("#status", Static).update(status)
        self.query_one("#error", Static).update(error or "")

    @staticmethod
    def _log_endpoints(name: str, urls: list[str]) -> None:
        # Печатаем явный список эндпоинтов для диагностики сетевых проблем
        print(f"[MCP] {name} endpoints: {', '.join(urls)}")

    async def on_unmount(self) -> None:
        await asyncio.gather(
            self.brave.close(),
            self.desktop.close(),
            self.summarizer.close(),
            return_exceptions=True,
        )


def main() -> None:
    app = WebSearchApp()
    app.run()


if __name__ == "__main__":
    main()
