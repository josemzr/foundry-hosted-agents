# Foundry Hosted Agent — LangGraph + Foundry Long-Term Memory

> **Branch**: `feature/foundry-long-term-memory`

A **LangGraph ReAct agent** with **Foundry Memory Store** integration for **long-term memory** across sessions. The agent remembers user preferences, facts, and conversation context — powered by Microsoft Foundry's managed memory service.

## How It Works

```
┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────────┐
│  Client   │───>│  Agent Server │───>│  Azure OpenAI  │    │  Foundry Memory  │
│  (curl)   │    │  (port 8088)  │    │  (gpt-4.1)     │    │  Store (managed) │
└──────────┘    └──────┬───────┘    └────────────────┘    └────────┬─────────┘
                       │                                           │
                       │  save_memory tool ────────────────────>   │
                       │  search_memory tool <──────────────────   │
                       │  retrieve_memories (per-turn injection)   │
                       │                                           │
```

### Memory Flow

1. **Every turn**: Before calling the model, the agent retrieves relevant memories from the Memory Store and injects them into the system prompt
2. **When user shares info**: The model calls `save_memory` tool to persist facts (name, preferences, etc.)
3. **When user asks to recall**: The model calls `search_memory` tool to find relevant memories
4. **Behind the scenes**: Foundry Memory automatically extracts, consolidates, and resolves conflicts in stored memories using LLM-powered processing

### Memory Types

| Type | What it stores | When to retrieve |
|---|---|---|
| **User profile** | Static facts: name, role, company, preferences, allergies | At conversation start |
| **Chat summary** | Distilled summaries of past conversations | Per-turn, based on current query |

## Quick Start

### 1. Prerequisites

- Azure AI Foundry project with:
  - `gpt-4.1` deployment (chat model)
  - `text-embedding-3-small` deployment (embedding model for memory)
- Memory Store created (see below)
- Python 3.10+

### 2. Create the Memory Store

```bash
export AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
uv run python scripts/create_memory_store.py
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your values
```

Required env vars:
```
AZURE_OPENAI_ENDPOINT=https://<account>.openai.azure.com/
OPENAI_API_VERSION=2025-03-01-preview
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
AZURE_AI_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
```

Optional:
```
MEMORY_STORE_NAME=agent_long_term_memory   # default
MEMORY_SCOPE=default_user                   # default; use user IDs in production
```

### 4. Install & Run

```bash
uv add -r requirements.txt --prerelease=allow
uv run main.py
```

### 5. Test

```bash
# Share some info (agent saves to memory)
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hi! My name is Jose, I work at Microsoft, and I love dark roast coffee.", "stream": false}'

# Ask what it remembers (agent searches memory)
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What do you remember about me?", "stream": false}'
```

### 6. Run the demo

```bash
./demo.sh
```

## Architecture

### Agent Graph

```
START → agent → should_continue? → tools (save_memory / search_memory) → agent → END
                     │
                     └─ END (no tool calls)
```

The agent uses a custom LangGraph `StateGraph`:
- **`call_model` node**: Retrieves relevant memories via `AzureAIMemoryRetriever`, injects them into the system prompt, then calls the model with tools bound
- **`should_continue` edge**: Routes to tool execution if the model made tool calls, otherwise ends
- **`tools` node**: Executes `save_memory` or `search_memory`

### Memory Integration

Built on the official `langchain-azure-ai` integration:

| Component | Purpose |
|---|---|
| `AzureAIMemoryChatMessageHistory` | Session-aware chat history that auto-extracts memories |
| `AzureAIMemoryRetriever` | Retrieves relevant memories (user profile + chat summaries) |
| `save_memory` tool | Agent tool to explicitly persist user information |
| `search_memory` tool | Agent tool to search stored memories |
| `retrieve_memories_for_context` | Per-turn memory injection into the system prompt |

### Scoping

Memory is partitioned by **scope** (user ID). In the default config, all requests use `default_user`. In production, set `MEMORY_SCOPE` per-user:

```python
# Single-user (demo)
MEMORY_SCOPE=default_user

# Multi-user (production)
MEMORY_SCOPE=user_12345
```

## Compatibility Patches

Two patches are applied at runtime for compatibility between `azure-ai-projects` v2.0.0 and `langchain-azure-ai` v1.1.0:

1. **`memory_stores` property alias**: `langchain-azure-ai` checks for `client.memory_stores` but v2.0.0 has it under `client.beta.memory_stores`
2. **Preview feature header**: Memory Store API requires `Foundry-Features: MemoryStores=V1Preview` header — added via a custom HTTP policy

