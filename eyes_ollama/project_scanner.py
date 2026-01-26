#!/usr/bin/env python3
"""
eyes_ollama/project_scanner.py — Сканер проекта для аналитики с Ollama.

Собирает метрики исходного кода, git-истории и зависимостей,
позволяет задавать аналитические вопросы через локальную Ollama.

Python 3.10+, только стандартная библиотека.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gemma2:2b"

# Паттерны для игнорирования
IGNORE_DIRS = {
    ".git", ".venv", "venv", "venvmcp", ".venvmcp", "__pycache__",
    "node_modules", ".cache", ".pytest_cache", ".mypy_cache",
    "dist", "build", "*.egg-info", ".tox", ".eggs"
}

IGNORE_FILES = {
    ".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.so", "*.dylib"
}

CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb"}


# ═══════════════════════════════════════════════════════════════════════════════
# СКАНЕР ИСХОДНОГО КОДА
# ═══════════════════════════════════════════════════════════════════════════════

def should_ignore(path: Path, root: Path) -> bool:
    """Проверяет, нужно ли игнорировать путь."""
    rel_parts = path.relative_to(root).parts
    for part in rel_parts:
        if part in IGNORE_DIRS or part.startswith("."):
            return True
        for pattern in IGNORE_DIRS:
            if "*" in pattern and part.endswith(pattern.replace("*", "")):
                return True
    return False


def analyze_python_file(file_path: Path) -> dict:
    """Анализирует Python файл: функции, классы, импорты, TODO."""
    result = {
        "functions": [],
        "classes": [],
        "imports": [],
        "todos": [],
        "lines_total": 0,
        "lines_code": 0,
        "lines_comment": 0,
        "lines_blank": 0,
        "complexity_indicators": [],
    }

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        result["lines_total"] = len(lines)

        # Подсчёт строк
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                result["lines_blank"] += 1
            elif stripped.startswith("#"):
                result["lines_comment"] += 1
                # TODO/FIXME
                if re.search(r"\b(TODO|FIXME|XXX|HACK|BUG)\b", stripped, re.IGNORECASE):
                    result["todos"].append({
                        "line": i,
                        "text": stripped[1:].strip()[:100]
                    })
            else:
                result["lines_code"] += 1
                # TODO в inline комментариях
                if "#" in line:
                    comment_part = line.split("#", 1)[1]
                    if re.search(r"\b(TODO|FIXME|XXX|HACK|BUG)\b", comment_part, re.IGNORECASE):
                        result["todos"].append({
                            "line": i,
                            "text": comment_part.strip()[:100]
                        })

        # AST анализ
        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    func_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "args": len(node.args.args),
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "decorators": [_get_decorator_name(d) for d in node.decorator_list],
                    }
                    # Простая метрика сложности: количество if/for/while/try
                    complexity = sum(1 for n in ast.walk(node)
                                   if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler)))
                    func_info["complexity"] = complexity
                    if complexity > 5:
                        result["complexity_indicators"].append(f"{node.name}:{complexity}")
                    result["functions"].append(func_info)

                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body
                              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    result["classes"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                        "method_count": len(methods),
                        "bases": [_get_name(b) for b in node.bases],
                    })

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name.split(".")[0])

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        result["imports"].append(node.module.split(".")[0])

        except SyntaxError:
            pass  # Файл с синтаксической ошибкой

    except Exception as e:
        result["error"] = str(e)

    return result


def _get_decorator_name(node) -> str:
    """Извлекает имя декоратора."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    elif isinstance(node, ast.Call):
        return _get_decorator_name(node.func)
    return "?"


