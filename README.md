# Foundry Hosted Agent — LangGraph + Cosmos DB Short-Term Memory

> **Branch**: `feature/cosmosdb-short-memory`

A **LangGraph ReAct agent** deployed as a **Hosted Agent** on Microsoft Foundry, with **persistent short-term memory** backed by Azure Cosmos DB. Conversations survive server restarts and can be resumed by referencing the same thread ID.

### Executive Summary — Memory on Hosted Agents

The SDK's `FoundryCheckpointSaver` is **not yet available** in `azure-ai-agentserver-langgraph` (tested up to v1.0.0b15). As a workaround, we use `langgraph-checkpoint-cosmosdb` (CosmosDBSaver) to persist LangGraph state directly in Cosmos DB — with vendored patches that fix severe performance issues (40-60s → <0.5s per checkpoint retrieval).

Conversation threading via `conversation.id` works **locally** (the agentserver maps it to LangGraph's `thread_id`). However, the **published Hosted Agent endpoint is stateless** and rejects the `conversation` field. The project-scoped `/responses` endpoint with `agent_reference` is not yet available. The Foundry **portal playground** does support multi-turn conversations through its own internal BFF (`/nextgen/api/agentchatcompletions`), which manages `threadId` server-side — but this is not a public API.

Bottom line: the Cosmos DB checkpointer is **production-ready** and will work end-to-end as soon as the platform exposes a stateful public endpoint.

## How It Works

```
┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│  Client   │───>│  Agent Server │───>│  Azure OpenAI  │    │  Cosmos DB   │
│  (curl)   │    │  (port 8088)  │    │  (gpt-4.1)     │    │  (checkpts)  │
└──────────┘    └──────┬───────┘    └────────────────┘    └──────┬───────┘
                       │                                         │
                       │  conversation.id ──> thread_id          │
                       │  LangGraph saves state ────────────────>│
                       │  LangGraph loads state <────────────────│
                       │                                         │
```

1. Client sends a message with `"conversation": {"id": "my-thread"}`
2. The agentserver maps `conversation.id` → LangGraph `thread_id`
3. LangGraph checks Cosmos DB for existing checkpoints for that thread
4. The agent gets the full conversation history from the checkpoint
5. After responding, LangGraph saves the new state to Cosmos DB

## Quick Start

### 1. Configure

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
COSMOSDB_ENDPOINT=https://<cosmos-account>.documents.azure.com:443/
COSMOSDB_KEY=<your-cosmos-key>
```

### 2. Install & Run

```bash
uv add -r requirements.txt --prerelease=allow
uv run main.py
```

### 3. Test

```bash
# Start a conversation (thread: "demo")
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hi, my name is Carlos", "stream": false, "conversation": {"id": "demo"}}'

# Recall memory (same thread)
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is my name?", "stream": false, "conversation": {"id": "demo"}}'
# → "Your name is Carlos."
```

### 4. Run the demo

```bash
./demo.sh
```

## Conversation Threading

The key to persistent memory is the **`conversation.id`** field in the request body. It maps to LangGraph's `thread_id`, which the checkpointer uses to store/retrieve state.

### Request Format

```json
{
  "input": "Your message here",
  "stream": false,
  "conversation": {
    "id": "unique-thread-id"
  }
}
```

### Thread Behavior

| Scenario | Result |
|---|---|
| Same `conversation.id` | Agent remembers previous messages |
| Different `conversation.id` | Fresh conversation, no shared memory |
| No `conversation.id` | Auto-generated ID per request (no memory) |
| Server restart + same `conversation.id` | Memory restored from Cosmos DB |

### Example: Multi-Thread

```bash
# Thread 1: Alice
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"I am Alice from Contoso","stream":false,"conversation":{"id":"alice-thread"}}'

# Thread 2: Bob (separate memory)
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"Do you know Alice?","stream":false,"conversation":{"id":"bob-thread"}}'
# → "I don't have information about Alice..."

