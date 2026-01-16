const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const clearChat = document.getElementById("clearChat");
const providerSelect = document.getElementById("provider");
let modelInput = document.getElementById("model");
const baseUrlInput = document.getElementById("baseUrl");
const hfBaseUrlInput = document.getElementById("hfBaseUrl");
const hfKeyInput = document.getElementById("hfKey");
const useMcpToggle = document.getElementById("useMcp");
const toolList = document.getElementById("toolList");
const refreshTools = document.getElementById("refreshTools");
const callToolBtn = document.getElementById("callTool");
const toolNameInput = document.getElementById("toolName");
const toolArgsInput = document.getElementById("toolArgs");
const toolResult = document.getElementById("toolResult");
const loadModelsBtn = document.getElementById("loadModels");
const modelCount = document.getElementById("modelCount");
const overrideHfKeyBtn = document.getElementById("overrideHfKey");
const toolNameSelect = document.getElementById("toolName");
const clearToolResultBtn = document.getElementById("clearToolResult");
const mcpServerInfo = document.getElementById("mcpServerInfo");
const runIndexBtn = document.getElementById("runIndex");
const ragProgressBar = document.getElementById("ragProgressBar");
const ragProgressText = document.getElementById("ragProgressText");
const ragContextPanel = document.getElementById("ragContextPanel");
const ragContextText = document.getElementById("ragContextText");
const supportModeToggle = document.getElementById("supportMode");
const supportPanel = document.getElementById("supportPanel");
const ticketList = document.getElementById("ticketList");
const ticketDetail = document.getElementById("ticketDetail");
const ticketTitle = document.getElementById("ticketTitle");
const ticketInfo = document.getElementById("ticketInfo");
const ticketComments = document.getElementById("ticketComments");
const commentForm = document.getElementById("commentForm");
const commentInput = document.getElementById("commentInput");
const backToListBtn = document.getElementById("backToList");
const statusFilter = document.getElementById("statusFilter");
const createTicketBtn = document.getElementById("createTicketBtn");
const issuesPanel = document.getElementById("issuesPanel");
const issueList = document.getElementById("issueList");

let messages = [];
let currentTicket = null;
let defaultConfig = {};
let isHfKeyOverridden = false;
let ragPollTimer = null;
let createdIssues = [];

const showMessage = (role, content) => {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  // Header with role label and copy button
  const header = document.createElement("div");
  header.className = "message-header";

  const roleLabel = document.createElement("div");
  roleLabel.className = "role";
  roleLabel.textContent = role === "assistant" ? "assistant" : "you";

  const copyBtn = document.createElement("button");
  copyBtn.className = "copy-btn ghost small";
  copyBtn.textContent = "Copy";
  copyBtn.title = "Copy raw text without formatting";
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(content).then(() => {
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
    });
  };

  header.appendChild(roleLabel);
  header.appendChild(copyBtn);

  // Body with rendered markdown
  const body = document.createElement("div");
  body.className = "message-body";

  if (role === "assistant" && typeof marked !== "undefined") {
    // Configure marked for safe rendering
    marked.setOptions({
      breaks: true,
      gfm: true,
    });
    // Sanitize HTML with DOMPurify to prevent XSS
    const rawHtml = marked.parse(content);
    const sanitizedHtml = typeof DOMPurify !== "undefined"
      ? DOMPurify.sanitize(rawHtml)
      : content;
    body.innerHTML = sanitizedHtml;
  } else {
    body.textContent = content;
  }

  wrapper.appendChild(header);
  wrapper.appendChild(body);
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
};

