# Troubleshooting Guide

## Performance Issues

### Slow RAG Indexing

**Cause**: Large codebase with many files and deep directory structures.

**Solutions**:

1. **Exclude large directories**:
   - The system already ignores: `.git`, `node_modules`, `__pycache__`, `venv`, `.venv`
   - Check ignore patterns in `assistant/rag/index.py` (see `RagIndexer.discover_files`)

2. **Limit directory depth**:
   - Modify `discover_files()` in `assistant/rag/index.py` to limit recursion depth
   - Focus on key directories: `docs/`, `assistant/`, README files

3. **Manual cleanup**:
   ```bash
   # Remove cache and rebuild
   rm .cache/rag_index.json
   python -m progect_assistant.main
   > /index
   ```

4. **Check file sizes**:
   ```bash
   find . -type f -name "*.md" -size +1M
   # Large markdown files slow down chunking
   ```

### Web UI Latency

**Cause**: Large model or slow LLM provider response times.

**Solutions**:

1. **Use smaller/faster models**:
   ```bash
   # For Ollama:
   export OLLAMA_MODEL=llama2:7b  # instead of 13b/70b

   # For HuggingFace:
   export HF_MODEL=google/flan-t5-base  # faster than large models
   ```

2. **Increase timeout values**:
   - Modify timeout in `assistant/llm.py` (default: 30s)
   - Edit `web/app.js` fetch timeout for API calls

3. **Local LLM optimization**:
   - For Ollama, use GPU acceleration if available
   - Ensure Ollama is running: `ollama serve`
   - Check model is loaded: `ollama list`

4. **Check network latency**:
   ```bash
   # Test Ollama connection:
   curl http://localhost:11434/api/version

   # Test HuggingFace API:
   curl -H "Authorization: Bearer $HF_API_KEY" \
     https://api-inference.huggingface.co/status
   ```

### Memory Usage Issues

**Cause**: Large vector index or too many concurrent requests.

**Solutions**:

1. **Monitor memory**:
   ```bash
   # Check Python process memory:
   ps aux | grep python
   ```

2. **Limit index size**:
   - Reduce number of indexed files
   - Smaller chunk sizes in `assistant/rag/index.py` (default: 1000 chars)

3. **Restart services periodically**:
   - Web server and MCP servers may accumulate memory
   - Use process managers like systemd or supervisor for automatic restarts

## Configuration Problems

### API Keys Not Working

**Symptom**: "HF_API_KEY is required" or authentication errors.

**Solutions**:

1. **Set environment variable properly**:
   ```bash
   # For current session:
   export HF_API_KEY=hf_your_key_here

   # For permanent (add to ~/.bashrc or ~/.zshrc):
   echo 'export HF_API_KEY=hf_your_key_here' >> ~/.bashrc
   source ~/.bashrc
   ```

2. **Verify key is set**:
   ```bash
   echo $HF_API_KEY
   # Should print your key, not empty
   ```

3. **Use Web UI override**:
   - Web interface has API key override buttons
   - Useful for testing without setting environment variables

4. **Test API key validity**:
   ```bash
   curl -H "Authorization: Bearer $HF_API_KEY" \
     https://api-inference.huggingface.co/models/gpt2
   # Should return model info, not 401 error
   ```

**Note**: Ollama doesn't require API keys (it's local).

### MCP Server Configuration Errors

**Symptom**: MCP tools not loading, "server command failed".

**Solutions**:

1. **Check mcp_config.json syntax**:
   ```bash
   # Validate JSON:
   python -m json.tool mcp_config.json
   # Should print formatted JSON, no errors
   ```

2. **Verify paths in config**:
   ```json
   {
     "assistant": {
       "command": "python -m progect_assistant.mcp_server",
       "env": {
         "PROJECT_ROOT": "${PROJECT_ROOT}",
         "PYTHONPATH": "${PROJECT_ROOT}"
       }
     }
   }
   ```
   - Ensure `PROJECT_ROOT` variable is set
   - Command should be executable

3. **Test server manually**:
   ```bash
   # Set required env vars:
   export PROJECT_ROOT=/path/to/progect_assistant
   export PYTHONPATH=$PROJECT_ROOT

   # Run server:
   python -m progect_assistant.mcp_server
   # Should start without ImportError or other exceptions
   ```

4. **Check Python path**:
   ```bash
   python -c "import sys; print(sys.path)"
   # Should include PROJECT_ROOT
   ```

### Git MCP Adapter Issues

**Symptom**: Git tools fail, "git command not found" in MCP mode.

**Solutions**:

1. **Ensure git is installed**:
   ```bash
   git --version
   # Should print git version, not "command not found"
   ```

2. **Check git_mcp_server.py**:
   - Located in: `progect_assistant/git_mcp_server.py`
   - Uses subprocess to run git commands
   - Requires git in PATH

