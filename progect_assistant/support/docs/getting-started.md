# Getting Started with project_assistant Support

## Installation

project_assistant is a Python-based AI assistant with RAG (Retrieval-Augmented Generation) and MCP (Model Context Protocol) integration.

### Requirements
- Python 3.8 or higher
- pip package manager
- Optional: Ollama for local LLM (or HuggingFace API key)

### Quick Start

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd aI-advent-challenge/progect_assistant
   ```

2. **Set environment variables** (optional):
   ```bash
   export PROJECT_ROOT=/path/to/progect_assistant
   export OLLAMA_MODEL=llama2  # or your preferred model
   ```

3. **Run the CLI**:
   ```bash
   python -m progect_assistant.main
   ```

4. **Run the Web UI**:
   ```bash
   python -m progect_assistant.web_server
   # Open http://127.0.0.1:8088 in your browser
   ```

## Common Issues

### Issue: RAG Index Not Loading

**Symptoms**:
- Running `/index` completes but searches return no results
- `.cache/rag_index.json` file exists but is empty or malformed

**Solutions**:
1. Check file permissions on `.cache` directory:
   ```bash
   ls -la .cache/
   chmod 755 .cache
   chmod 644 .cache/rag_index.json
   ```

2. Verify PROJECT_ROOT is set correctly:
   ```bash
   echo $PROJECT_ROOT
   # Should point to progect_assistant directory
   ```

3. Rebuild index manually:
   ```bash
   python -m progect_assistant.main
   > /index
   ```

4. Check for file system errors in logs:
   ```bash
   tail -f progect_assistant/logs/assistant.log
   ```

### Issue: MCP Connection Failures

**Symptoms**:
- Tools are unavailable
- `/mcp list` returns empty or error
- MCP server fails to start

**Solutions**:
1. Install MCP package:
   ```bash
   pip install mcp
   # or
   pip install anthropic-mcp
   ```

2. Check `mcp_config.json` configuration:
   ```json
   {
     "assistant": {
       "command": "python -m progect_assistant.mcp_server",
       "env": {
         "PROJECT_ROOT": "${PROJECT_ROOT}"
       }
     }
   }
   ```

3. Test MCP server directly:
   ```bash
   python -m progect_assistant.mcp_server
   # Should start without errors
   ```

4. Verify Python environment has access to `mcp` module:
   ```bash
   python -c "import mcp; print(mcp.__version__)"
   ```

### Issue: Web UI Not Accessible

**Symptoms**:
- Browser cannot connect to http://127.0.0.1:8088
- Connection timeout or refused

**Solutions**:
1. Check if port 8088 is already in use:
   ```bash
   # On Linux/Mac:
   lsof -i :8088

   # On Windows:
   netstat -an | findstr :8088
   ```

2. Kill existing process on port 8088:
   ```bash
   # Find PID from lsof output, then:
   kill <PID>
   ```

3. Check if web server started successfully:
   ```bash
   python -m progect_assistant.web_server
   # Should see: "Server running on http://127.0.0.1:8088"
   ```

4. Try accessing from localhost explicitly:
   - Instead of 127.0.0.1, try: http://localhost:8088

## Best Practices

### RAG Indexing
- Run `/index` after updating documentation
- Exclude large directories (node_modules, .git) - already handled by default
- Index is cached in `.cache/rag_index.json` for fast loading
- Re-index if documentation changes significantly

### Using Tools
- Use `/help <topic>` for context-aware answers from RAG
- CLI commands start with `/` (e.g., `/index`, `/tool`, `/mcp`)
- Tools can be called directly: `/tool <name> <json_params>`
- Check available tools: `/mcp list` or see tools panel in Web UI

### MCP Integration
- MCP tools enhance assistant capabilities
- Git operations available via git MCP server
- Support tools available via support MCP server
- Tools automatically discovered from mcp_config.json

### Performance Tips
1. **Faster indexing**: Limit directory depth in `assistant/rag/index.py`
2. **Faster searches**: Use specific keywords in queries
3. **Smaller models**: Use faster models like Llama 2 7B for better latency
4. **Cache**: Don't delete `.cache` directory unnecessarily

## Next Steps

- Read [troubleshooting.md](troubleshooting.md) for advanced issues
- Explore `/help` command with different topics
- Try creating custom tools in `assistant/tools/` (see `builtin.py` for examples)
- Configure MCP servers in `mcp_config.json`