const renderIssues = () => {
  if (!issueList) return;
  issueList.innerHTML = "";
  if (!createdIssues.length) {
    issueList.innerHTML = "<p class='note'>No issues created yet.</p>";
    return;
  }

  createdIssues.forEach((issue) => {
    const card = document.createElement("div");
    card.className = `issue-card${issue.success === false ? " issue-card-error" : ""}`;

    const header = document.createElement("div");
    header.className = "issue-header";

    const info = document.createElement("div");
    const title = document.createElement("div");
    title.className = "issue-title";
    title.textContent = issue.title || "GitHub issue";
    info.appendChild(title);

    const metaParts = [];
    if (issue.number) metaParts.push(`#${issue.number}`);
    const labels = Array.isArray(issue.labels) ? issue.labels.filter(Boolean) : [];
    if (labels.length) metaParts.push(labels.join(", "));
    if (metaParts.length) {
      const meta = document.createElement("div");
      meta.className = "issue-meta";
      meta.textContent = metaParts.join(" · ");
      info.appendChild(meta);
    }

    if (issue.name) {
      const tool = document.createElement("div");
      tool.className = "issue-tool";
      tool.textContent = issue.name;
      info.appendChild(tool);
    }

    header.appendChild(info);

    if (issue.url) {
      const link = document.createElement("a");
      link.className = "issue-link";
      link.href = issue.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Open ↗";
      header.appendChild(link);
    }

    card.appendChild(header);

    if (issue.success === false) {
      const error = document.createElement("div");
      error.className = "issue-error";
      error.textContent = issue.error || "Issue creation failed.";
      card.appendChild(error);
    }

    issueList.appendChild(card);
  });

  if (issuesPanel) {
    issuesPanel.open = true;
  }
};

const upsertIssues = (issues = []) => {
  issues.forEach((issue) => {
    const existingIdx = createdIssues.findIndex(
      (item) => (issue.url && item.url === issue.url) || (issue.number && item.number === issue.number)
    );
    if (existingIdx >= 0) {
      createdIssues[existingIdx] = { ...createdIssues[existingIdx], ...issue };
    } else {
      createdIssues.unshift(issue);
    }
  });
  createdIssues = createdIssues.slice(0, 10);
  renderIssues();
};

const issuesFromToolResults = (toolResults = []) => {
  const collected = [];
  toolResults.forEach((item) => {
    const name = String(item.name || "");
    if (!name.includes("create_github_issue")) return;
    const result = item.result || {};
    collected.push({
      name,
      success: result.success !== false,
      number: result.number,
      title: result.title,
      url: result.url || result.html_url,
      labels: Array.isArray(result.labels) ? result.labels : [],
      error: result.error,
    });
  });
  return collected;
};

const fetchConfig = async () => {
  const response = await fetch("/api/config");
  if (!response.ok) return;
  const data = await response.json();
  defaultConfig = data;

  // Ollama configuration
  baseUrlInput.value = data.ollama?.base_url || "";

  // HuggingFace configuration
  hfBaseUrlInput.value = data.huggingface?.base_url || "";

  if (data.huggingface?.api_key_masked) {
    hfKeyInput.placeholder = `Env: ${data.huggingface.api_key_masked} [Override to change]`;
    hfKeyInput.setAttribute('data-has-env-key', 'true');
    overrideHfKeyBtn.style.display = 'block';
  } else {
    hfKeyInput.placeholder = "hf_...";
    hfKeyInput.removeAttribute('data-has-env-key');
    overrideHfKeyBtn.style.display = 'none';
  }

};

const loadOllamaModels = async () => {
  const baseUrl = encodeURIComponent(baseUrlInput.value || "");
  modelInput = document.getElementById("model"); // Ensure we have the current reference
  modelInput.innerHTML = '<option value="">Loading...</option>';
  modelCount.textContent = "";

  try {
    const response = await fetch(`/api/ollama/models?base_url=${baseUrl}`);
    if (!response.ok) {
      modelInput.innerHTML = '<option value="">Failed to load models</option>';
      return;
    }

    const data = await response.json();
    const models = data.models || [];
    const defaultModel = defaultConfig.ollama?.model || "";

    modelInput.innerHTML = "";

    if (models.length === 0) {
      modelInput.innerHTML = '<option value="">No models found</option>';
      modelCount.textContent = "(0 available)";
      return;
    }

    // Add all available models to select
    models.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;

      // Mark default model
      if (name === defaultModel) {
        option.selected = true;
        option.textContent = `${name} (default)`;
      }

      modelInput.appendChild(option);
    });

    // Update model count
    modelCount.textContent = `(${models.length} available)`;

    // Set default if not found in list
    if (!models.includes(defaultModel) && defaultModel) {
      const option = document.createElement("option");
      option.value = defaultModel;
      option.textContent = `${defaultModel} (default)`;
      option.selected = true;
      modelInput.insertBefore(option, modelInput.firstChild);
    }
  } catch (error) {
    modelInput.innerHTML = '<option value="">Error loading models</option>';
    console.error("Failed to load Ollama models:", error);
  }
};