# Thread 1: Alice still remembered
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input":"Where do I work?","stream":false,"conversation":{"id":"alice-thread"}}'
# → "You work at Contoso."
```

## Architecture

### Cosmos DB Structure

The checkpointer stores data in Cosmos DB:
- **Database**: `agent-memory`
- **Container**: `checkpoints`
- **Partition key**: `/partition_key`

Each checkpoint is stored as a document with:
```
ID format: checkpoint$<thread_id>$<namespace>$<checkpoint_id>
```

Writes (intermediate state) use:
```
ID format: writes$<thread_id>$<namespace>$<checkpoint_id>$<task_id>$<idx>
```

### Inspecting Cosmos DB

```python
from langgraph_checkpoint_cosmosdb import CosmosDBSaver

saver = CosmosDBSaver("agent-memory", "checkpoints")
items = list(saver.container.read_all_items())
print(f"Total checkpoints: {len(items)}")

# List threads
threads = set()
for item in items:
    parts = item["id"].split("$")
    if len(parts) >= 2:
        threads.add(parts[1])
print(f"Active threads: {threads}")
```

## Performance Patches

The `langgraph-checkpoint-cosmosdb` library (v0.2.5) has known performance issues with inefficient Cosmos DB queries. This project includes a vendored, patched version in the `patches/` directory.

### What was changed

The patches are in [patches/cosmosdbSaver.py](patches/cosmosdbSaver.py). Here's a diff summary:

#### 1. `_get_checkpoint_key` — Find latest checkpoint for a thread

**Before** (original library):
```python
# Fetches ALL documents in the partition, then finds max in Python
query = "SELECT * FROM c WHERE c.partition_key=@partition_key"
all_keys = list(container.query_items(query=query, parameters=parameters,
    enable_cross_partition_query=True))
latest_key = max(all_keys, key=lambda k: ...)
```

**After** (patched):
```python
# Single document, sorted by Cosmos DB, partition-scoped
query = "SELECT TOP 1 c.id FROM c WHERE c.partition_key=@partition_key 
         AND IS_DEFINED(c.checkpoint) ORDER BY c.id DESC"
items = list(container.query_items(query=query, parameters=parameters,
    partition_key=partition_key))
```

**Impact**: from O(n) documents transferred + Python sort → 1 document, server-side sort.

#### 2. `get_tuple` — Read a specific checkpoint

**Before**:
```python
# Full query with cross-partition scan
query = "SELECT * FROM c WHERE c.partition_key=@pk AND c.id=@key"
items = list(self.container.query_items(query=query, parameters=parameters,
    enable_cross_partition_query=True))
```

**After**:
```python
# Direct point read (fastest possible Cosmos DB operation)
checkpoint_data = self.container.read_item(item=checkpoint_key, 
    partition_key=partition_key)
```

**Impact**: point read is ~2ms vs ~50-200ms for a cross-partition query.

#### 3. `_load_pending_writes` — Load intermediate state

**Before**:
```python
# Cross-partition query (scans all partitions)
writes = list(self.container.query_items(query=query, parameters=parameters,
    enable_cross_partition_query=True))
```

**After**:
```python
# Partition-scoped query (only scans the relevant partition)
writes = list(self.container.query_items(query=query, parameters=parameters,
    partition_key=partition_key))
```

**Impact**: eliminates cross-partition fan-out overhead.

#### 4. `list` — List checkpoints for a thread

**Before**:
```python
# Fetches ALL documents, no ordering, no limit
query = "SELECT * FROM c WHERE c.partition_key=@partition_key"
items = list(self.container.query_items(query=query, parameters=parameters,
    enable_cross_partition_query=True))
```

**After**:
```python
# Server-side TOP N + ORDER BY, partition-scoped
top_clause = f"TOP {limit}" if limit else ""
query = f"SELECT {top_clause} * FROM c WHERE c.partition_key=@partition_key 
         AND IS_DEFINED(c.checkpoint) ORDER BY c.id DESC"
items = list(self.container.query_items(query=query, parameters=parameters,
    partition_key=partition_key))
