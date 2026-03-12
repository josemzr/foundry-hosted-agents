#!/bin/bash
# Setup APIM as reverse proxy for per-user memory scoping.
# Run AFTER the APIM resource has been created.
#
# Prerequisites:
#   - APIM: hosted-agents-apim (Standard) in rg-hosted-agents
#   - Hosted Agent published at the backend URL below
#
# Usage: ./scripts/setup_apim_proxy.sh

set -e

APIM_NAME="hosted-agents-apim2"
RG="rg-hosted-agents"
SUB="ce5ba768-f1dc-422c-9e9d-e6e57edb1d4b"
TENANT_ID="1c69fedf-9baf-480d-a78a-574f99039a4d"
BACKEND_URL="https://hosted-agents-foundry.services.ai.azure.com/api/projects/hosted-agents/applications/ReactAgentCosmosMemory/protocols/openai"
API_ID="agent-memory"

echo "=== Step 1: Create API ==="
echo "🔧 az apim api create --service-name $APIM_NAME --resource-group $RG --api-id $API_ID ..."
az apim api create \
  --service-name "$APIM_NAME" \
  --resource-group "$RG" \
  --api-id "$API_ID" \
  --display-name "Agent Memory API" \
  --path "agent" \
  --protocols https \
  --service-url "$BACKEND_URL" \
  --subscription-required false \
  --subscription "$SUB"
echo "✅ API created"

echo ""
echo "=== Step 2: Create POST /responses operation ==="
echo "🔧 az apim api operation create ... --url-template /responses"
az apim api operation create \
  --service-name "$APIM_NAME" \
  --resource-group "$RG" \
  --api-id "$API_ID" \
  --operation-id responses \
  --display-name "Invoke Agent" \
  --method POST \
  --url-template "/responses" \
  --subscription "$SUB"
echo "✅ Operation created"

echo ""
echo "=== Step 3: Apply inbound policy ==="
echo "🔧 Applying policy from scripts/apim-policy.xml via REST API"

# Replace TENANT_ID placeholder in policy
POLICY_FILE="scripts/apim-policy.xml"
POLICY_CONTENT=$(sed "s/{{TENANT_ID}}/$TENANT_ID/g" "$POLICY_FILE")

# Use REST API since az apim cli doesn't have policy commands
POLICY_URL="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/service/$APIM_NAME/apis/$API_ID/operations/responses/policies/policy?api-version=2022-08-01"
echo "🔧 PUT $POLICY_URL"

az rest --method put --url "$POLICY_URL" \
  --body "{\"properties\":{\"format\":\"xml\",\"value\":$(echo "$POLICY_CONTENT" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}}"
echo "✅ Policy applied"

echo ""
echo "=== Done ==="
GATEWAY_URL=$(az apim show --name "$APIM_NAME" --resource-group "$RG" --subscription "$SUB" --query "gatewayUrl" -o tsv 2>/dev/null)
echo ""
echo "APIM Gateway: $GATEWAY_URL"
echo "Agent endpoint: $GATEWAY_URL/agent/responses"
echo ""
echo "Test with:"
echo "  TOKEN=\$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"
echo "  curl -s \$GATEWAY_URL/agent/responses -H 'Authorization: Bearer \$TOKEN' -H 'Content-Type: application/json' -d '{\"input\":\"Hello!\",\"stream\":false}'"
