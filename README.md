# Foundry Hosted Agent — LangGraph + React

A **LangGraph ReAct agent** deployed as a **Hosted Agent** on Microsoft Foundry. This repo includes the agent code, Dockerfile, and a GitHub Actions pipeline that handles the full CI/CD lifecycle.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  GitHub      │────>│  Azure Container │────>│  Microsoft Foundry   │
│  Actions     │     │  Registry (ACR)  │     │  Hosted Agent        │
│  (CI/CD)     │     │                  │     │  (Container on ACA)  │
└─────────────┘     └──────────────────┘     └──────────┬───────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │  Azure OpenAI      │
                                              │  (gpt-4.1)         │
                                              └───────────────────┘
```

## Prerequisites

| Requirement | Details |
|---|---|
| Azure subscription | With `Microsoft.CognitiveServices` and `Microsoft.MachineLearningServices` resource providers registered |
| Foundry account | Kind: `AIServices`, with SystemAssigned managed identity |
| Foundry project | Under the Foundry account, also with SystemAssigned managed identity |
| Azure Container Registry | Basic SKU or higher |
| Model deployment | `gpt-4.1` (or adjust `AZURE_AI_MODEL_DEPLOYMENT_NAME`) |
| GitHub environment | `copilot` with OIDC federated credentials |

## Quick Start

### 1. Run locally

```bash
# Install dependencies
uv add -r requirements.txt --prerelease=allow

# Create .env file
cat > .env << 'EOF'
AZURE_OPENAI_ENDPOINT=https://<your-foundry-account>.openai.azure.com/
OPENAI_API_VERSION=2025-03-01-preview
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
AZURE_AI_PROJECT_ENDPOINT=https://<your-foundry-account>.services.ai.azure.com/api/projects/<your-project>
EOF

# Run the agent
uv run main.py

# Test it
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
  -d '{"input": "Hello!", "stream": false}'
```

### 2. Deploy to Azure

Push to `main` to trigger the GitHub Actions pipeline, or run it manually via `workflow_dispatch`.

## Project Structure

```
.
├── main.py                 # Agent code (LangGraph + Foundry hosting adapter)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image definition
├── agent.yaml              # Agent metadata for Foundry
├── .dockerignore           # Excludes .venv, .env, .git from builds
├── .env                    # Local env vars (not committed)
└── .github/
    └── workflows/
        └── deploy.yml      # CI/CD pipeline
```

## Infrastructure Setup

### Resource Provider Registration

The `Microsoft.MachineLearningServices` provider **must** be registered in your subscription — Foundry uses AML internally for the managed hosting environment:

```bash
az provider register --namespace Microsoft.MachineLearningServices
# Wait until Registered:
az provider show --namespace Microsoft.MachineLearningServices --query registrationState -o tsv
```

### Capability Host

A **capability host** at the account level is required for hosted agents. Key points:

- Use `api-version=2025-10-01-preview` (not `2025-06-01`)
- Set `enablePublicHostingEnvironment: true` directly in `properties` (not nested)
- Only **one** capability host per scope — creating a second gives a 409 Conflict
- Capability hosts **cannot be updated** — delete and recreate to change configuration
- Only the **account-level** capability host is required (project-level is optional)

```bash
az rest --method put \
  --url "https://management.azure.com/subscriptions/{subId}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/capabilityHosts/accountcaphost?api-version=2025-10-01-preview" \
  --headers "content-type=application/json" \
  --body '{"properties":{"capabilityHostKind":"Agents","enablePublicHostingEnvironment":true}}'
