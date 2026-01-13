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

let messages = [];
let defaultConfig = {};
let isHfKeyOverridden = false;

const showMessage = (role, content) => {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;
  const roleLabel = document.createElement("div");
  roleLabel.className = "role";
  roleLabel.textContent = role === "assistant" ? "assistant" : "you";
  const body = document.createElement("div");
  body.textContent = content;
  wrapper.appendChild(roleLabel);
  wrapper.appendChild(body);
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
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

  // Auto-load Ollama models on startup if Ollama is selected
  if (providerSelect.value === "ollama") {
    await loadOllamaModels();
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

  if (data.tool_results?.length) {
    const toolSummary = data.tool_results
      .map((item) => `${item.name}: ${JSON.stringify(item.result).slice(0, 200)}`)
      .join("\n");
    showMessage("assistant", `Tool results:\n${toolSummary}`);
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
});

clearToolResultBtn.addEventListener("click", () => {
  toolResult.textContent = "";
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

fetchConfig();
fetchTools();
updateProviderFields();