const fetchTools = async () => {
  toolList.textContent = "";
  toolNameSelect.innerHTML = '<option value="">Select a tool...</option>';

  const response = await fetch("/api/mcp/tools");
  if (!response.ok) {
    toolList.textContent = "Unable to load tools.";
    mcpServerInfo.textContent = "Disconnected ✗";
    mcpServerInfo.className = "mcp-info error";
    return;
  }

  const data = await response.json();
  const tools = data.tools || [];
  const servers = data.servers || [];

  // Update server info
  if (servers.length) {
    mcpServerInfo.textContent = `mcp: ${servers.join(", ")} (${tools.length} tools) ●`;
  } else {
    mcpServerInfo.textContent = `mcp (${tools.length} tools) ●`;
  }
  mcpServerInfo.className = "mcp-info connected";

  if (!tools.length) {
    toolList.textContent = "No MCP tools detected.";
    return;
  }

  tools.forEach((tool) => {
    // Create expanded tool card
    const card = createToolCard(tool);
    toolList.appendChild(card);

    // Add to dropdown
    const option = document.createElement("option");
    option.value = tool.name;
    option.textContent = tool.name;
    toolNameSelect.appendChild(option);
  });
};

const createToolCard = (tool) => {
  const card = document.createElement("div");
  card.className = "tool-card";

  // Header with name and Use button
  const header = document.createElement("div");
  header.className = "tool-card-header";

  const title = document.createElement("h4");
  title.textContent = tool.name;

  const useBtn = document.createElement("button");
  useBtn.className = "ghost small";
  useBtn.textContent = "Use";
  useBtn.title = "Auto-fill manual testing form";
  useBtn.onclick = () => useToolInForm(tool);

  header.appendChild(title);
  header.appendChild(useBtn);
  card.appendChild(header);

  // Description
  const desc = document.createElement("p");
  desc.textContent = tool.description || "No description.";
  card.appendChild(desc);

  // Parameters section
  if (tool.inputSchema && tool.inputSchema.properties) {
    const paramsSection = document.createElement("div");
    paramsSection.className = "tool-params";

    const paramsTitle = document.createElement("strong");
    paramsTitle.textContent = "Parameters:";
    paramsSection.appendChild(paramsTitle);

    const paramsList = document.createElement("ul");
    const required = tool.inputSchema.required || [];

    Object.entries(tool.inputSchema.properties).forEach(([name, schema]) => {
      const item = document.createElement("li");
      const isRequired = required.includes(name);
      const type = schema.type || "any";

      item.innerHTML = `<code>${name}</code> (${type}${isRequired ? ', required' : ', optional'})`;

      if (schema.description) {
        const desc = document.createElement("div");
        desc.className = "param-desc";
        desc.textContent = schema.description;
        item.appendChild(desc);
      }

      paramsList.appendChild(item);
    });

    paramsSection.appendChild(paramsList);
    card.appendChild(paramsSection);

    // Example JSON
    const example = generateExampleJSON(tool.inputSchema);
    if (example) {
      const exampleSection = document.createElement("div");
      exampleSection.className = "tool-example";

      const exampleTitle = document.createElement("strong");
      exampleTitle.textContent = "Example:";
      exampleSection.appendChild(exampleTitle);

      const exampleCode = document.createElement("code");
      exampleCode.textContent = example;
      exampleSection.appendChild(exampleCode);

      card.appendChild(exampleSection);
    }
  }

  return card;
};

const generateExampleJSON = (schema) => {
  if (!schema.properties) return null;

  const example = {};
  Object.entries(schema.properties).forEach(([name, prop]) => {
    if (prop.default !== undefined) {
      example[name] = prop.default;
    } else if (prop.type === "string") {
      example[name] = "example";
    } else if (prop.type === "integer" || prop.type === "number") {
      example[name] = 100;
    } else if (prop.type === "boolean") {
      example[name] = true;
    }
  });

  return Object.keys(example).length > 0 ? JSON.stringify(example, null, 2) : null;
};

