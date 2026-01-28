"""Инструменты для анализа проектов: сканирование, поиск, метрики, ревью."""

import ast
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

IGNORE_DIRS = {
    ".git", ".venv", "venv", "venvmcp", ".venvmcp", "__pycache__",
    "node_modules", ".cache", ".pytest_cache", ".mypy_cache",
    "dist", "build", ".tox", ".eggs", ".history", ".config",
}

CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb"}

SEARCH_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb",
    ".yaml", ".yml", ".json", ".md", ".txt", ".toml", ".cfg", ".ini",
    ".html", ".css", ".sh", ".bash",
}

REVIEW_PROMPT = """Ты опытный код-ревьюер. Проведи ревью следующего файла.

Файл: {path}
Язык: {lang}

```{lang}
{code}
```

Проверь:
1. Баги и логические ошибки
2. Проблемы безопасности (инъекции, утечки данных, хардкод секретов)
3. Стиль кода и читаемость
4. Возможности оптимизации
5. Обработка ошибок

Формат ответа:
- Для каждой проблемы укажи строку и серьёзность (критическая/важная/замечание)
- В конце дай общую оценку качества кода (1-10)
- Будь конкретным и давай примеры исправлений"""


# ═══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════════════════════

def _should_ignore(path: Path, root: Path) -> bool:
    """Проверяет, нужно ли игнорировать путь."""
    for part in path.relative_to(root).parts:
        if part in IGNORE_DIRS or part.startswith("."):
            return True
        if part.endswith(".egg-info"):
            return True
    return False


def _get_decorator_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    elif isinstance(node, ast.Call):
        return _get_decorator_name(node.func)
    return "?"


def _get_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    return "?"


def _lang_from_ext(ext: str) -> str:
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".rb": "ruby",
    }.get(ext, "text")


# ═══════════════════════════════════════════════════════════════════════════════
# АНАЛИЗ ФАЙЛОВ
# ═══════════════════════════════════════════════════════════════════════════════