```

### RBAC Requirements

Three identities need roles:

#### 1. Project Managed Identity (runtime identity for the container)

| Role | Scope | Why |
|---|---|---|
| `AcrPull` | ACR | Pull container images |
| `Azure AI Owner` | Foundry account | `Microsoft.CognitiveServices/*` data action (covers `AIServices/agents/write`) |
| `Azure AI Owner` | Foundry project | Same as above, at project scope |

#### 2. GitHub Actions Service Principal (deploys the agent)

| Role | Scope | Why |
|---|---|---|
| `Contributor` | Resource group | Create/manage resources |
| `Azure AI Owner` | Foundry account + project | `AIServices/agents/write` to call `az cognitiveservices agent create` |

#### 3. Your user (for local dev / portal access)

| Role | Scope | Why |
|---|---|---|
| `Azure AI Owner` or `Cognitive Services User` | Foundry account | Access the playground, invoke agents |

> **Note:** `Azure AI Developer` does NOT have `AIServices/agents/write`. You need `Azure AI Owner` (which has `Microsoft.CognitiveServices/*`).

### Policy Exemptions

If your subscription has restrictive policies from management groups, create permanent exemptions (type: Waiver) on the resource group:

```bash
az policy exemption create \
  --name "exempt-<policy>" \
  --exemption-category Waiver \
  --policy-assignment "<policy-assignment-id>" \
  --scope "/subscriptions/{subId}/resourceGroups/{rg}"
```

## GitHub Actions Variables

Configure these in the `copilot` environment:

| Variable | Description |
|---|---|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_CLIENT_ID` | App registration client ID (with federated OIDC) |
| `AZURE_TENANT_ID` | Azure AD tenant ID |

## CI/CD Pipeline

The pipeline ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)) does the following:

1. **Build & push** container image to ACR using `az acr build`
2. **Grant AcrPull** to the project managed identity on ACR
3. **Grant Azure AI Owner** to the project managed identity on account + project
4. **Grant Azure AI Owner** to the GitHub Actions SP on account + project
5. **Ensure Capability Host** exists with `enablePublicHostingEnvironment: true`
6. **Wait 30s** for RBAC propagation
7. **Deploy** the hosted agent with `az cognitiveservices agent create` (with retry)

Each `agent create` call creates a **new version** — no need to delete previous versions.

## Dockerfile Notes

```dockerfile
# Pre-release SDK needs pip upgrade first to handle beta versions
RUN pip install --upgrade pip && \
    pip install --pre azure-ai-agentserver-langgraph==1.0.0b15 && \
    pip install -r requirements.txt
```

- Use `--pre` only for the azure package (applying `--pre` globally causes `InvalidVersion` errors with some OpenTelemetry packages)
- Always include a `.dockerignore` to exclude `.venv`, `.env`, `.git`
- The image runs on `linux/amd64` in Foundry — if building locally on Apple Silicon, use `docker build --platform linux/amd64`

## Troubleshooting

### Agent stuck in "Starting" state

| Cause | Fix |
|---|---|
| `Microsoft.MachineLearningServices` not registered | `az provider register --namespace Microsoft.MachineLearningServices` |
| Capability host without `enablePublicHostingEnvironment` | Delete and recreate with `enablePublicHostingEnvironment: true` |
| Capability host using wrong API version | Use `api-version=2025-10-01-preview` |
| ACR pull failure (no AcrPull role) | Assign `AcrPull` to the **project** managed identity |

### PermissionDenied errors

| Error | Fix |
|---|---|
| `AIServices/agents/write` for SP | Assign `Azure AI Owner` (not `Azure AI Developer`) |
| `Principal does not have access to API/Operation` | Assign `Azure AI Owner` to the **project** MI at both account and project scope, then stop/start the agent |
| Graph API query failed warning | Use `--assignee-object-id` and `--assignee-principal-type ServicePrincipal` |

### Managed environment provisioning timeout

Delete all deployments, delete the agent, delete the capability host, verify resource provider registration, then recreate everything:

```bash
# Delete deployments
az cognitiveservices agent delete-deployment --account-name $ACCOUNT --project-name $PROJECT --name $AGENT --agent-version $VERSION

# Delete agent
az cognitiveservices agent delete --account-name $ACCOUNT --project-name $PROJECT --name $AGENT

# Delete capability host
az rest --method delete --url "https://management.azure.com/subscriptions/{subId}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/capabilityHosts/accountcaphost?api-version=2025-10-01-preview"
```

### Container logs

Stream console logs from a running agent:

```bash
curl -N "https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/versions/{version}/containers/default:logstream?kind=console&tail=100&api-version=2025-11-15-preview" \
  -H "Authorization: Bearer $(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"
```

### DOCKER_HOST conflict (Podman vs Docker Desktop)

If you see errors referencing the Podman socket:
```bash
unset DOCKER_HOST
```

## References

- [Hosted Agents documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Capability Hosts documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/capability-hosts)
- [Foundry Permissions](https://aka.ms/FoundryPermissions)
- [Foundry samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents)
- [Deploy guide (Arnaud Tincelin)](https://medium.com/@arnaud.tincelin/deploy-hosted-agents-on-microsoft-foundry-complete-guide-0de13e4f835f)
- [Reference Bicep template](https://github.com/arnaud-tincelin/MicrosoftFoundryHostedAgent/blob/master/infra/main.bicep)
