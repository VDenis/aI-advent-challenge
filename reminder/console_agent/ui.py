import asyncio
import contextlib
from datetime import datetime, timedelta
from typing import List

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from .gigachat_summary import summarize_tasks


class AddTaskSubmitted(Message):
    def __init__(self, text: str, remind_at: str) -> None:
        self.text = text
        self.remind_at = remind_at
        super().__init__()


class AddTaskModal(ModalScreen[AddTaskSubmitted]):
    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self.text_input = Input(placeholder="Текст задачи", id="task_text")
        self.time_input = Input(placeholder="ISO-8601 дата/время", id="task_time")

    def compose(self) -> ComposeResult:
        yield Container(
            Static("Новая задача", classes="title"),
            self.text_input,
            self.time_input,
            Horizontal(
                Button("+30 мин", id="preset_30m", variant="primary"),
                Button("+1 час", id="preset_1h", variant="primary"),
                Button("Завтра 10:00", id="preset_tomorrow_10", variant="primary"),
            ),
            Horizontal(
                Button("Сохранить", id="save", variant="success"),
                Button("Отмена", id="cancel", variant="error"),
            ),
            classes="modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss()
            return

        if event.button.id == "save":
            text = self.text_input.value.strip()
            remind_at = self.time_input.value.strip()
            if text and remind_at:
                # Send message to parent app and then close modal
                self.post_message(AddTaskSubmitted(text, remind_at))
                self.dismiss()
            return

        # Preset buttons fill the remind_at field with ISO-8601 (with tz) values
        now = datetime.now().astimezone()
        if event.button.id == "preset_30m":
            target = now + timedelta(minutes=30)
            self.time_input.value = target.isoformat(timespec="minutes")
        elif event.button.id == "preset_1h":
            target = now + timedelta(hours=1)
            self.time_input.value = target.isoformat(timespec="minutes")
        elif event.button.id == "preset_tomorrow_10":
            target = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
            self.time_input.value = target.isoformat(timespec="minutes")


class ReminderApp(App):
    CSS = """
    Screen { align: center middle; }
    .summary { width: 100%; }
    .summary-meta { color: $text-muted; }
    .modal { width: 60%; padding: 1; border: round $surface; }
    #loader {
        layer: overlay;
        width: 100%;
        height: 100%;
        align: center middle;
        background: $panel;
        opacity: 0.85;
        color: $text;
        text-style: bold;
        text-align: center;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("a", "add_task", "Add task"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, client, use_llm: bool) -> None:
        super().__init__()
        self.client = client
        self.use_llm = use_llm
        self.tasks: List[dict] = []
        self._sse_task: asyncio.Task | None = None
        self._loader_shown = True

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Задачи", classes="title"),
            Static("", classes="summary", id="summary"),
            Static("", classes="summary-meta", id="summary_meta"),
            DataTable(id="table"),
        )
        yield Static("Загрузка…", id="loader")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("ID", "Текст", "Когда", "Статус")
        await self.refresh_tasks()
        self._sse_task = asyncio.create_task(self._listen_sse())

    async def _listen_sse(self) -> None:
        try:
            async for event in self.client.stream_events():
                if event.event in {"tasks_snapshot", "task_added", "task_deleted", "task_done"}:
                    await self.refresh_tasks()
        except Exception:
            # SSE is optional; ignore errors and allow manual refresh
            return

    async def refresh_tasks(self) -> None:
        self.tasks = await self.client.task_list()
        summary_widget = self.query_one("#summary", Static)
        summary_meta_widget = self.query_one("#summary_meta", Static)
        summary_widget.update("Обновляем сводку…")
        summary_meta_widget.update("Источник: ...")

        try:
            summary, source = await summarize_tasks(self.tasks, allow_llm=self.use_llm, return_meta=True)
            summary_widget = self.query_one("#summary", Static)
            summary_widget.update(summary or "Нет задач")

            source_text = {
                "gigachat": "Источник: GigaChat",
                "fallback": "Источник: fallback",
                "disabled": "Источник: LLM отключен",
            }.get(source, f"Источник: {source}")
            summary_meta_widget.update(source_text)
        except Exception as exc:
            summary_widget = self.query_one("#summary", Static)
            summary_widget.update(f"Ошибка сводки: {exc}")
            summary_meta_widget.update("Источник: ошибка")

        table = self.query_one(DataTable)
        table.clear()
        for task in sorted(self.tasks, key=lambda t: t["remind_at"]):
            table.add_row(task["id"], task["text"], task["remind_at"], task["status"])
        self._hide_loader()

    async def action_add_task(self) -> None:
        await self.push_screen(AddTaskModal())

    async def action_refresh(self) -> None:
        await self.refresh_tasks()

    @on(AddTaskSubmitted)
    async def handle_new_task(self, event: AddTaskSubmitted) -> None:
        await self.client.task_add(event.text, event.remind_at)
        await self.refresh_tasks()

    async def on_unmount(self) -> None:
        if self._sse_task:
            self._sse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sse_task
        with contextlib.suppress(Exception):
            await self.client.aclose()

    def _hide_loader(self) -> None:
        if not self._loader_shown:
            return
        loader = self.query_one("#loader", Static)
        loader.display = False
        self._loader_shown = False