const useToolInForm = (tool) => {
  // Select tool in dropdown
  toolNameSelect.value = tool.name;

  // Generate example arguments
  const example = generateExampleJSON(tool.inputSchema);
  toolArgsInput.value = example || "{}";

  // Scroll to form
  document.querySelector('.tool-call').scrollIntoView({ behavior: 'smooth' });

  // Focus on arguments
  toolArgsInput.focus();
};

const renderRagStatus = (status) => {
  if (!status) return;
  const state = status.state || "idle";
  const total = status.total_files || 0;
  const processed = status.processed_files || 0;
  const currentFile = status.current_file || "";
  const chunks = status.chunks || 0;
  const error = status.error || "";

  const progress = total > 0 ? Math.min((processed / total) * 100, 100) : 0;
  ragProgressBar.style.width = `${progress}%`;

  if (state === "running") {
    ragProgressText.textContent = `Indexing ${processed}/${total}${currentFile ? `: ${currentFile}` : ""}`;
  } else if (state === "done") {
    ragProgressText.textContent = `Complete: ${chunks} chunks from ${total} files.`;
  } else if (state === "error") {
    ragProgressText.textContent = `Error: ${error || "indexing failed"}`;
  } else {
    ragProgressText.textContent = "Idle";
  }

  runIndexBtn.disabled = state === "running";
  runIndexBtn.textContent = state === "running" ? "Indexing..." : "Reindex";

  if (state === "running") {
    if (!ragPollTimer) {
      ragPollTimer = setInterval(fetchRagStatus, 1000);
    }
  } else if (ragPollTimer) {
    clearInterval(ragPollTimer);
    ragPollTimer = null;
  }
};

const fetchRagStatus = async () => {
  const response = await fetch("/api/rag/status");
  if (!response.ok) return;
  const data = await response.json();
  renderRagStatus(data.status);
};

const startRagIndex = async () => {
  runIndexBtn.disabled = true;
  ragProgressText.textContent = "Starting indexing...";
  if (!ragPollTimer) {
    ragPollTimer = setInterval(fetchRagStatus, 1000);
  }
  const response = await fetch("/api/rag/index", { method: "POST" });
  if (!response.ok) {
    ragProgressText.textContent = "Failed to start indexing.";
    runIndexBtn.disabled = false;
    if (ragPollTimer) {
      clearInterval(ragPollTimer);
      ragPollTimer = null;
    }
    return;
  }
  const data = await response.json();
  renderRagStatus(data.status);
};