```

**Impact**: reduces data transfer and eliminates client-side filtering.

### Performance Results

| Operation | Before | After |
|---|---|---|
| Checkpoint retrieval (get_tuple) | 40-60s | **< 0.5s** |
| End-to-end response with memory | 60s+ | **1.5-4s** (model latency) |

The bottleneck shifted from Cosmos DB queries to model inference time.

### Why these issues exist

The library was ported from a DynamoDB implementation. Key differences:
- DynamoDB uses `Scan` operations that are inherently partition-aware
- Cosmos DB's `enable_cross_partition_query=True` causes fan-out across ALL partitions
- Cosmos DB supports `ORDER BY` and `TOP` server-side, but the library did sorting in Python
- Cosmos DB has `read_item()` for O(1) point reads, but the library used queries for known IDs

## Multi-Tenant Strategy

A single Cosmos DB (serverless) can serve multiple agents and tenants efficiently. Recommended approach: **one container per agent**.

```
Cosmos DB: hosted-agents-cosmos (serverless)
└── Database: agent-memory
    ├── Container: sales-agent-checkpoints      ← Agent A
    ├── Container: support-agent-checkpoints    ← Agent B
    └── Container: onboarding-assistant         ← Agent C
```

Each hosted agent gets its own `AGENT_CONTAINER_NAME` env var:

```bash
az cognitiveservices agent create ... \
  --env "COSMOSDB_ENDPOINT=https://hosted-agents-cosmos.documents.azure.com:443/" \
        "AGENT_CONTAINER_NAME=sales-agent-checkpoints"
```

| Approach | Isolation | Cost | Complexity |
|---|---|---|---|
| Shared container, prefixed thread IDs | Soft (code-level) | Minimal | None |
| **Container per agent** (recommended) | **Hard (data-level)** | **Minimal (serverless)** | **1 env var** |
| Database per tenant | Full (RBAC-level) | Minimal (serverless) | Database management |

## Checkpointer Selection

The agent auto-selects the checkpointer based on env vars:

```python
if os.environ.get("COSMOSDB_ENDPOINT"):
    # Persistent memory in Cosmos DB
    checkpointer = CosmosDBSaver(database_name="agent-memory", container_name="checkpoints")
else:
    # In-memory (lost on restart)
    checkpointer = MemorySaver()
```

## Project Structure

```
.
├── main.py                 # Agent with Cosmos DB checkpointer
├── demo.sh                 # Interactive demo script
├── patches/                # Vendored & patched Cosmos DB checkpointer
│   ├── __init__.py
│   ├── cosmosdbSaver.py    # Patched: optimized queries (see Performance Patches)
│   └── cosmosSerializer.py # Serializer dependency
├── requirements.txt        # Dependencies (includes langgraph-checkpoint-cosmosdb)
├── Dockerfile              # Container for hosted deployment
├── agent.yaml              # Agent metadata (name: ReactAgentCosmosMemory)
├── .dockerignore            
├── .env                    # Local config (not committed)
└── .github/workflows/
    └── deploy.yml          # CI/CD pipeline
```

## Deploying as Hosted Agent

### Deploy with Managed Identity (no secrets)

The recommended approach uses Managed Identity for Cosmos DB access — no API keys needed:

```bash
az cognitiveservices agent create \
  --account-name hosted-agents-foundry \
  --project-name hosted-agents \
  --name ReactAgentCosmosMemory \
  --image "hostedagentsregistry.azurecr.io/foundry-tools-react-agent:cosmos" \
  --cpu 1 --memory 2Gi \
  --protocol responses --protocol-version v1 \
  --env "AZURE_OPENAI_ENDPOINT=https://hosted-agents-foundry.services.ai.azure.com/" \
        "OPENAI_API_VERSION=2025-03-01-preview" \
        "AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1" \
        "COSMOSDB_ENDPOINT=https://hosted-agents-cosmos.documents.azure.com:443/"
```

The `CosmosDBSaver` detects that `COSMOSDB_KEY` is absent and uses `DefaultAzureCredential`, which automatically picks up the hosted agent's Managed Identity.

### Creating a New Version

The CLI doesn't have a `--version` flag. To create a new version, push the same code with a **different image tag** — the platform auto-increments the version number:

```bash
# Build with a new tag
az acr build --registry hostedagentsregistry \
  --image foundry-tools-react-agent:cosmos-v2 \
  --file Dockerfile .

