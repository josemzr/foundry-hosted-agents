# Foundry Hosted Agent — LangGraph + Microsoft Learn MCP

> **Branch**: `feature/mcp-microsoft-learn`

A **LangGraph ReAct agent** that connects to the **Microsoft Learn MCP server** to search and retrieve documentation. Uses `langchain-mcp-adapters` for native MCP integration without Foundry MCP connections.

## How It Works

```
┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────────┐
│  Client   │───>│  Agent Server │───>│  Azure OpenAI  │    │  Microsoft Learn │
│  (curl)   │    │  (port 8088)  │    │  (gpt-4.1)     │    │  MCP Server      │
└──────────┘    └──────┬───────┘    └────────────────┘    └────────┬─────────┘
                       │                                           │
                       │  LangChain MCP adapter ──────────────────>│
                       │  (streamable HTTP transport)              │
                       │  Tools: search, lookup, etc. <────────────│
                       │                                           │
```

1. On startup, the agent connects to `https://learn.microsoft.com/api/mcp` via streamable HTTP
2. It loads all available tools from the MCP server (search, lookup, etc.)
3. When a user asks a question, the model decides which MCP tools to call
4. Results from Microsoft Learn are incorporated into the response

## Quick Start

### 1. Configure

```bash
cp .env.example .env
# Edit .env with your values
```

Required:
```
AZURE_OPENAI_ENDPOINT=https://<account>.openai.azure.com/
OPENAI_API_VERSION=2025-03-01-preview
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
```

Optional:
```
MCP_SERVER_URL=https://learn.microsoft.com/api/mcp   # default
```

### 2. Install & Run

```bash
uv add -r requirements.txt --prerelease=allow
uv run python main.py
```

### 3. Test

```bash
# Ask about Azure services
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is Azure Container Apps?", "stream": false}'

# Ask about CLI commands
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "How do I create a Foundry hosted agent with az cli?", "stream": false}'
```

## Architecture

The agent uses `langchain-mcp-adapters` `MultiServerMCPClient` with **streamable HTTP transport** to connect to external MCP servers. No Foundry MCP connections or project tool connections needed.

```python
mcp_client = MultiServerMCPClient({
    "microsoft-learn": {
        "transport": "streamable_http",
        "url": "https://learn.microsoft.com/api/mcp",
    }
})
tools = await mcp_client.get_tools()
agent = create_react_agent(model, tools, ...)
```

### Adding More MCP Servers

Add any MCP server by extending the connections dict:

```python
mcp_client = MultiServerMCPClient({
    "microsoft-learn": {
        "transport": "streamable_http",
        "url": "https://learn.microsoft.com/api/mcp",
    },
    "my-custom-server": {
        "transport": "streamable_http",
        "url": "https://my-mcp-server.azurewebsites.net/mcp",
    },
    "local-server": {
        "transport": "stdio",
        "command": "python",
        "args": ["my_mcp_server.py"],
    },
})
```

## Project Structure

```
.
├── main.py              # Agent with MCP integration (async)
├── requirements.txt     # Dependencies
├── Dockerfile
├── agent.yaml
└── .env                 # Local config (not committed)
```

## Key Dependencies

| Package | Purpose |
|---|---|
| `langchain-mcp-adapters` | LangChain native MCP client (streamable HTTP, SSE, stdio, websocket) |
| `azure-ai-agentserver-langgraph` | Hosted Agent server wrapper |
| `langgraph` | Agent graph with `create_react_agent` |

## References

- [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [Microsoft Learn MCP Server](https://github.com/microsoftdocs/mcp)
- [MCP Protocol](https://modelcontextprotocol.io/)

