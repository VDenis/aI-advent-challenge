# AI Code Review System

LLM-powered reviewer for GitHub PRs (GigaChat) with RAG context and MCP GitHub integration.

## Features
- ✅ Automatic PR reviews with blocking/non-blocking split
- 🧠 Context-aware via RAG cache
- 🔄 MCP GitHub server for fetching/posting
- 📝 Structured Markdown output with file/line citations

## Quickstart (local)
1. Install deps (isolated от монорепо):
   ```bash
   cd code_review
   pip install -r requirements.txt  # или pip install -e .
   npm install -g @modelcontextprotocol/server-github
   ```
2. Export env: `GITHUB_TOKEN`, `GIGACHAT_CREDENTIALS`, и либо `GITHUB_REPO`, либо `REPO_OWNER` + `REPO_NAME`. При необходимости укажи `PROJECT_ROOT` (по умолчанию `pwd`).
3. Собери RAG индекс для кеша:
   ```bash
   PROJECT_ROOT=$(pwd)/.. python -m code_review.build_index
   ```
4. Прогон без публикации:
   ```bash
   python -m code_review.main --pr 123 --repo owner/repo --no-post
   ```

## CI usage
- В GitHub Actions запускай `python -m code_review.github_action`.
- Workflow в репозитории не включён: добавь свой `.github/workflows/ai-code-review.yml`, который ставит Python + Node, устанавливает зависимости выше и прокидывает `PR_NUMBER`, `GITHUB_TOKEN`, `GIGACHAT_CREDENTIALS`, `REPO_OWNER/REPO_NAME` (или `GITHUB_REPO`).

## Architecture

```
GitHub PR Event → GitHub Actions Workflow
    ↓
code_review/github_action.py (Orchestrator)
    ├── PRFetcher (MCP) → Fetch PR data from GitHub
    ├── ContextBuilder (RAG) → Gather project context
    ├── AIReviewer (GigaChat) → Generate review
    └── ReviewPoster (MCP) → Post comment to GitHub
```

### Components

| Module | Responsibility |
|--------|----------------|
| `models.py` | Data structures (PRData, ReviewResult, etc.) |
| `config.py` | Environment-driven configuration |
| `pr_fetcher.py` | Fetch PR data via MCP GitHub server |
| `context_builder.py` | Build review context using RAG |
| `reviewer.py` | Generate reviews using GigaChat |
| `formatter.py` | Format reviews as Markdown |
| `poster.py` | Post reviews to GitHub via MCP |
| `github_action.py` | Actions entrypoint |
| `build_index.py` | Build RAG index |
| `main.py` | Local CLI |

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | GitHub API token | ✅ |
| `GIGACHAT_CREDENTIALS` | Base64 `client_id:client_secret` | ✅ |
| `PR_NUMBER` | Pull request number | ✅ в Actions |
| `REPO_OWNER` / `REPO_NAME` | Repo owner/name | ✅ в Actions (если нет `GITHUB_REPO`) |
| `GITHUB_REPO` | `owner/repo` shorthand | ✅ локально |
| `PROJECT_ROOT` | Project root for RAG cache | Опционально (`os.getcwd()` по умолчанию) |
| `mcp_github_command` | MCP GitHub server command (по умолчанию `npx -y @modelcontextprotocol/server-github`) | Опционально |

## PR size limits
- Макс файлов: 30
- Макс строк (добавления + удаления): 2000
- При превышении возвращается просьба разбить PR.

## Review output
- Summary
- Blocking Issues (с ссылками file:line)
- Non-Blocking Issues
- Tests assessment
- Risks / Suggested improvements

## RAG context
- Источники: `README.md`, `CONTRIBUTING.md`, исходники и конфиги.
- Кэш индекса: `.cache/rag_index.json` в `PROJECT_ROOT`. Пересборка: `python -m code_review.build_index`.

## Development
- Тесты: `pytest code_review/tests -v`.
- Структура:
  ```
  code_review/
  ├── build_index.py
  ├── config.py
  ├── context_builder.py
  ├── formatter.py
  ├── github_action.py
  ├── main.py
  ├── models.py
  ├── poster.py
  ├── pr_fetcher.py
  ├── reviewer.py
  ├── prompts/
  └── tests/
  ```
- Зависимости из `requirements.txt` изолированы от остальной монорепы.

## Troubleshooting
- "Configuration error": проверь обязательные env.
- "MCP connection error": убедись, что `@modelcontextprotocol/server-github` установлен и доступен в `$PATH`.
- "RAG index missing": пересобери `python -m code_review.build_index` (учти `PROJECT_ROOT`).

## License

Same as parent project.