# Create version 2 (auto-detected because the image tag changed)
# Use --no-start to create without deploying
az cognitiveservices agent create \
  --account-name hosted-agents-foundry \
  --project-name hosted-agents \
  --name ReactAgentCosmosMemory \
  --image "hostedagentsregistry.azurecr.io/foundry-tools-react-agent:cosmos-v2" \
  --cpu 1 --memory 2Gi \
  --protocol responses --protocol-version v1 \
  --env "AZURE_OPENAI_ENDPOINT=https://hosted-agents-foundry.services.ai.azure.com/" \
        "OPENAI_API_VERSION=2025-03-01-preview" \
        "AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1" \
        "COSMOSDB_ENDPOINT=https://hosted-agents-cosmos.documents.azure.com:443/" \
  --no-start
```

> **Gotcha**: If you use the same image tag, the CLI returns `Container for agent X version 1 already exists`. You must change the tag to create a new version.

> **Gotcha**: `--env` with URLs containing `/` can confuse the CLI's space-separated parsing. Always quote each `key=value` pair individually.

### Publishing the Agent

After deploying, publish the agent in the Foundry portal to get a stable endpoint with its own Entra ID identity. Once published, the agent gets:

- A **dedicated Entra ID identity** (separate from the project MI)
- A **stable API endpoint** at:
  ```
  https://<account>.services.ai.azure.com/api/projects/<project>/applications/<agent-name>/protocols/openai/responses?api-version=2025-11-15-preview
  ```

### RBAC for the Published Agent

When you publish an agent, Foundry creates a new identity. You need to grant it access to Cosmos DB.

#### 1. Find the agent's identity

```bash
SUB_ID="<your-subscription-id>"
ACCT="hosted-agents-foundry"
PROJECT="hosted-agents"
AGENT="ReactAgentCosmosMemory"

az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/rg-hosted-agents/providers/Microsoft.CognitiveServices/accounts/$ACCT/projects/$PROJECT/applications/$AGENT?api-version=2025-10-01-preview" \
  --query "properties.defaultInstanceIdentity.{principalId:principalId, clientId:clientId}" \
  -o json
```

Look for the `clientId` field — that's the SP's Object ID for Cosmos DB RBAC.

#### 2. Grant Cosmos DB access

```bash
AGENT_PRINCIPAL_ID="<clientId from above>"

az cosmosdb sql role assignment create \
  --account-name hosted-agents-cosmos \
  --resource-group rg-hosted-agents \
  --principal-id "$AGENT_PRINCIPAL_ID" \
  --role-definition-id "00000000-0000-0000-0000-000000000002" \
  --scope "/subscriptions/$SUB_ID/resourceGroups/rg-hosted-agents/providers/Microsoft.DocumentDB/databaseAccounts/hosted-agents-cosmos"
