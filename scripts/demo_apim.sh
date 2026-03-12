#!/bin/bash
# Demo: Multi-user memory isolation via APIM (production flow).
# APIM extracts the OID from the JWT token and injects [user_id:{oid}] automatically.
# Each caller gets their own isolated memory scope based on their Entra ID identity.
#
# Prerequisites:
#   - APIM configured with setup_apim_proxy.sh
#   - LongTermMemoryAgent deployed and running
#   - az login (for token acquisition)
#
# Note: Since we're using the same az login identity, all requests share the same OID.
# In production, different users would have different tokens with different OIDs.

set -e

APIM_URL="https://hosted-agents-apim2.azure-api.net/agent/responses"

extract_text() {
    python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'output' in d:
    for o in reversed(d['output']):
        if o.get('type') == 'message':
            for c in o.get('content', []):
                if c.get('type') == 'output_text':
                    print(c['text'])
                    sys.exit(0)
print(json.dumps(d, indent=2))
" 2>/dev/null
}

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  APIM Multi-User Memory Demo (Production Flow)             ║"
echo "║  APIM extracts OID from JWT → per-user memory isolation    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Get token
echo "🔑 Acquiring Entra ID token..."
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
USER_OID=$(echo "$TOKEN" | python3 -c "import sys,json,base64; t=sys.stdin.read().split('.')[1]; t+='='*(-len(t)%4); print(json.loads(base64.urlsafe_b64decode(t)).get('oid','unknown'))" 2>/dev/null)
echo "   User OID: $USER_OID"
echo "   APIM URL: $APIM_URL"
echo ""

read -p "Press Enter to start..."
echo ""

# --- Step 1: Share info via APIM ---
echo "━━━ Step 1: Share personal info via APIM ━━━"
echo ""
echo "USER: Hi! I am Carlos from Fabrikam and I love tea."
echo "      (APIM injects [user_id:$USER_OID] automatically)"
echo ""
RESPONSE=$(curl -s "$APIM_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"Hi! I am Carlos from Fabrikam and I love tea"}]}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Step 2: Recall via APIM ---
echo "━━━ Step 2: Ask what the agent remembers (via APIM) ━━━"
echo ""
echo "USER: What do you remember about me?"
echo "      (Same OID → same memory scope)"
echo ""
RESPONSE=$(curl -s "$APIM_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"What do you remember about me?"}]}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Step 3: Add more info ---
echo "━━━ Step 3: Share more preferences ━━━"
echo ""
echo "USER: I also love hiking and I'm learning Japanese."
echo ""
RESPONSE=$(curl -s "$APIM_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"I also love hiking and I am learning Japanese"}]}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Step 4: Final recall ---
echo "━━━ Step 4: Full recall ━━━"
echo ""
echo "USER: Tell me everything you know about me."
echo ""
RESPONSE=$(curl -s "$APIM_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"role":"user","content":"Tell me everything you know about me"}]}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Demo complete! End-to-end flow:"
echo ""
echo "  Client → APIM (extract OID, inject [user_id:{oid}])"
echo "       → Foundry /openai/v1/responses (with agent_reference)"
echo "       → Hosted Agent (parse [user_id:], scope memory)"
echo "       → Memory Store (isolated per user OID)"
echo ""
echo "  Your OID: $USER_OID"
echo "  All memories stored under scope: $USER_OID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