const updateProviderFields = async () => {
  const provider = providerSelect.value;
  document.querySelectorAll("[data-provider]").forEach((field) => {
    field.style.display = field.dataset.provider === provider ? "grid" : "none";
  });

  if (provider === "ollama") {
    // Show select with Ollama models
    modelInput.outerHTML = '<select id="model" class="model-select"><option value="">Loading...</option></select>';
    modelInput = document.getElementById("model");
    loadModelsBtn.style.display = "block";
    await loadOllamaModels();
  } else if (provider === "huggingface") {
    // Show text input for HuggingFace
    const currentValue = modelInput.value || defaultConfig.huggingface?.model || "";
    modelInput.outerHTML = `<input id="model" type="text" placeholder="meta-llama/Meta-Llama-3.1-8B-Instruct" value="${currentValue}" />`;
    modelInput = document.getElementById("model");
    loadModelsBtn.style.display = "none";
    modelCount.textContent = "";
  }
};

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = chatInput.value.trim();
  if (!content) return;
  messages.push({ role: "user", content });
  showMessage("user", content);
  chatInput.value = "";

  const provider = providerSelect.value;
  const payload = {
    provider: provider,
    model: modelInput.value,
    base_url: provider === "ollama" ? baseUrlInput.value : hfBaseUrlInput.value,
    api_key: hfKeyInput.value,
    use_mcp: useMcpToggle.checked,
    messages,
  };

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    showMessage("assistant", data.error || "Request failed.");
    return;
  }

  const message = data.message?.content || "";
  messages.push({ role: "assistant", content: message });
  showMessage("assistant", message);

  if (Object.prototype.hasOwnProperty.call(data, "rag_context")) {
    const context = data.rag_context || "No RAG context used.";
    ragContextText.textContent = context;
    ragContextPanel.open = true;
  }

  if (data.issues?.length) {
    upsertIssues(data.issues);
    const summaryLines = data.issues.map((issue) => {
      if (issue.success === false) {
        return `${issue.name || "issue"}: failed (${issue.error || "unknown error"})`;
      }
      const num = issue.number ? `#${issue.number}` : "";
      return `${issue.name || "issue"}: ${num} ${issue.url || ""}`.trim();
    });
    showMessage("assistant", `GitHub issues:\n${summaryLines.join("\n")}`);
  } else if (data.tool_results?.length) {
    const inferredIssues = issuesFromToolResults(data.tool_results);
    if (inferredIssues.length) {
      upsertIssues(inferredIssues);
      const summaryLines = inferredIssues.map((issue) => {
        if (issue.success === false) {
          return `${issue.name || "issue"}: failed (${issue.error || "unknown error"})`;
        }
        const num = issue.number ? `#${issue.number}` : "";
        return `${issue.name || "issue"}: ${num} ${issue.url || ""}`.trim();
      });
      showMessage("assistant", `GitHub issues:\n${summaryLines.join("\n")}`);
    }
  }

  if (data.tool_results?.length) {
    const toolSummary = data.tool_results
      .filter((item) => !String(item.name || "").includes("create_github_issue"))
      .map((item) => `${item.name}: ${JSON.stringify(item.result).slice(0, 200)}`)
      .join("\n");
    if (toolSummary) {
      showMessage("assistant", `Tool results:\n${toolSummary}`);
    }
  }
});

clearChat.addEventListener("click", () => {
  messages = [];
  chatLog.textContent = "";
});

refreshTools.addEventListener("click", () => {
  fetchTools();
});

loadModelsBtn.addEventListener("click", () => {
  loadOllamaModels();
});

callToolBtn.addEventListener("click", async () => {
  const name = toolNameSelect.value;
  if (!name) {
    toolResult.textContent = "Please select a tool.";
    return;
  }
  let argumentsPayload = {};
  if (toolArgsInput.value.trim()) {
    try {
      argumentsPayload = JSON.parse(toolArgsInput.value);
    } catch (err) {
      toolResult.textContent = "Invalid JSON arguments.";
      return;
    }
  }
  toolResult.textContent = "Running...";
  const response = await fetch("/api/mcp/call", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, arguments: argumentsPayload }),
  });
  const data = await response.json();
  toolResult.textContent = JSON.stringify(data.result || data, null, 2);

  const toolResults = [];
  if (data.result) {
    toolResults.push({ name, result: data.result });
  }
  const inferredIssues = issuesFromToolResults(toolResults);
  if (inferredIssues.length) {
    upsertIssues(inferredIssues);
  }
});

clearToolResultBtn.addEventListener("click", () => {
  toolResult.textContent = "";
});

runIndexBtn.addEventListener("click", () => {
  startRagIndex();
});

overrideHfKeyBtn.addEventListener("click", () => {
  isHfKeyOverridden = true;
  hfKeyInput.placeholder = "hf_... (temporary override)";
  hfKeyInput.focus();
  overrideHfKeyBtn.textContent = "🔒";
  overrideHfKeyBtn.title = "Using temporary override";
});

providerSelect.addEventListener("change", () => {
  isHfKeyOverridden = false;
  overrideHfKeyBtn.textContent = "🔓";
  overrideHfKeyBtn.title = "Override env API key";
  updateProviderFields();
});

// ================================
// Support Mode Functions
// ================================

const loadTickets = async () => {
  const response = await fetch("/api/support/tickets");
  if (!response.ok) return;
  const data = await response.json();
  renderTickets(data.tickets || []);
};

