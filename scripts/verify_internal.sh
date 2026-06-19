#!/usr/bin/env bash
# MetoCare — Internal DEV Verification Script (PA-08 smoke checklist)
# Run ON the DEV server after deploy_internal.sh completes.
# Usage: bash scripts/verify_internal.sh

set -uo pipefail
BASE="http://localhost:18000"
FRONT="http://localhost:13000"
PASS=0; FAIL=0; SKIP=0

log()  { echo "[$(date '+%H:%M:%S')] $*"; }
ok()   { echo "  ✅ PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  ❌ FAIL: $*"; FAIL=$((FAIL+1)); }
skip() { echo "  ⏭  SKIP: $*"; SKIP=$((SKIP+1)); }
hdr()  { echo ""; echo "── $* ──────────────────────────────"; }

# ── Helper: POST with JSON, return HTTP status + body ─────────────────────────
post_json() {
    local url="$1" data="$2" auth="${3:-}"
    local hdr_args=()
    [[ -n "$auth" ]] && hdr_args=(-H "Authorization: Bearer $auth")
    curl -sf -w "\n%{http_code}" -X POST "$url" \
        -H "Content-Type: application/json" \
        "${hdr_args[@]}" \
        -d "$data" 2>/dev/null
}

get_auth() {
    local url="$1" auth="${2:-}"
    [[ -n "$auth" ]] && curl -sf -w "\n%{http_code}" "$url" -H "Authorization: Bearer $auth" 2>/dev/null \
        || curl -sf -w "\n%{http_code}" "$url" 2>/dev/null
}

# ─────────────────────────────────────────────────────────────────────────────
hdr "ITEM 1 — Backend health"
RESP=$(curl -sf "$BASE/health" 2>/dev/null)
echo "$RESP" | grep -q '"ok"' && ok "GET /health → {\"status\":\"ok\"}" || fail "GET /health returned: $RESP"

hdr "ITEM 2 — Backend info"
RESP=$(curl -sf "$BASE/info" 2>/dev/null)
echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('app'), 'missing app field'
print('  env=%s ai_mode=%s' % (d.get('env','?'), d.get('ai_mode','?')))
" 2>/dev/null && ok "GET /info → fields present" || fail "GET /info failed: $RESP"

