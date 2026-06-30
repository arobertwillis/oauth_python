#!/usr/bin/env bash
# ============================================================
# Shared configuration for all setup scripts.
#
# This file is sourced by every other script in the setup/ folder.
# Edit the values below BEFORE running the setup scripts.
# ============================================================

# ── App Registration (API) ──────────────────────────────────────────
# Display name for the main API app registration in Azure
APP_NAME="OAuth Python API"

# App Roles for Service-to-Service auth (Client Credentials)
ROLE_READ_ALL="Items.Read.All"
ROLE_READ_ALL_DESC="Read all items (Service-to-Service)"
ROLE_WRITE_ALL="Items.Write.All"
ROLE_WRITE_ALL_DESC="Read and write all items (Service-to-Service)"

# ── App Registration (Client) ───────────────────────────────────
# Display name for the automated CLI client app
CLIENT_APP_NAME="OAuth Python API - CLI Client"

# ── Redirect URIs ───────────────────────────────────────────────
# Where Azure redirects after authentication (Swagger UI callback)
REDIRECT_URI="http://localhost:8000/docs/oauth2-redirect"

# ── Security Groups ────────────────────────────────────────────
READER_GROUP_NAME="api-readers"
READER_GROUP_DESCRIPTION="Users with read-only access to the OAuth Python API"

WRITER_GROUP_NAME="api-writers"
WRITER_GROUP_DESCRIPTION="Users with read and write access to the OAuth Python API"

# ── Test Users ──────────────────────────────────────────────────
# These will be created in your tenant. The domain is auto-detected
# from your Azure tenant (e.g., yourdomain.onmicrosoft.com).
READER_USERNAME="reader"
READER_DISPLAY_NAME="API Reader"

WRITER_USERNAME="writer"
WRITER_DISPLAY_NAME="API Writer"

# Temporary password for new users (they must change on first login)
TEMP_PASSWORD="ChangeMe@FirstLogin1!"

# ── Output ──────────────────────────────────────────────────────
# Where the generated .env file will be written (relative to repo root)
ENV_OUTPUT_FILE=".env"

# ── Colours for output ──────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No colour

# ── Helper Functions ────────────────────────────────────────────

# Print a step header
step() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Print success
ok() {
    echo -e "  ${GREEN}✓${NC} $1"
}

# Print info
info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

# Print warning
warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

# Print error and exit
fail() {
    echo -e "  ${RED}✗ ERROR:${NC} $1" >&2
    exit 1
}

# Check that a command exists
require_cmd() {
    command -v "$1" &>/dev/null || fail "'$1' is not installed. Please install it first."
}

# Check that the user is logged in to Azure CLI
require_az_login() {
    az account show &>/dev/null 2>&1 || fail "Not logged in to Azure CLI. Run 'az login' first."
}

# Get the default domain for the Azure tenant
get_tenant_domain() {
    az rest --method get \
        --url 'https://graph.microsoft.com/v1.0/domains' \
        --query "value[?isDefault].id" \
        --output tsv 2>/dev/null
}

# Get the tenant ID
get_tenant_id() {
    az account show --query tenantId --output tsv 2>/dev/null
}