3. **Test git operations**:
   ```bash
   # In project directory:
   git status
   git log --oneline -5
   # Should work without errors
   ```

4. **Fallback to local git**:
   - If MCP fails, `assistant/mcp/git_adapter.py` (`GitMCPAdapter`) falls back to local subprocess calls
   - Check logs in `progect_assistant/logs/assistant.log`

## Tool Execution Errors

### Tool Not Found

**Symptom**: "Tool 'xyz' not found in registry".

**Solutions**:

1. **List available tools**:
   ```bash
   python -m progect_assistant.main
   > /mcp list
   # Shows all registered tools
   ```

2. **Check tool registration**:
   - Tools registered in `main.py` → `build_registry()`
   - Verify import statements and `registry.register()` calls

3. **Reload assistant**:
   - Exit and restart CLI
   - Code changes require restart to take effect

### Tool Parameter Errors

**Symptom**: "Missing required parameter" or "Invalid JSON".

**Solutions**:

1. **Check parameter schema**:
   - Each tool defines `parameters_schema` dict
   - See tool source code for required fields

2. **Use correct JSON format**:
   ```bash
   # Correct:
   /tool search_faq {"query": "setup"}

   # Wrong (missing quotes):
   /tool search_faq {query: setup}
   ```

3. **Escape special characters**:
   ```bash
   # If query contains quotes:
   /tool search_faq {"query": "how to \"escape\" quotes"}
   ```

## RAG-Specific Issues

### Search Returns Irrelevant Results

**Cause**: TF-IDF similarity may match common words, not semantic meaning.

**Solutions**:

1. **Use specific keywords**:
   - Instead of: "how to fix problem"
   - Use: "RAG index permission error"

2. **Check indexed content**:
   ```bash
   # View index file:
   cat .cache/rag_index.json | python -m json.tool | less
   # Verify your target documents are indexed
   ```

3. **Adjust similarity threshold**:
   - Modify `top_k` parameter in RAG search
   - Higher threshold = fewer but more relevant results

### Documentation Not Indexed

**Symptom**: `/help topic` finds nothing, but files exist.

**Solutions**:

1. **Check file patterns in `assistant/rag/index.py`**:
   - `RagIndexer.discover_files` defines which files are indexed
   - Supported: `*.md`, `*.txt`, `docs/**/*`, `support/**/*`
   - Not supported by default: `*.docx`, `*.pdf`

2. **Verify file extensions**:
   ```bash
   find docs -type f
   # Check if files have .md or .txt extension
   ```

3. **Manual re-index**:
   ```bash
   # Force rebuild:
   rm .cache/rag_index.json
   python -m progect_assistant.main
   > /index
   ```

4. **Check file encoding**:
   - RAG expects UTF-8 encoding
   - Binary files or wrong encoding cause failures:
   ```bash
   file docs/example.md
   # Should say "UTF-8 Unicode text"
   ```

## Web UI Specific Issues

### Chat Not Working

**Symptom**: Messages sent but no response.

**Solutions**:

1. **Check browser console**:
   - Open DevTools (F12)
   - Look for JavaScript errors or failed API calls

2. **Verify model configuration**:
   - Select provider (Ollama/HuggingFace) in UI
   - Enter API key if using HuggingFace
   - Click "Load Models" button

3. **Test backend**:
   ```bash
   # Check if server responds:
   curl http://127.0.0.1:8088/api/models
   # Should return list of models, not 500 error
   ```

4. **Enable RAG context**:
   - Toggle "Enable RAG" checkbox in UI
   - Verify index exists: check ".cache/rag_index.json"

### Tools Panel Empty

**Symptom**: Tools panel shows "No tools available".

**Solutions**:

1. **Load tools**:
   - Cl click "Refresh Tools" button in UI
   - Check browser console for errors

2. **Start MCP servers**:
   - MCP servers must be running for tools to load
   - Start manually or via mcp_config.json

3. **Check API endpoint**:
   ```bash
   curl http://127.0.0.1:8088/api/tools
   # Should return JSON list of tools
   ```

## Getting More Help

If issues persist:

1. **Check logs**:
   ```bash
   tail -f progect_assistant/logs/assistant.log
   ```

2. **Enable debug mode** (if available):
   - Set `DEBUG=1` environment variable
   - Restart services

3. **Create a support ticket**:
   - Use the Support Mode in Web UI
   - Provide error messages and logs
   - Include: OS, Python version, installation method

4. **Search for similar issues**:
   - Use `/tool search_tickets` to find similar problems
   - Check FAQ: `/tool search_faq`

## See Also

- [Getting Started Guide](getting-started.md)
- [FAQ](../faq.json)
- Source code: `assistant/rag/index.py`, `web_server.py`, `main.py`