```

> **Note**: The `principalId` from `agentIdentityBlueprint` may be of type `Application` and rejected by Cosmos DB. Use the `clientId` from `defaultInstanceIdentity` instead — it resolves to a `ServiceIdentity` SP that Cosmos DB accepts.

#### 3. Also grant the project MI (for unpublished/pre-publish testing)

```bash
PROJECT_MI=$(az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/rg-hosted-agents/providers/Microsoft.CognitiveServices/accounts/$ACCT/projects/$PROJECT?api-version=2025-10-01-preview" \
  --query "identity.principalId" -o tsv)

az cosmosdb sql role assignment create \
  --account-name hosted-agents-cosmos \
  --resource-group rg-hosted-agents \
  --principal-id "$PROJECT_MI" \
  --role-definition-id "00000000-0000-0000-0000-000000000002" \
  --scope "/subscriptions/$SUB_ID/resourceGroups/rg-hosted-agents/providers/Microsoft.DocumentDB/databaseAccounts/hosted-agents-cosmos"
```

### Invoking the Published Agent

The published endpoint uses `https://ai.azure.com` as the token audience (not `cognitiveservices.azure.com`):

```bash
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

curl -s "https://hosted-agents-foundry.services.ai.azure.com/api/projects/hosted-agents/applications/ReactAgentCosmosMemory/protocols/openai/responses?api-version=2025-11-15-preview" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"input": "Hi, I am Carlos", "stream": false}'
```

> **Important**: Published agent endpoints are **stateless** — they do NOT support the `"conversation"` field. If you send `"conversation": {"id": "..."}` you'll get a `400 invalid_payload` error.

### Published vs Unpublished: Conversation Memory

| | Local (direct) | Published (app endpoint) | Portal Playground |
|---|---|---|---|
| **Endpoint** | `http://localhost:8088/responses` | `/api/projects/{project}/applications/{app}/protocols/openai/responses` | `ai.azure.com/nextgen/api/agentchatcompletions` (internal BFF) |
| **`conversation.id` support** | **Yes** | **No** (stateless, returns `400 invalid_payload`) | **Yes** (managed via internal `threadId`) |
| **Memory via Cosmos DB checkpointer** | **Yes** (thread per `conversation.id`) | **No** (each request is independent) | **Yes** (portal manages thread lifecycle) |
| **Identity** | User credentials / `.env` keys | Dedicated agent MI | User session |
| **Use case** | Development, testing, demos | Production APIs, M365 integration | Manual testing in browser |

> **Known limitation (March 2026)**: The project-scoped `/responses` endpoint with `agent_reference` returns `404 NotFound` — it is not yet publicly available. The `/conversations/{id}/responses` path exists but rejects standard token authentication. The only ways to test conversation threading are: **(1)** locally via `uv run main.py`, or **(2)** via the Foundry portal playground which uses an internal BFF.

### When to use each

**Use local testing when**:
- You need conversation threading with `conversation.id`
- You're developing and debugging memory behavior
- Demo/testing with `./demo.sh`

**Use the published endpoint when**:
- You need a stable, versioned API endpoint
- You're integrating with Microsoft 365 Copilot or Teams
- Each request is self-contained (no multi-turn needed via API)

**Use the portal playground when**:
- You want to test multi-turn conversations with a deployed agent
- The portal manages the conversation context internally via its own BFF

> **Note**: The Foundry playground supports multi-turn conversations with published agents — it manages the conversation context internally through `/nextgen/api/agentchatcompletions`. The stateless limitation only applies to direct REST API calls against the published endpoint.

### Identity Summary

| Identity | When used | How to find |
|---|---|---|
| **Project MI** | Before publishing (testing) | `az rest ... /projects/<name>?... --query identity.principalId` |
| **Agent MI** | After publishing (production) | `az rest ... /applications/<name>?... --query properties.defaultInstanceIdentity.clientId` |
| **GitHub Actions SP** | CI/CD deployment | `az ad sp show --id $AZURE_CLIENT_ID --query id` |

All three need:
- `Azure AI Owner` on the Foundry account (for model access)
- `Cosmos DB Built-in Data Contributor` on the Cosmos DB account (for checkpoints)
- `AcrPull` on the ACR (project MI only, for pulling container images)

## Capability Host (BYOD)

This branch uses a Foundry account (`hosted-agents-foundry`) with a BYOD capability host that stores thread data in your own Azure resources:

```json
{
  "capabilityHostKind": "Agents",
  "enablePublicHostingEnvironment": true,
  "threadStorageConnections": ["cosmos-thread-storage"],
  "vectorStoreConnections": ["ai-search"],
  "storageConnections": ["blob-storage"]
}
```

Resources in `rg-hosted-agents`:
| Resource | Name | Purpose |
|---|---|---|
| Cosmos DB | `hosted-agents-cosmos` | Thread storage + LangGraph checkpoints |
| Storage Account | `hostedagentssa01` | File storage |
| AI Search | `hosted-agents-search01` | Vector store |
| App Insights | `hosted-agents-appinsights` | Observability |

## References

- [LangChain Short-Term Memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- [LangGraph Persistence & Checkpointers](https://docs.langchain.com/oss/python/langgraph/persistence#checkpointer-libraries)
- [langgraph-checkpoint-cosmosdb on PyPI](https://pypi.org/project/langgraph-checkpoint-cosmosdb/)
- [Capability Hosts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/capability-hosts)
- [Hosted Agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