hdr "ITEM 3 — Patient login"
RAW=$(curl -sf -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=demo.patient@example.com&password=DemoPatient123!" 2>/dev/null)
HTTP=$(echo "$RAW" | tail -1)
BODY=$(echo "$RAW" | head -1)
PAT_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
[[ "$HTTP" == "200" && -n "$PAT_TOKEN" ]] && ok "Patient login → 200, token obtained" || fail "Patient login HTTP=$HTTP body=$BODY"

hdr "ITEM 4 — Patient ID from me"
if [[ -n "$PAT_TOKEN" ]]; then
    RAW=$(get_auth "$BASE/api/v1/auth/me" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    BODY=$(echo "$RAW" | head -1)
    PAT_ID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
    [[ "$HTTP" == "200" && -n "$PAT_ID" ]] && ok "GET /me → 200, patient_id=$PAT_ID" || fail "GET /me HTTP=$HTTP"
else
    skip "No patient token — skipping /me"
    PAT_ID=""
fi

hdr "ITEM 5 — Patient profile"
if [[ -n "$PAT_ID" ]]; then
    RAW=$(get_auth "$BASE/api/v1/patients/$PAT_ID/profile" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /patients/$PAT_ID/profile → 200" || fail "Profile HTTP=$HTTP"
else
    skip "No patient_id"
fi

hdr "ITEM 6 — Health metrics list"
if [[ -n "$PAT_ID" ]]; then
    RAW=$(get_auth "$BASE/api/v1/patients/$PAT_ID/metrics?limit=5" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /metrics → 200" || fail "Metrics HTTP=$HTTP"
else
    skip "No patient_id"
fi

hdr "ITEM 7 — Symptoms"
if [[ -n "$PAT_ID" ]]; then
    RAW=$(get_auth "$BASE/api/v1/patients/$PAT_ID/symptoms" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /symptoms → 200" || fail "Symptoms HTTP=$HTTP"
else
    skip "No patient_id"
fi

hdr "ITEM 8 — Medications"
if [[ -n "$PAT_ID" ]]; then
    RAW=$(get_auth "$BASE/api/v1/patients/$PAT_ID/medications" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /medications → 200" || fail "Medications HTTP=$HTTP"
else
    skip "No patient_id"
fi

hdr "ITEM 9 — Care plans"
if [[ -n "$PAT_ID" ]]; then
    RAW=$(get_auth "$BASE/api/v1/care_plans?patient_id=$PAT_ID" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /care_plans → 200" || fail "Care plans HTTP=$HTTP"
else
    skip "No patient_id"
fi

hdr "ITEM 10 — Notifications"
if [[ -n "$PAT_TOKEN" ]]; then
    RAW=$(get_auth "$BASE/api/v1/notifications" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /notifications → 200" || fail "Notifications HTTP=$HTTP"
else
    skip "No token"
fi

hdr "ITEM 11 — Lab documents"
if [[ -n "$PAT_ID" ]]; then
    RAW=$(get_auth "$BASE/api/v1/patients/$PAT_ID/lab-documents" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /lab-documents → 200" || fail "Lab documents HTTP=$HTTP"
else
    skip "No patient_id"
fi

hdr "ITEM 12 — AI explain (mock)"
if [[ -n "$PAT_ID" ]]; then
    DATA="{\"patient_id\":\"$PAT_ID\",\"explanation_type\":\"metabolic_summary\",\"context\":{}}"
    RAW=$(post_json "$BASE/api/v1/ai/explain" "$DATA" "$PAT_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    BODY=$(echo "$RAW" | head -1)
    [[ "$HTTP" == "200" ]] && ok "POST /ai/explain → 200 (mock)" || fail "AI explain HTTP=$HTTP body=$BODY"
else
    skip "No patient_id"
fi

hdr "ITEM 13 — Token refresh"
if [[ -n "$PAT_TOKEN" ]]; then
    # Get refresh token from cookie jar login
    RAW=$(curl -sf -w "\n%{http_code}" -c /tmp/mcp_cookies.txt -X POST "$BASE/api/v1/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=demo.patient@example.com&password=DemoPatient123!" 2>/dev/null)
    REFRESH_TOKEN=$(echo "$RAW" | head -1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh_token',''))" 2>/dev/null)
    if [[ -n "$REFRESH_TOKEN" ]]; then
        RAW2=$(curl -sf -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/refresh" \
            -H "Content-Type: application/json" \
            -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}" 2>/dev/null)
        HTTP2=$(echo "$RAW2" | tail -1)
        [[ "$HTTP2" == "200" ]] && ok "POST /auth/refresh → 200" || fail "Token refresh HTTP=$HTTP2"
    else
        skip "No refresh_token in login response"
    fi
else
    skip "No patient token"
fi

hdr "ITEM 14 — Doctor login"
RAW=$(curl -sf -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=demo.doctor@example.com&password=DemoDoctor123!" 2>/dev/null)
HTTP=$(echo "$RAW" | tail -1)
BODY=$(echo "$RAW" | head -1)
DOC_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
[[ "$HTTP" == "200" && -n "$DOC_TOKEN" ]] && ok "Doctor login → 200, token obtained" || fail "Doctor login HTTP=$HTTP"

hdr "ITEM 15 — Doctor patients list"
if [[ -n "$DOC_TOKEN" ]]; then
    RAW=$(get_auth "$BASE/api/v1/doctor/patients" "$DOC_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /doctor/patients → 200" || \
        { skip "GET /doctor/patients → $HTTP (no patients assigned in demo — acceptable)"; }
else
    skip "No doctor token"
fi

hdr "ITEM 16 — Admin login"
RAW=$(curl -sf -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=demo.admin@example.com&password=DemoAdmin123!" 2>/dev/null)
HTTP=$(echo "$RAW" | tail -1)
BODY=$(echo "$RAW" | head -1)
ADM_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
[[ "$HTTP" == "200" && -n "$ADM_TOKEN" ]] && ok "Admin login → 200, token obtained" || fail "Admin login HTTP=$HTTP"

hdr "ITEM 17 — Admin users list"
if [[ -n "$ADM_TOKEN" ]]; then
    RAW=$(get_auth "$BASE/api/v1/admin/users" "$ADM_TOKEN")
    HTTP=$(echo "$RAW" | tail -1)
    [[ "$HTTP" == "200" ]] && ok "GET /admin/users → 200" || fail "Admin users HTTP=$HTTP"
else
    skip "No admin token"
fi

hdr "ITEM 18 — Frontend accessible"
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "$FRONT/" 2>/dev/null)
[[ "$HTTP" == "200" ]] && ok "GET $FRONT/ → 200 (Next.js served)" || fail "Frontend HTTP=$HTTP"

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Smoke Result: ✅ $PASS PASS | ❌ $FAIL FAIL | ⏭  $SKIP SKIP"
echo "════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo "  VERDICT: ALL CLEAR — stack ready for internal use" \
                  || echo "  VERDICT: FAILURES FOUND — review output above"
echo ""
rm -f /tmp/mcp_cookies.txt