## Project Structure

```
.
├── main.py                 # Agent with Foundry Memory integration
├── memory_tools.py         # Memory tools + retriever + patches
├── scripts/
│   └── create_memory_store.py  # One-time setup: create the memory store
├── demo.sh                 # Interactive demo script
├── requirements.txt
├── Dockerfile
├── agent.yaml
└── .env                    # Local config (not committed)
```

## Foundry Memory vs Cosmos DB Short-Term Memory

| | Foundry Memory (this branch) | Cosmos DB Checkpointer (`feature/cosmosdb-short-memory`) |
|---|---|---|
| **Type** | Long-term memory | Short-term memory (conversation state) |
| **Persistence** | Across sessions, indefinitely | Per conversation thread |
| **What it stores** | Distilled facts & preferences | Full conversation history + agent state |
| **How it works** | LLM extracts & consolidates memories | Checkpoint serialization |
| **Managed by** | Foundry Memory Store service | Your own Cosmos DB |
| **Scoping** | By user ID (`scope`) | By thread ID |
| **Use case** | "Remember my name is Jose" | "Continue our conversation from earlier" |

These are complementary — you can use both together for a complete memory architecture.

## References

- [Foundry Memory with LangChain/LangGraph](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-memory)
- [Memory in Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory)
- [Create and use memory](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage)
- [langchain-azure-ai on PyPI](https://pypi.org/project/langchain-azure-ai/)

## Multi-User Memory Isolation with APIM

This branch includes a **per-user memory scoping** pattern using Azure API Management as a reverse proxy. APIM extracts the user identity from the JWT token and injects it into the request so the agent can scope memories to each individual user.

### The Problem

Hosted Agents don't expose HTTP headers to the container, so the agent can't know who the caller is. Without user identity, all users share the same memory scope.

### The Solution

```
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│  App/Client   │───>│  Azure APIM  │───>│  Hosted Agent    │───>│  Memory Store│
│  (JWT token)  │    │  (extract    │    │  (reads user_id  │    │  (scope per  │
│               │    │   OID →      │    │   from input)    │    │   user)      │
│               │    │   inject)    │    │                  │    │              │
└──────────────┘    └──────────────┘    └──────────────────┘    └──────────────┘
```

1. **APIM** validates the JWT token and extracts the `oid` (Object ID) claim
2. **APIM policy** injects `[user_id:{oid}]` as a prefix in the `input` field
3. **Agent** parses the prefix, sets the memory scope to that user, and removes the prefix before processing
4. **Memory Store** operations (save/search) use the user-specific scope — memories are fully isolated

### How It Works in the Agent

```python
# main.py — extract_user_id()
def extract_user_id(message: str) -> tuple[str, str]:
    match = re.match(r'^\[user_id:([^\]]+)\]\s*', message)
    if match:
        return match.group(1), message[match.end():]
    return MEMORY_SCOPE, message  # fallback to default
```

The `user_id` is propagated to memory tools via thread-local storage (`set_current_user()`), so `save_memory` and `search_memory` automatically use the correct scope.

### APIM Policy

The policy in [scripts/apim-policy.xml](scripts/apim-policy.xml) does three things:
1. Validates the JWT token from Entra ID
2. Extracts the `oid` claim
3. Modifies the request body to inject `[user_id:{oid}]` into the `input` field

### Setup

```bash
# 1. Create APIM (Standard tier) — takes ~30 min
az apim create --name hosted-agents-apim \
  --resource-group rg-hosted-agents \
  --publisher-name "Hosted Agents" \
  --publisher-email "admin@contoso.com" \
  --sku-name Standard --location swedencentral

# 2. Configure API + policy
./scripts/setup_apim_proxy.sh
```

### Testing Locally (Without APIM)

Simulate APIM by manually adding the `[user_id:xxx]` prefix:

```bash
# Alice shares info
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"[user_id:alice] I am Alice, allergic to shellfish","stream":false}'

# Bob shares info
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"[user_id:bob] I am Bob, I love hiking","stream":false}'

# Alice asks — only sees her memories
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"[user_id:alice] What do you remember about me?","stream":false}'

# Bob asks — only sees his memories
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"[user_id:bob] What do you remember about me?","stream":false}'
```

Run the full demo:
```bash
./scripts/demo_multi_user.sh
```

### Testing via APIM (Production)

APIM proxies to the hosted agent via the **`/openai/v1/responses`** endpoint with `agent_reference`. The policy automatically injects the caller's OID and the agent reference.

```bash
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Share info — APIM extracts your OID and injects [user_id:{oid}] + agent_reference
curl -s https://hosted-agents-apim2.azure-api.net/agent/responses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"Hi I am Carlos from Fabrikam and I love tea"}]}'

# Recall — same OID, same user scope
curl -s https://hosted-agents-apim2.azure-api.net/agent/responses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"What do you remember about me?"}]}'
```

> **Note**: The `input` field uses the array format `[{"role":"user","content":"..."}]` (OpenAI Responses API format), not a plain string. The `agent_reference` is auto-injected by the APIM policy.

### Invoking Hosted Agents — REST vs SDK

| Method | Endpoint | Token Audience | Works? |
|---|---|---|---|
| **SDK** (`openai_client.responses.create`) | `/openai/v1/responses` with `extra_body={"agent_reference":...}` | `https://cognitiveservices.azure.com` | **Yes** |
| **REST** (curl) | `POST /api/projects/{project}/openai/v1/responses` | `https://ai.azure.com` | **Yes** |
| **APIM** → REST | `POST https://{apim}.azure-api.net/agent/responses` → backend `/openai/v1/responses` | `https://ai.azure.com` | **Yes** |
| Published endpoint | `/applications/{name}/protocols/openai/responses` | `https://ai.azure.com` | **No** (prompt agents only) |

The key discovery: hosted agents are invoked via `/openai/v1/responses` with `agent_reference` in the body, **not** via the `/applications/` published endpoint.

### Memory Isolation Result

```
Memory Store: agent_long_term_memory
├── scope: "f1356774-4df4-..."  → Jose: works at Microsoft, dark roast coffee
├── scope: "alice"              → Alice: works at Contoso, allergic to shellfish
└── scope: "bob"                → Bob: prefers Python, loves hiking
```

### Multi-Tenancy Strategies Comparison

| Strategy | Isolation | How | Cost |
|---|---|---|---|
| Env var `MEMORY_SCOPE` | Shared (all users) | Single scope | Minimal |
| One agent per tenant | Tenant-level | Different env var per deployment | One agent per tenant |
| **APIM + `[user_id:]` prefix** | **User-level** | **OID from JWT → scope** | **One APIM + one agent** |

### Project Structure (with APIM scripts)

```
scripts/
├── create_memory_store.py    # One-time: create the memory store
├── purge_memories.py         # Purge all memories (reset for demos)
├── setup_apim_proxy.sh       # One-time: configure APIM API + policy
├── apim-policy.xml           # APIM inbound policy (JWT → user_id injection)
├── demo_multi_user.sh        # Demo: multi-user isolation (local)
└── demo_apim.sh              # Demo: multi-user isolation via APIM (production)
```

### Purging Memories

Reset the memory store before a demo:

```bash
# Purge all default scopes (default_user, alice, bob, your OID)
uv run python scripts/purge_memories.py

# Purge specific scopes
uv run python scripts/purge_memories.py alice bob custom_user_123
```

## Invoking Hosted Agents — SDK to REST Translation

The official docs show how to invoke hosted agents via the Python SDK, but not via REST. Here's the translation we discovered by intercepting the SDK traffic.

### Python SDK (official)

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

client = AIProjectClient(
    endpoint="https://{account}.services.ai.azure.com/api/projects/{project}",
    credential=DefaultAzureCredential(),
    allow_preview=True,
)
agent = client.agents.get(agent_name="LongTermMemoryAgent")
openai_client = client.get_openai_client()

response = openai_client.responses.create(
    input=[{"role": "user", "content": "Hello!"}],
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)
print(response.output_text)
```

### Equivalent REST (curl)

```bash
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

curl -s "https://{account}.services.ai.azure.com/api/projects/{project}/openai/v1/responses" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "Hello!"}],
    "agent_reference": {"name": "LongTermMemoryAgent", "type": "agent_reference"}
  }'
```

### Key Details

| Parameter | Value |
|---|---|
| **Endpoint path** | `/api/projects/{project}/openai/v1/responses` |
| **Token audience** | `https://ai.azure.com` (NOT `cognitiveservices.azure.com`) |
| **Input format** | Array: `[{"role":"user","content":"..."}]` |
| **Agent routing** | `"agent_reference": {"name": "AgentName", "type": "agent_reference"}` in body |
| **No api-version needed** | The `/openai/v1/` path doesn't require an `api-version` query param |

> **How we found this**: We enabled `DEBUG` logging on the SDK's `openai._base_client` and `httpx` loggers to capture the exact HTTP request the SDK sends. The critical difference from the published endpoint (`/applications/.../protocols/openai/responses`) is that this endpoint uses `/openai/v1/responses` with `agent_reference` in the body.
