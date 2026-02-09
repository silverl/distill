#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# Distill — Full Setup Script
#
# Checks prerequisites, installs dependencies, starts Postiz,
# creates a test account, and writes the API key to .env.
#
# Usage:
#   ./scripts/setup.sh            # full setup
#   ./scripts/setup.sh --no-docker  # skip Docker/Postiz
#   ./scripts/setup.sh --teardown   # stop Postiz and clean up
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_DIR="$ROOT/docker/postiz"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

# Postiz account defaults
POSTIZ_EMAIL="distill@local.dev"
POSTIZ_PASS="distill123"
POSTIZ_PORT=6100
POSTIZ_HTTPS_PORT=6106
POSTIZ_API_BASE="http://localhost:$POSTIZ_PORT"

# ─── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail()  { echo -e "${RED}[fail]${NC}  $*"; exit 1; }

# ─── Teardown ──────────────────────────────────────────────────
if [[ "${1:-}" == "--teardown" ]]; then
    info "Stopping Postiz stack..."
    (cd "$COMPOSE_DIR" && docker compose down -v 2>/dev/null) || true
    ok "Postiz stack stopped and volumes removed."
    exit 0
fi

SKIP_DOCKER=false
if [[ "${1:-}" == "--no-docker" ]]; then
    SKIP_DOCKER=true
fi

echo ""
echo -e "${BLUE}━━━ Distill Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ─── 1. Check Prerequisites ───────────────────────────────────
info "Checking prerequisites..."

# Python 3.11+
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        ok "Python $PY_VERSION"
    else
        fail "Python 3.11+ required (found $PY_VERSION). Install: brew install python@3.12"
    fi
else
    fail "Python 3 not found. Install: brew install python@3.12"
fi

# uv
if command -v uv &>/dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | head -1)
    ok "uv ($UV_VERSION)"
else
    warn "uv not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv installed"
fi

# Git
if command -v git &>/dev/null; then
    ok "git $(git --version | awk '{print $3}')"
else
    fail "git not found. Install: brew install git"
fi

# Docker (optional)
if [[ "$SKIP_DOCKER" == false ]]; then
    if command -v docker &>/dev/null; then
        ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    else
        fail "Docker not found. Install: brew install --cask docker"
    fi

    if docker compose version &>/dev/null; then
        ok "Docker Compose $(docker compose version --short 2>/dev/null)"
    else
        fail "Docker Compose not found. Update Docker Desktop."
    fi

    if ! docker info &>/dev/null; then
        fail "Docker daemon not running. Start Docker Desktop first."
    fi
fi

echo ""

# ─── 2. Install Python Dependencies ───────────────────────────
info "Installing Python dependencies..."
uv sync --quiet --directory "$ROOT"
ok "Python dependencies installed"
echo ""

# ─── 3. Create .env if missing ─────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating .env from .env.example..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok "Created .env"
else
    ok ".env already exists"
fi
echo ""

# ─── 4. Start Postiz Stack ─────────────────────────────────────
if [[ "$SKIP_DOCKER" == true ]]; then
    warn "Skipping Docker/Postiz setup (--no-docker)"
    echo ""
    echo -e "${GREEN}━━━ Setup Complete (no Docker) ━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Run tests:    uv run pytest tests/ -x -q"
    echo "  Run CLI:      uv run python -m distill --help"
    echo ""
    exit 0
fi

# Check if already running
if curl -sf "http://localhost:$POSTIZ_PORT/" &>/dev/null; then
    ok "Postiz already running on port $POSTIZ_PORT"
else
    info "Starting Postiz stack (ports 6100-6106)..."
    (cd "$COMPOSE_DIR" && docker compose up -d 2>&1) | while IFS= read -r line; do
        echo "  $line"
    done

    # Wait for backend to be ready (NestJS on internal port 3000)
    info "Waiting for Postiz backend (this takes ~60-90s on first run)..."
    ATTEMPTS=0
    MAX_ATTEMPTS=40
    while [[ $ATTEMPTS -lt $MAX_ATTEMPTS ]]; do
        # Check for "Backend is running" in PM2 logs — the definitive startup signal
        if docker exec distill-postiz pm2 logs backend --lines 3 --nostream 2>/dev/null | grep -q "Backend is running"; then
            break
        fi
        ATTEMPTS=$((ATTEMPTS + 1))
        sleep 5
        printf "  Waiting... (%d/%d)\r" "$ATTEMPTS" "$MAX_ATTEMPTS"
    done
    echo ""

    if [[ $ATTEMPTS -ge $MAX_ATTEMPTS ]]; then
        warn "Postiz backend did not start within timeout."
        warn "Check logs: docker logs distill-postiz"
        warn "Continuing without Postiz API key..."
        echo ""
        echo -e "${YELLOW}━━━ Setup Partial ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "  Postiz UI:    https://localhost:$POSTIZ_HTTPS_PORT (may still be starting)"
        echo "  Run tests:    uv run pytest tests/ -x -q"
        echo ""
        exit 1
    fi
    ok "Postiz backend is ready"
fi
echo ""

# ─── 5. Create Test Account + Get API Key ──────────────────────
info "Setting up Postiz account..."

# Try to register (may already exist)
REG_RESULT=$(curl -sf -X POST "http://localhost:$POSTIZ_PORT/api/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$POSTIZ_EMAIL\",\"password\":\"$POSTIZ_PASS\",\"provider\":\"LOCAL\",\"company\":\"Distill\"}" 2>/dev/null || echo '{"error":"exists"}')