def _analyze_python_file(file_path: Path) -> dict:
    """Анализирует Python файл через AST."""
    result = {
        "functions": [], "classes": [], "imports": [], "todos": [],
        "lines_total": 0, "lines_code": 0, "lines_comment": 0, "lines_blank": 0,
    }
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        result["lines_total"] = len(lines)

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                result["lines_blank"] += 1
            elif stripped.startswith("#"):
                result["lines_comment"] += 1
                if re.search(r"\b(TODO|FIXME|XXX|HACK|BUG)\b", stripped, re.IGNORECASE):
                    result["todos"].append({"line": i, "text": stripped[1:].strip()[:100]})
            else:
                result["lines_code"] += 1

        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = sum(
                        1 for n in ast.walk(node)
                        if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler))
                    )
                    result["functions"].append({
                        "name": node.name, "line": node.lineno,
                        "args": len(node.args.args), "complexity": complexity,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "decorators": [_get_decorator_name(d) for d in node.decorator_list],
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    result["classes"].append({
                        "name": node.name, "line": node.lineno,
                        "methods": methods, "method_count": len(methods),
                        "bases": [_get_name(b) for b in node.bases],
                    })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        result["imports"].append(node.module.split(".")[0])
        except SyntaxError:
            pass
    except Exception as e:
        result["error"] = str(e)
    return result


def _count_lines(file_path: Path) -> dict:
    """Простой подсчёт строк для не-Python файлов."""
    result = {"lines_total": 0, "lines_code": 0, "lines_comment": 0, "lines_blank": 0}
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        result["lines_total"] = len(lines)
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result["lines_blank"] += 1
            elif stripped.startswith(("//", "#", "/*", "*")):
                result["lines_comment"] += 1
            else:
                result["lines_code"] += 1
    except Exception:
        pass
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# СКАНЕР GIT
# ═══════════════════════════════════════════════════════════════════════════════

def _scan_git(root: Path, limit: int = 500) -> dict:
    """Сканирует git историю."""
    result = {"available": False, "summary": {}}
    if not (root / ".git").exists():
        return result

    result["available"] = True
    try:
        output = subprocess.check_output(
            ["git", "-C", str(root), "log", f"--max-count={limit}",
             "--pretty=format:%h|%an|%ai|%s", "--no-merges"],
            stderr=subprocess.DEVNULL, text=True,
        )
        authors = Counter()
        commit_types = Counter()
        dates = []
        total = 0

        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            _, author, date_str, msg = parts
            total += 1
            authors[author] += 1
            dates.append(date_str[:10])
            msg_lower = msg.lower()
            if "fix" in msg_lower[:20]:
                commit_types["fix"] += 1
            elif any(w in msg_lower[:20] for w in ("feat", "add", "new")):
                commit_types["feature"] += 1
            elif "refactor" in msg_lower:
                commit_types["refactor"] += 1
            elif any(w in msg_lower[:20] for w in ("doc", "readme")):
                commit_types["docs"] += 1
            elif "test" in msg_lower[:20]:
                commit_types["test"] += 1
            else:
                commit_types["other"] += 1

        branch = subprocess.check_output(
            ["git", "-C", str(root), "branch", "--show-current"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()

        result["summary"] = {
            "total_commits": total,
            "authors": dict(authors.most_common(10)),
            "commit_types": dict(commit_types),
            "current_branch": branch,
            "date_range": {"first": dates[-1] if dates else None, "last": dates[0] if dates else None},
        }
    except Exception as e:
        result["error"] = str(e)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# СКАНЕР ЗАВИСИМОСТЕЙ
# ═══════════════════════════════════════════════════════════════════════════════

def _scan_deps(root: Path) -> dict:
    """Сканирует зависимости."""
    all_deps = []
    sources = {}

    for req_file in root.glob("**/requirements*.txt"):
        if _should_ignore(req_file, root):
            continue
        rel = str(req_file.relative_to(root))
        deps = []
        try:
            for line in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    deps.append(line)
        except Exception:
            pass
        sources[rel] = deps
        all_deps.extend(deps)

    unique = set()
    for dep in all_deps:
        m = re.match(r"^([a-zA-Z0-9_-]+)", dep)
        if m:
            unique.add(m.group(1).lower())

    return {"sources": sources, "packages": sorted(unique), "total": len(unique)}


# ═══════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ КЛАСС
# ═══════════════════════════════════════════════════════════════════════════════

class ProjectTools:
    """Инструменты для работы с проектами из чата."""

    def __init__(self, chat_client):
        self.chat_client = chat_client
        self.last_scan: Optional[dict] = None
        self.last_scan_path: Optional[str] = None

    # ─── /scan ────────────────────────────────────────────────────────────

    def scan(self, path_str: str) -> None:
        """Сканирует проект по указанному пути."""
        root = Path(path_str).resolve()
        if not root.exists():
            console.print(f"[red]Путь не найден:[/red] {root}")
            return
        if not root.is_dir():
            console.print(f"[red]Не директория:[/red] {root}")
            return

        console.print(f"[cyan]Сканирование:[/cyan] {root}")

        with console.status("[cyan]Анализ исходного кода...[/cyan]"):
            code_data = self._scan_code(root)

        with console.status("[cyan]Анализ git...[/cyan]"):
            git_data = _scan_git(root)

        with console.status("[cyan]Анализ зависимостей...[/cyan]"):
            deps_data = _scan_deps(root)

        self.last_scan = {
            "project_name": root.name,
            "project_root": str(root),
            "scanned_at": datetime.now().isoformat(),
            "code": code_data,
            "git": git_data,
            "dependencies": deps_data,
        }
        self.last_scan_path = str(root)

        console.print(f"[green]Сканирование завершено![/green]")
        self._print_summary()

    def _scan_code(self, root: Path) -> dict:
        """Сканирует исходный код."""
        files = []
        stats = {
            "total_files": 0, "total_lines": 0, "total_code_lines": 0,
            "total_comment_lines": 0, "total_blank_lines": 0,
            "total_functions": 0, "total_classes": 0,
            "all_imports": Counter(), "all_todos": [],
            "files_by_dir": defaultdict(int),
            "largest_files": [], "most_complex": [],
        }

        for fp in root.rglob("*"):
            if not fp.is_file() or _should_ignore(fp, root) or fp.suffix not in CODE_EXTENSIONS:
                continue

            rel = str(fp.relative_to(root))
            if fp.suffix == ".py":
                analysis = _analyze_python_file(fp)
            else:
                analysis = _count_lines(fp)
                analysis.setdefault("functions", [])
                analysis.setdefault("classes", [])
                analysis.setdefault("imports", [])
                analysis.setdefault("todos", [])

            files.append({"path": rel, **analysis})
            stats["total_files"] += 1
            stats["total_lines"] += analysis["lines_total"]
            stats["total_code_lines"] += analysis["lines_code"]
            stats["total_comment_lines"] += analysis["lines_comment"]
            stats["total_blank_lines"] += analysis["lines_blank"]
            stats["total_functions"] += len(analysis.get("functions", []))
            stats["total_classes"] += len(analysis.get("classes", []))
            stats["all_imports"].update(analysis.get("imports", []))
            stats["files_by_dir"][str(fp.parent.relative_to(root))] += 1

            for todo in analysis.get("todos", []):
                stats["all_todos"].append({"file": rel, **todo})

            stats["largest_files"].append((rel, analysis["lines_code"]))
            for func in analysis.get("functions", []):
                if func.get("complexity", 0) > 3:
                    stats["most_complex"].append({
                        "file": rel, "function": func["name"],
                        "complexity": func["complexity"], "line": func["line"],
                    })

        stats["largest_files"] = sorted(stats["largest_files"], key=lambda x: x[1], reverse=True)[:15]
        stats["most_complex"] = sorted(stats["most_complex"], key=lambda x: x["complexity"], reverse=True)[:15]
        stats["all_imports"] = dict(stats["all_imports"].most_common(20))
        stats["files_by_dir"] = dict(stats["files_by_dir"])

        return {"files": files, "summary": stats}

    # ─── /metrics ─────────────────────────────────────────────────────────

    def metrics(self) -> None:
        """Показывает метрики последнего сканирования."""
        if not self.last_scan:
            console.print("[yellow]Сначала выполните /scan <путь>[/yellow]")
            return
        self._print_summary()

    def _print_summary(self) -> None:
        """Выводит сводку метрик в Rich-таблицах."""
        data = self.last_scan
        code = data["code"]["summary"]
        git = data["git"]
        deps = data["dependencies"]

        # Общая статистика
        t = Table(title=f"Проект: {data['project_name']}", show_header=False, border_style="cyan")
        t.add_column("Метрика", style="cyan")
        t.add_column("Значение", justify="right")
        t.add_row("Файлов кода", str(code["total_files"]))
        t.add_row("Строк кода", str(code["total_code_lines"]))
        t.add_row("Строк комментариев", str(code["total_comment_lines"]))
        t.add_row("Функций", str(code["total_functions"]))
        t.add_row("Классов", str(code["total_classes"]))
        t.add_row("TODO/FIXME", str(len(code["all_todos"])))
        t.add_row("Пакетов (зависимости)", str(deps["total"]))
        if git.get("available"):
            gs = git["summary"]
            t.add_row("Git коммитов", str(gs.get("total_commits", 0)))
            t.add_row("Git авторов", str(len(gs.get("authors", {}))))
            t.add_row("Ветка", gs.get("current_branch", "?"))
        console.print(t)

        # Топ файлов
        if code["largest_files"]:
            ft = Table(title="Крупнейшие файлы", show_header=True, header_style="bold")
            ft.add_column("Файл")
            ft.add_column("Строк кода", justify="right")
            for path, lines in code["largest_files"][:10]:
                ft.add_row(path, str(lines))
            console.print(ft)

        # Сложные функции
        if code["most_complex"]:
            ct = Table(title="Самые сложные функции", show_header=True, header_style="bold")
            ct.add_column("Функция")
            ct.add_column("Файл")
            ct.add_column("Сложность", justify="right")
            for item in code["most_complex"][:10]:
                ct.add_row(item["function"], item["file"], str(item["complexity"]))
            console.print(ct)

        # Git авторы
        if git.get("available") and git["summary"].get("authors"):
            at = Table(title="Контрибьюторы", show_header=True, header_style="bold")
            at.add_column("Автор")
            at.add_column("Коммитов", justify="right")
            for author, count in git["summary"]["authors"].items():
                at.add_row(author, str(count))
            console.print(at)

    # ─── /search ──────────────────────────────────────────────────────────

    def search(self, query: str, path_str: str = None) -> None:
        """Поиск по содержимому файлов проекта."""
        root_str = path_str or self.last_scan_path or "."

        root = Path(root_str).resolve()
        if not root.exists():
            console.print(f"[red]Путь не найден:[/red] {root}")
            return

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        results = []
        with console.status(f"[cyan]Поиск '{query}'...[/cyan]"):
            for fp in root.rglob("*"):
                if not fp.is_file() or _should_ignore(fp, root) or fp.suffix not in SEARCH_EXTENSIONS:
                    continue
                try:
                    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                    for i, line in enumerate(lines, 1):
                        if pattern.search(line):
                            results.append((str(fp.relative_to(root)), i, line.strip()[:120]))
                            if len(results) >= 50:
                                break
                except Exception:
                    continue
                if len(results) >= 50:
                    break

        if not results:
            console.print(f"[yellow]Ничего не найдено по запросу '{query}'[/yellow]")
            return

        t = Table(title=f"Результаты поиска: '{query}' ({len(results)})", show_header=True, header_style="bold")
        t.add_column("Файл", style="cyan", max_width=40)
        t.add_column("Стр", justify="right", style="dim")
        t.add_column("Содержимое", max_width=80)

        for path, line_no, content in results:
            t.add_row(path, str(line_no), content)

        console.print(t)

    # ─── /review ──────────────────────────────────────────────────────────

    def review(self, file_path_str: str) -> None:
        """Ревью файла через GigaChat."""
        fp = Path(file_path_str).resolve()
        if not fp.exists():
            console.print(f"[red]Файл не найден:[/red] {fp}")
            return
        if not fp.is_file():
            console.print(f"[red]Не файл:[/red] {fp}")
            return

        try:
            code = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            console.print(f"[red]Ошибка чтения:[/red] {e}")
            return

        if len(code) > 15000:
            console.print("[yellow]Файл слишком большой, обрезаю до 15000 символов[/yellow]")
            code = code[:15000]

        lang = _lang_from_ext(fp.suffix)
        prompt = REVIEW_PROMPT.format(path=fp.name, lang=lang, code=code)

        console.print(f"[cyan]Ревью файла:[/cyan] {fp.name} ({lang})\n")

        try:
            console.print("[bold green]Ревью:[/bold green] ", end="")
            full_response = ""
            for chunk in self.chat_client.send_message_stream(prompt, []):
                console.print(chunk, end="")
                full_response += chunk
            console.print("\n")
        except Exception as e:
            console.print(f"\n[red]Ошибка:[/red] {e}")