def _get_name(node) -> str:
    """Извлекает имя из AST узла."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    return "?"


def scan_codebase(root: Path, extensions: set[str] | None = None) -> dict:
    """Сканирует кодовую базу проекта."""
    if extensions is None:
        extensions = {".py"}

    files = []
    total_stats = {
        "total_files": 0,
        "total_lines": 0,
        "total_code_lines": 0,
        "total_comment_lines": 0,
        "total_blank_lines": 0,
        "total_functions": 0,
        "total_classes": 0,
        "all_imports": Counter(),
        "all_todos": [],
        "files_by_dir": defaultdict(list),
        "largest_files": [],
        "most_complex": [],
    }

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if should_ignore(file_path, root):
            continue
        if file_path.suffix not in extensions:
            continue

        rel_path = str(file_path.relative_to(root))
        analysis = analyze_python_file(file_path)

        file_info = {
            "path": rel_path,
            "dir": str(file_path.parent.relative_to(root)),
            "name": file_path.name,
            **analysis
        }
        files.append(file_info)

        # Агрегация
        total_stats["total_files"] += 1
        total_stats["total_lines"] += analysis["lines_total"]
        total_stats["total_code_lines"] += analysis["lines_code"]
        total_stats["total_comment_lines"] += analysis["lines_comment"]
        total_stats["total_blank_lines"] += analysis["lines_blank"]
        total_stats["total_functions"] += len(analysis["functions"])
        total_stats["total_classes"] += len(analysis["classes"])
        total_stats["all_imports"].update(analysis["imports"])
        total_stats["files_by_dir"][file_info["dir"]].append(rel_path)

        for todo in analysis["todos"]:
            total_stats["all_todos"].append({
                "file": rel_path,
                **todo
            })

        # Для топов
        total_stats["largest_files"].append((rel_path, analysis["lines_code"]))
        for func in analysis["functions"]:
            if func.get("complexity", 0) > 3:
                total_stats["most_complex"].append({
                    "file": rel_path,
                    "function": func["name"],
                    "complexity": func["complexity"],
                    "line": func["line"],
                })

    # Сортировка топов
    total_stats["largest_files"] = sorted(
        total_stats["largest_files"], key=lambda x: x[1], reverse=True
    )[:20]
    total_stats["most_complex"] = sorted(
        total_stats["most_complex"], key=lambda x: x["complexity"], reverse=True
    )[:20]
    total_stats["all_imports"] = dict(total_stats["all_imports"].most_common(30))
    total_stats["files_by_dir"] = {k: len(v) for k, v in total_stats["files_by_dir"].items()}

    return {
        "files": files,
        "summary": total_stats,
        "scanned_at": datetime.now().isoformat(),
        "root": str(root),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# СКАНЕР GIT ИСТОРИИ
# ═══════════════════════════════════════════════════════════════════════════════

def scan_git_history(root: Path, limit: int = 500) -> dict:
    """Сканирует git историю проекта."""
    result = {
        "commits": [],
        "summary": {},
        "available": False,
    }

    # Проверяем, что это git репозиторий
    git_dir = root / ".git"
    if not git_dir.exists():
        result["error"] = "Не git репозиторий"
        return result

    result["available"] = True

    try:
        # Получаем коммиты
        cmd = [
            "git", "-C", str(root), "log",
            f"--max-count={limit}",
            "--pretty=format:%H|%h|%an|%ae|%ai|%s",
            "--no-merges"
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)

        commits = []
        authors = Counter()
        dates = []
        messages = []

        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 5)
            if len(parts) < 6:
                continue

            full_hash, short_hash, author, email, date_str, message = parts

            commit = {
                "hash": short_hash,
                "author": author,
                "email": email,
                "date": date_str,
                "message": message[:200],
            }
            commits.append(commit)
            authors[author] += 1
            dates.append(date_str[:10])  # только дата
            messages.append(message.lower())

        result["commits"] = commits

        # Анализ сообщений коммитов
        commit_types = Counter()
        for msg in messages:
            if msg.startswith("fix") or "fix" in msg[:20]:
                commit_types["fix"] += 1
            elif msg.startswith("feat") or "add" in msg[:20] or "new" in msg[:20]:
                commit_types["feature"] += 1
            elif msg.startswith("refactor") or "refactor" in msg:
                commit_types["refactor"] += 1
            elif msg.startswith("docs") or "readme" in msg or "doc" in msg[:20]:
                commit_types["docs"] += 1
            elif msg.startswith("test") or "test" in msg[:20]:
                commit_types["test"] += 1
            elif "merge" in msg[:20]:
                commit_types["merge"] += 1
            else:
                commit_types["other"] += 1

        # Файлы, которые чаще всего меняются
        cmd_files = [
            "git", "-C", str(root), "log",
            f"--max-count={limit}",
            "--pretty=format:", "--name-only"
        ]
        files_output = subprocess.check_output(cmd_files, stderr=subprocess.DEVNULL, text=True)
        file_changes = Counter(f for f in files_output.split("\n") if f.strip() and not f.startswith("."))

        # Активность по дням
        activity_by_date = Counter(dates)

        result["summary"] = {
            "total_commits": len(commits),
            "authors": dict(authors.most_common(20)),
            "top_contributors": list(authors.most_common(5)),
            "commit_types": dict(commit_types),
            "most_changed_files": dict(file_changes.most_common(20)),
            "activity_by_date": dict(sorted(activity_by_date.items())[-30:]),  # последние 30 дней
            "date_range": {
                "first": dates[-1] if dates else None,
                "last": dates[0] if dates else None,
            }
        }

        # Текущая ветка
        try:
            branch = subprocess.check_output(
                ["git", "-C", str(root), "branch", "--show-current"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            result["summary"]["current_branch"] = branch
        except:
            pass

    except subprocess.CalledProcessError as e:
        result["error"] = f"Git ошибка: {e}"
    except Exception as e:
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# СКАНЕР ЗАВИСИМОСТЕЙ
# ═══════════════════════════════════════════════════════════════════════════════

def scan_dependencies(root: Path) -> dict:
    """Сканирует зависимости проекта."""
    result = {
        "requirements": {},
        "pyproject": {},
        "setup_py": {},
        "all_deps": [],
    }

    # requirements*.txt
    for req_file in root.glob("**/requirements*.txt"):
        if should_ignore(req_file, root):
            continue
        rel_path = str(req_file.relative_to(root))
        deps = parse_requirements(req_file)
        result["requirements"][rel_path] = deps
        result["all_deps"].extend(deps)

    # pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        deps = parse_pyproject(pyproject)
        result["pyproject"] = deps
        result["all_deps"].extend(deps.get("dependencies", []))
        result["all_deps"].extend(deps.get("dev_dependencies", []))

    # setup.py (простой парсинг)
    setup_py = root / "setup.py"
    if setup_py.exists():
        deps = parse_setup_py(setup_py)
        result["setup_py"] = deps
        result["all_deps"].extend(deps.get("install_requires", []))

    # Уникальные зависимости (только имена пакетов)
    unique_deps = set()
    for dep in result["all_deps"]:
        # Извлекаем имя пакета (без версии)
        match = re.match(r"^([a-zA-Z0-9_-]+)", dep)
        if match:
            unique_deps.add(match.group(1).lower())

    result["unique_packages"] = sorted(unique_deps)
    result["total_unique"] = len(unique_deps)

    return result


def parse_requirements(file_path: Path) -> list[str]:
    """Парсит requirements.txt."""
    deps = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            deps.append(line)
    except:
        pass
    return deps


def parse_pyproject(file_path: Path) -> dict:
    """Простой парсинг pyproject.toml (без toml библиотеки)."""
    result = {"dependencies": [], "dev_dependencies": [], "project_name": None}
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Имя проекта
        match = re.search(r'name\s*=\s*"([^"]+)"', content)
        if match:
            result["project_name"] = match.group(1)

        # Dependencies (простой парсинг)
        in_deps = False
        in_dev_deps = False
        for line in content.splitlines():
            if line.strip().startswith("dependencies"):
                in_deps = True
                in_dev_deps = False
                continue
            if "dev-dependencies" in line or "dev_dependencies" in line:
                in_deps = False
                in_dev_deps = True
                continue
            if line.strip().startswith("[") and in_deps:
                in_deps = False
            if line.strip().startswith("[") and in_dev_deps:
                in_dev_deps = False

            # Извлекаем зависимость из строки типа "  package>=1.0"
            match = re.match(r'^\s*"?([a-zA-Z0-9_-]+[^"]*)"?,?\s*$', line)
            if match:
                dep = match.group(1).strip()
                if in_deps:
                    result["dependencies"].append(dep)
                elif in_dev_deps:
                    result["dev_dependencies"].append(dep)
    except:
        pass
    return result


def parse_setup_py(file_path: Path) -> dict:
    """Простой парсинг setup.py."""
    result = {"install_requires": []}
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Ищем install_requires = [...]
        match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if match:
            deps_str = match.group(1)
            for dep_match in re.finditer(r'"([^"]+)"', deps_str):
                result["install_requires"].append(dep_match.group(1))
    except:
        pass
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ПОЛНОЕ СКАНИРОВАНИЕ ПРОЕКТА
# ═══════════════════════════════════════════════════════════════════════════════

def scan_project(root: Path, git_limit: int = 500) -> dict:
    """Полное сканирование проекта."""
    print(f"Сканирование: {root}")

    print("  → Исходный код...")
    code = scan_codebase(root)

    print("  → Git история...")
    git = scan_git_history(root, limit=git_limit)

    print("  → Зависимости...")
    deps = scan_dependencies(root)

    return {
        "project_root": str(root),
        "project_name": root.name,
        "scanned_at": datetime.now().isoformat(),
        "code": code,
        "git": git,
        "dependencies": deps,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OLLAMA ИНТЕГРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def call_ollama(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 120) -> str:
    """Вызов Ollama API."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 2048,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response", "")
    except urllib.error.URLError as e:
        return f"[ОШИБКА] Не удалось подключиться к Ollama: {e}. Убедитесь, что ollama serve запущен."
    except Exception as e:
        return f"[ОШИБКА] {e}"