if echo "$REG_RESULT" | grep -q '"register":true'; then
    ok "Created account: $POSTIZ_EMAIL"
elif echo "$REG_RESULT" | grep -q 'already'; then
    ok "Account already exists: $POSTIZ_EMAIL"
else
    ok "Account ready: $POSTIZ_EMAIL"
fi

# Login and get auth cookie (use -D to dump headers to stdout)
AUTH_COOKIE=$(curl -s -D - -X POST "http://localhost:$POSTIZ_PORT/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$POSTIZ_EMAIL\",\"password\":\"$POSTIZ_PASS\",\"provider\":\"LOCAL\"}" 2>/dev/null \
    | grep -i "set-cookie: auth=" | sed 's/.*[Ss]et-[Cc]ookie: //' | sed 's/;.*//' | head -1 || true)

if [[ -z "$AUTH_COOKIE" ]]; then
    warn "Could not retrieve auth cookie. Set POSTIZ_API_KEY manually."
    echo "  1. Open http://localhost:$POSTIZ_PORT"
    echo "  2. Login: $POSTIZ_EMAIL / $POSTIZ_PASS"
    echo "  3. Find API key in user profile"
    echo "  4. Add to .env: POSTIZ_API_KEY=<key>"
else
    # Get API key from user self endpoint
    API_KEY=$(curl -sf "http://localhost:$POSTIZ_PORT/api/user/self" \
        -b "$AUTH_COOKIE" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('publicApi',''))" 2>/dev/null || echo "")

    if [[ -n "$API_KEY" ]]; then
        ok "Retrieved API key"

        # Write to .env
        if grep -q "^POSTIZ_API_KEY=" "$ENV_FILE" 2>/dev/null; then
            # Replace existing key
            if [[ "$(uname)" == "Darwin" ]]; then
                sed -i '' "s|^POSTIZ_API_KEY=.*|POSTIZ_API_KEY=$API_KEY|" "$ENV_FILE"
            else
                sed -i "s|^POSTIZ_API_KEY=.*|POSTIZ_API_KEY=$API_KEY|" "$ENV_FILE"
            fi
        else
            echo "POSTIZ_API_KEY=$API_KEY" >> "$ENV_FILE"
        fi
        ok "Wrote POSTIZ_API_KEY to .env"

        # Also set POSTIZ_URL if not set
        if grep -q "^POSTIZ_URL=http://localhost:$POSTIZ_PORT" "$ENV_FILE" 2>/dev/null; then
            : # already correct
        elif grep -q "^POSTIZ_URL=" "$ENV_FILE" 2>/dev/null; then
            if [[ "$(uname)" == "Darwin" ]]; then
                sed -i '' "s|^POSTIZ_URL=.*|POSTIZ_URL=http://localhost:$POSTIZ_PORT/api/public/v1|" "$ENV_FILE"
            else
                sed -i "s|^POSTIZ_URL=.*|POSTIZ_URL=http://localhost:$POSTIZ_PORT/api/public/v1|" "$ENV_FILE"
            fi
        fi
    else
        warn "Could not retrieve API key automatically."
        echo "  Login at http://localhost:$POSTIZ_PORT with $POSTIZ_EMAIL / $POSTIZ_PASS"
    fi
fi
echo ""

# ─── 6. Verify API Connection ──────────────────────────────────
# Source .env for env vars
set -a
source "$ENV_FILE" 2>/dev/null || true
set +a

if [[ -n "${POSTIZ_API_KEY:-}" && -n "${POSTIZ_URL:-}" ]]; then
    info "Verifying Postiz API connection..."
    VERIFY=$(curl -sf "$POSTIZ_URL/is-connected" -H "Authorization: $POSTIZ_API_KEY" 2>/dev/null || echo "")
    if echo "$VERIFY" | grep -q '"connected":true'; then
        ok "API connection verified"
    else
        warn "API connection check failed — verify manually:"
        echo "  curl -H 'Authorization: $POSTIZ_API_KEY' $POSTIZ_URL/integrations"
    fi
else
    warn "POSTIZ_API_KEY not set in .env — Postiz tests will be skipped"
fi
echo ""

# ─── Done ──────────────────────────────────────────────────────
echo -e "${GREEN}━━━ Setup Complete ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Postiz UI:     https://localhost:$POSTIZ_HTTPS_PORT"
echo "  Login:         $POSTIZ_EMAIL / $POSTIZ_PASS"
echo ""
echo "  Ports:"
echo "    6100  Postiz app (HTTP, internal)"
echo "    6101  PostgreSQL (Postiz)"
echo "    6102  Redis"
echo "    6103  OpenSearch"
echo "    6104  Temporal gRPC"
echo "    6105  PostgreSQL (Temporal)"
echo "    6106  Postiz HTTPS (Caddy reverse proxy)"
echo ""
echo "  Next steps:"
echo "    uv run python -m distill --help                       # CLI help"
echo "    uv run pytest tests/ -x -q                            # run all tests"
echo "    source .env && uv run pytest tests/integration/test_postiz_smoke.py -v  # Postiz smoke tests"
echo ""
echo "  Teardown:"
echo "    ./scripts/setup.sh --teardown             # stop + remove volumes"
echo ""
