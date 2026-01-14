# AI Code Review System

Automatic code review system for GitHub Pull Requests using GigaChat LLM, RAG context, and MCP protocol.

## Features

- ✅ **Automatic PR Review**: Triggered on every pull request
- 🧠 **AI-Powered**: Uses GigaChat for intelligent code analysis
- 📚 **Context-Aware**: RAG system provides project-specific context
- 🔄 **MCP Integration**: Uses Model Context Protocol for GitHub operations
- 🚨 **Smart Issue Detection**: Separates blocking from non-blocking issues
- 📝 **Structured Output**: Markdown reviews with clear sections

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
| `config.py` | Configuration management from environment |
| `pr_fetcher.py` | Fetch PR data via MCP GitHub server |
| `context_builder.py` | Build review context using RAG |
| `reviewer.py` | Generate reviews using GigaChat |
| `formatter.py` | Format reviews as Markdown |
| `poster.py` | Post reviews to GitHub via MCP |
| `github_action.py` | Main orchestrator for GitHub Actions |
| `build_index.py` | Build RAG index for caching |
| `main.py` | Local testing CLI |

## Setup

### 1. Prerequisites

- Python 3.10+
- Node.js 20+ (for MCP GitHub server)
- GitHub repository access
- GigaChat API credentials

### 2. Install Dependencies

**Option 1: Using requirements.txt (recommended)**
```bash
cd code_review
pip install -r requirements.txt
npm install -g @modelcontextprotocol/server-github
```

**Option 2: Using pyproject.toml**
```bash
cd code_review
pip install -e .
npm install -g @modelcontextprotocol/server-github
```

**Note:** Code review has isolated dependencies and doesn't conflict with other projects in the monorepo.

### 3. Configure GitHub Secrets

Add these secrets to your repository:

- `GITHUB_TOKEN`: Automatically provided by Actions
- `GIGACHAT_CREDENTIALS`: Base64 encoded `client_id:client_secret`

### 4. Enable Workflow

The workflow is automatically enabled when you commit `.github/workflows/ai-code-review.yml`.

## Local Testing

### Build RAG Index

```bash
export PROJECT_ROOT=$(pwd)
python -m code_review.build_index
```

### Test Against Real PR

```bash
export GITHUB_TOKEN="ghp_your_token"
export GIGACHAT_CREDENTIALS="base64_encoded_credentials"

python -m code_review.main --pr 123 --repo owner/repo
```

Use `--no-post` flag to preview review without posting:

```bash
python -m code_review.main --pr 123 --repo owner/repo --no-post
```

## Configuration

Environment variables (set in GitHub Actions or locally):

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | GitHub API token | ✅ |
| `GIGACHAT_CREDENTIALS` | GigaChat API credentials (Base64) | ✅ |
| `PR_NUMBER` | Pull request number | ✅ (Actions) |
| `REPO_OWNER` | Repository owner | ✅ (Actions) |
| `REPO_NAME` | Repository name | ✅ (Actions) |
| `GITHUB_REPO` | Full repo path (owner/repo) | ✅ (Local) |
| `PROJECT_ROOT` | Project root directory | Optional |

## PR Size Limits

To ensure quality reviews within token limits:

- **Max files**: 30 changed files
- **Max lines**: 2000 lines changed (additions + deletions)

PRs exceeding these limits will receive a polite message suggesting to split the PR.

## Review Output

Generated reviews include:

1. **Summary**: Brief overview of the PR
2. **Blocking Issues**: Must be fixed before merge (security, bugs, breaking changes)
3. **Non-Blocking Issues**: Suggestions for improvement (style, performance, refactoring)
4. **Tests Assessment**: Evaluation of test coverage
5. **Risks**: Potential issues to be aware of
6. **Suggested Improvements**: Future enhancements

### Example Output

```markdown
# 🤖 AI Code Review

## Summary
This PR adds user authentication using JWT. Implementation looks solid but has one security concern.

## 🚨 Blocking Issues

### 1. api/auth.py
**`api/auth.py:45`**
Password comparison uses `==` instead of constant-time comparison, vulnerable to timing attacks

💡 **Suggestion:** Use `secrets.compare_digest(password, stored_hash)` for constant-time comparison

## ✅ No Non-Blocking Issues

## 🧪 Tests
Good test coverage for happy path. Consider adding tests for edge cases (expired tokens, invalid signatures).

## ⚠️ Risks
- Breaking change: New authentication required for all API endpoints

## 🚀 Suggested Improvements
- Add rate limiting to prevent brute force attacks
- Consider implementing refresh tokens
```

## RAG Context

The system uses RAG (Retrieval-Augmented Generation) to provide project-specific context:

### Indexed Sources
- `README.md` - Project overview
- `CONTRIBUTING.md` - Contribution guidelines
- All source code - Existing patterns and conventions
- Configuration files - Linting rules and standards

### Context Retrieval
For each PR, the system:
1. Extracts key terms from PR title, description, and changed files
2. Searches RAG index for relevant documentation and code patterns
3. Includes top results in the review prompt

### Cache Strategy
- Index is cached at `.cache/rag_index.json`
- GitHub Actions caches index across workflow runs
- Index rebuilds automatically when cache is stale

## Anti-Hallucination Measures

To ensure accurate reviews:

1. **Explicit constraints**: Reviewer only comments on visible code
2. **Citation requirement**: All issues must cite `file:line`
3. **Uncertainty handling**: System says "needs human review" when uncertain
4. **Evidence requirement**: Issues must quote problematic code
5. **JSON schema**: Structured output prevents rambling

## Development

### Running Tests

```bash
pytest code_review/tests/ -v
```

### Code Structure

```
code_review/
├── __init__.py
├── models.py           # Data structures
├── config.py           # Configuration
├── pr_fetcher.py       # MCP GitHub integration
├── context_builder.py  # RAG integration
├── reviewer.py         # GigaChat integration
├── formatter.py        # Markdown formatting
├── poster.py           # GitHub posting
├── github_action.py    # Main orchestrator
├── build_index.py      # RAG indexing
├── main.py            # Local testing CLI
├── prompts/
│   └── system_prompt.txt
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_formatter.py
    └── test_context_builder.py
```

## Troubleshooting

### Review fails with "Configuration error"

Ensure all required environment variables are set. Check GitHub Actions secrets.

### Review fails with "MCP connection error"

Ensure `@modelcontextprotocol/server-github` is installed:
```bash
npm install -g @modelcontextprotocol/server-github
```

### Review fails with "RAG index missing"

Build the index manually:
```bash
python -m code_review.build_index
```

### Review posts but is low quality

- Check that RAG index is up to date
- Verify GigaChat credentials are correct
- Review system prompt in `prompts/system_prompt.txt`

## Performance

For medium PRs (15 files, 800 lines):
- PR data fetch: 2-5 seconds
- RAG context retrieval: 1-2 seconds
- GigaChat inference: 10-30 seconds
- Review posting: 2-5 seconds
- **Total**: ~15-42 seconds

## Security

- GitHub token has minimal permissions (`contents: read`, `pull-requests: write`)
- Tokens are never logged or exposed
- Path traversal protection for file operations
- Input validation on all external data

## License

Same as parent project.

## Contributing

See project's main CONTRIBUTING.md for guidelines.
