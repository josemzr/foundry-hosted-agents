#!/bin/bash
# Demo: Multi-user memory isolation via [user_id:xxx] prefix.
# Works locally (prefix injected manually) or via APIM (prefix injected from JWT).

set -e

BASE_URL="http://localhost:8088/responses"

extract_text() {
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('output',d)[-1]['content'][0]['text'] if 'output' in d else d)" 2>/dev/null
}

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Multi-User Memory Isolation Demo                           ║"
echo "║  Using [user_id:xxx] prefix for per-user memory scoping     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# --- Alice ---
echo "━━━ Alice: Share personal info ━━━"
echo ""
echo "USER (alice): Hi! My name is Alice, I work at Contoso, and I'm allergic to shellfish."
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"[user_id:alice] Hi! My name is Alice, I work at Contoso, and I am allergic to shellfish.","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Bob ---
echo "━━━ Bob: Share different info ━━━"
echo ""
echo "USER (bob): Hey! I'm Bob, I prefer Python over Java, and I love hiking."
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"[user_id:bob] Hey! I am Bob, I prefer Python over Java, and I love hiking.","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Alice recall ---
echo "━━━ Alice: What do you remember? (should NOT see Bob's info) ━━━"
echo ""
echo "USER (alice): What do you remember about me?"
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"[user_id:alice] What do you remember about me?","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Bob recall ---
echo "━━━ Bob: What do you remember? (should NOT see Alice's info) ━━━"
echo ""
echo "USER (bob): What do you remember about me?"
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"[user_id:bob] What do you remember about me?","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Demo complete! Memory is isolated by user_id scope:"
echo "  • Alice only sees: name, company, allergy"
echo "  • Bob only sees: name, language preference, hobby"
echo "  • No cross-contamination between users"
echo ""
echo "In production, APIM extracts the OID from the JWT token"
echo "and injects [user_id:{oid}] automatically — zero trust."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