def build_project_prompt(question: str, project_data: dict) -> str:
    """Строит промпт для вопроса о проекте."""

    code_summary = project_data.get("code", {}).get("summary", {})
    git_summary = project_data.get("git", {}).get("summary", {})
    deps = project_data.get("dependencies", {})

    context = f"""АНАЛИЗ ПРОЕКТА: {project_data.get('project_name', '?')}

## ИСХОДНЫЙ КОД
- Всего файлов: {code_summary.get('total_files', 0)}
- Строк кода: {code_summary.get('total_code_lines', 0)}
- Строк комментариев: {code_summary.get('total_comment_lines', 0)}
- Функций: {code_summary.get('total_functions', 0)}
- Классов: {code_summary.get('total_classes', 0)}

Файлы по папкам:
{json.dumps(code_summary.get('files_by_dir', {}), indent=2, ensure_ascii=False)}

Самые большие файлы (строк кода):
{json.dumps(code_summary.get('largest_files', [])[:10], indent=2)}

Самые сложные функции:
{json.dumps(code_summary.get('most_complex', [])[:10], indent=2, ensure_ascii=False)}

Импорты (топ-20):
{json.dumps(code_summary.get('all_imports', {}), indent=2)}

TODO/FIXME ({len(code_summary.get('all_todos', []))} шт):
{json.dumps(code_summary.get('all_todos', [])[:15], indent=2, ensure_ascii=False)}

## GIT ИСТОРИЯ
- Всего коммитов: {git_summary.get('total_commits', 0)}
- Текущая ветка: {git_summary.get('current_branch', '?')}
- Период: {git_summary.get('date_range', {}).get('first', '?')} — {git_summary.get('date_range', {}).get('last', '?')}

Авторы:
{json.dumps(git_summary.get('authors', {}), indent=2, ensure_ascii=False)}

Типы коммитов:
{json.dumps(git_summary.get('commit_types', {}), indent=2)}

Часто меняющиеся файлы:
{json.dumps(dict(list(git_summary.get('most_changed_files', {}).items())[:15]), indent=2)}

## ЗАВИСИМОСТИ
Всего уникальных пакетов: {deps.get('total_unique', 0)}
Пакеты: {', '.join(deps.get('unique_packages', [])[:30])}
"""

    prompt = f"""{context}

ВОПРОС: {question}

Дай конкретный ответ на основе данных выше. Используй числа и факты из анализа. Будь кратким."""

    return prompt