const renderTickets = (tickets) => {
  ticketList.innerHTML = "";

  // Apply status filter
  const filter = statusFilter.value;
  const filtered = filter ? tickets.filter(t => t.status === filter) : tickets;

  if (filtered.length === 0) {
    ticketList.innerHTML = "<p class='note'>No tickets found</p>";
    return;
  }

  filtered.forEach((ticket) => {
    const card = document.createElement("div");
    card.className = `ticket-card status-${ticket.status}`;

    const header = document.createElement("div");
    header.className = "ticket-header";
    header.innerHTML = `
      <strong>${ticket.ticket_id}</strong>
      <span class="badge ${ticket.status}">${ticket.status}</span>
    `;

    const subject = document.createElement("p");
    subject.textContent = ticket.subject;

    const meta = document.createElement("small");
    meta.textContent = `Priority: ${ticket.priority} | Created: ${new Date(ticket.created_at).toLocaleString()}`;

    card.appendChild(header);
    card.appendChild(subject);
    card.appendChild(meta);

    card.onclick = () => loadTicketDetail(ticket.ticket_id);
    ticketList.appendChild(card);
  });
};

const loadTicketDetail = async (ticketId) => {
  const response = await fetch(`/api/support/ticket/${ticketId}`);
  if (!response.ok) return;
  const data = await response.json();
  if (data.error) {
    alert(data.error);
    return;
  }

  currentTicket = data.ticket;
  renderTicketDetail(data.ticket);
};

const renderTicketDetail = (ticket) => {
  ticketList.style.display = "none";
  ticketDetail.style.display = "block";

  ticketTitle.textContent = `${ticket.ticket_id}: ${ticket.subject}`;

  ticketInfo.innerHTML = `
    <p><strong>Status:</strong> <span class="badge ${ticket.status}">${ticket.status}</span></p>
    <p><strong>Priority:</strong> ${ticket.priority}</p>
    <p><strong>User:</strong> ${ticket.user_id}</p>
    <p><strong>Created:</strong> ${new Date(ticket.created_at).toLocaleString()}</p>
    <p><strong>Description:</strong></p>
    <p>${ticket.description}</p>
    ${ticket.resolution ? `<p><strong>Resolution:</strong> ${ticket.resolution}</p>` : ""}
  `;

  ticketComments.innerHTML = "<h4>Comments</h4>";
  if (ticket.comments && ticket.comments.length > 0) {
    ticket.comments.forEach((comment) => {
      const commentDiv = document.createElement("div");
      commentDiv.className = "comment";
      commentDiv.innerHTML = `
        <strong>${comment.author}</strong> <small>${new Date(comment.created_at).toLocaleString()}</small>
        <p>${comment.text}</p>
      `;
      ticketComments.appendChild(commentDiv);
    });
  } else {
    ticketComments.innerHTML += "<p class='note'>No comments yet</p>";
  }
};

// ================================
// Support Mode Event Listeners
// ================================

supportModeToggle.addEventListener("change", () => {
  if (supportModeToggle.checked) {
    supportPanel.style.display = "block";
    loadTickets();
  } else {
    supportPanel.style.display = "none";
  }
});

statusFilter.addEventListener("change", () => {
  loadTickets();
});

backToListBtn.addEventListener("click", () => {
  ticketDetail.style.display = "none";
  ticketList.style.display = "block";
  currentTicket = null;
});

commentForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentTicket || !commentInput.value.trim()) return;

  const comment = commentInput.value.trim();

  // In production, this would call /api/support/update endpoint
  // For now, just show the comment locally
  alert(`Comment would be added to ${currentTicket.ticket_id}: ${comment}`);
  commentInput.value = "";

  // Reload ticket to show new comment
  // await loadTicketDetail(currentTicket.ticket_id);
});

createTicketBtn.addEventListener("click", () => {
  const subject = prompt("Ticket subject:");
  if (!subject) return;

  const description = prompt("Problem description:");
  if (!description) return;

  alert(`New ticket would be created:\nSubject: ${subject}\nDescription: ${description}`);
  // In production, call API to create ticket and reload list
});

// ================================
// Initialization
// ================================

const init = async () => {
  await fetchConfig();
  await updateProviderFields();
  fetchTools();
  fetchRagStatus();
};

init();