def ask_about_project(question: str, project_data: dict, model: str = DEFAULT_MODEL) -> str:
    """Отвечает на вопрос о проекте через Ollama."""
    prompt = build_project_prompt(question, project_data)
    return call_ollama(prompt, model)


# ═══════════════════════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ ВЫВОДА
# ═══════════════════════════════════════════════════════════════════════════════

def print_summary(project_data: dict):
    """Печатает краткую сводку проекта."""
    code = project_data.get("code", {}).get("summary", {})
    git = project_data.get("git", {}).get("summary", {})
    deps = project_data.get("dependencies", {})

    print(f"\n{'═' * 60}")
    print(f"ПРОЕКТ: {project_data.get('project_name', '?')}")
    print(f"{'═' * 60}")

    print(f"\n📁 ИСХОДНЫЙ КОД")
    print(f"   Файлов: {code.get('total_files', 0)}")
    print(f"   Строк кода: {code.get('total_code_lines', 0)}")
    print(f"   Функций: {code.get('total_functions', 0)}")
    print(f"   Классов: {code.get('total_classes', 0)}")
    print(f"   TODO/FIXME: {len(code.get('all_todos', []))}")

    if code.get("largest_files"):
        print(f"\n   Самые большие файлы:")
        for path, lines in code["largest_files"][:5]:
            print(f"     {lines:>5} строк  {path}")

    if git.get("total_commits"):
        print(f"\n📊 GIT")
        print(f"   Коммитов: {git.get('total_commits', 0)}")
        print(f"   Авторов: {len(git.get('authors', {}))}")
        print(f"   Ветка: {git.get('current_branch', '?')}")

        if git.get("top_contributors"):
            print(f"\n   Топ контрибьюторов:")
            for author, count in git["top_contributors"][:3]:
                print(f"     {count:>4} коммитов  {author}")

    print(f"\n📦 ЗАВИСИМОСТИ")
    print(f"   Уникальных пакетов: {deps.get('total_unique', 0)}")
    if deps.get("unique_packages"):
        print(f"   Примеры: {', '.join(deps['unique_packages'][:10])}")

    print(f"\n{'═' * 60}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_scan(args):
    """Сканирует проект и сохраняет результат."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Путь не найден: {root}", file=sys.stderr)
        return 1

    data = scan_project(root, git_limit=args.git_limit)

    output_path = Path(args.output) if args.output else root / "project_analysis.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nРезультат сохранён: {output_path}")

    if not args.json:
        print_summary(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    return 0


def cmd_ask(args):
    """Задаёт вопрос по проекту."""
    # Загружаем или сканируем данные
    analysis_file = Path(args.file) if args.file else Path(args.path) / "project_analysis.json"

    if analysis_file.exists() and analysis_file.suffix == ".json":
        print(f"Загрузка анализа: {analysis_file}")
        with open(analysis_file, "r", encoding="utf-8") as f:
            project_data = json.load(f)
    else:
        print("Анализ не найден, сканирую проект...")
        root = Path(args.path).resolve()
        project_data = scan_project(root)

    question = " ".join(args.question)
    if not question:
        print("Укажите вопрос", file=sys.stderr)
        return 1

    print(f"\nСпрашиваю {args.model}...\n")

    answer = ask_about_project(question, project_data, model=args.model)

    print("─" * 60)
    print(answer)
    print("─" * 60)

    return 0


def cmd_chat(args):
    """Интерактивный чат о проекте."""
    analysis_file = Path(args.file) if args.file else Path(args.path) / "project_analysis.json"

    if analysis_file.exists() and analysis_file.suffix == ".json":
        print(f"Загрузка анализа: {analysis_file}")
        with open(analysis_file, "r", encoding="utf-8") as f:
            project_data = json.load(f)
    else:
        print("Анализ не найден, сканирую проект...")
        root = Path(args.path).resolve()
        project_data = scan_project(root)
        # Сохраняем для последующих запросов
        output_path = root / "project_analysis.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
        print(f"Анализ сохранён: {output_path}")

    print_summary(project_data)

    print(f"Модель: {args.model}")
    print("Введите вопрос (или 'exit' для выхода):\n")

    while True:
        try:
            question = input("❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q", "выход"):
            break

        answer = ask_about_project(question, project_data, model=args.model)
        print(f"\n{answer}\n")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="project_scanner",
        description="Сканер проекта для аналитики с Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s scan .                           # Сканировать текущий проект
  %(prog)s scan /path/to/project -o analysis.json
  %(prog)s ask . "какой модуль самый большой?"
  %(prog)s ask -f analysis.json "кто больше всех коммитит?"
  %(prog)s chat .                           # Интерактивный режим
        """
    )

    parser.add_argument("--json", action="store_true", help="JSON вывод")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan", help="Сканировать проект")
    p_scan.add_argument("path", nargs="?", default=".", help="Путь к проекту")
    p_scan.add_argument("-o", "--output", help="Выходной JSON файл")
    p_scan.add_argument("--git-limit", type=int, default=500, help="Лимит коммитов git")
    p_scan.set_defaults(func=cmd_scan)

    # ask
    p_ask = subparsers.add_parser("ask", help="Задать вопрос о проекте")
    p_ask.add_argument("path", nargs="?", default=".", help="Путь к проекту")
    p_ask.add_argument("question", nargs="*", help="Вопрос")
    p_ask.add_argument("-f", "--file", help="JSON файл с анализом")
    p_ask.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Модель Ollama (default: {DEFAULT_MODEL})")
    p_ask.set_defaults(func=cmd_ask)

    # chat
    p_chat = subparsers.add_parser("chat", help="Интерактивный чат о проекте")
    p_chat.add_argument("path", nargs="?", default=".", help="Путь к проекту")
    p_chat.add_argument("-f", "--file", help="JSON файл с анализом")
    p_chat.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Модель Ollama (default: {DEFAULT_MODEL})")
    p_chat.set_defaults(func=cmd_chat)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
