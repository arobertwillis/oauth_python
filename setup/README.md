# Azure Setup Scripts

Bash scripts to fully automate the Azure Entra ID setup — no Portal clicks needed.

## Prerequisites

| Tool | Install | Purpose |
|---|---|---|
| **Azure CLI** | `brew install azure-cli` | Talks to Azure |
| **jq** | `brew install jq` | Parses JSON responses |
| **uuidgen** | Pre-installed on macOS | Generates UUIDs for API scopes |

You also need one of these Azure roles:
- **Global Administrator** (covers everything), or
- **Application Administrator** + **Groups Administrator** + **User Administrator**

## Quick Start

```bash
# 1. Log in to Azure
az login

# 2. Run the full setup (creates everything + generates .env)
./setup/setup_all.sh

# 3. Start the API
source .venv/bin/activate
uvicorn app.main:app --reload
```

That's it. The script will:
1. Create the app registration with PKCE/SPA configuration
2. Create `api-readers` and `api-writers` security groups
3. Create `reader` and `writer` test users
4. Assign users to groups and groups to the enterprise app
5. Generate the `.env` file with all the Azure IDs

## Individual Scripts

If you prefer to run steps individually (or need to re-run a single step):

| Script | What it does |
|---|---|
| `01_create_app_registration.sh` | App registration, SPA redirect, API scope, manifest, admin consent |
| `02_create_groups.sh` | Creates api-readers and api-writers security groups |
| `03_create_users.sh` | Creates reader and writer test users |
| `04_assign_memberships.sh` | Adds users to groups, assigns groups to enterprise app |
| `05_generate_env.sh` | Collects all IDs and writes the .env file |

Run them in order:

```bash
./setup/01_create_app_registration.sh
./setup/02_create_groups.sh
./setup/03_create_users.sh
./setup/04_assign_memberships.sh
./setup/05_generate_env.sh
```

## Configuration

Edit `setup/config.sh` **before** running the scripts to customise:

- App name
- Group names
- User names
- Temporary password
- Redirect URI

## Teardown

To remove **everything** created by these scripts:

```bash
./setup/teardown.sh
```

This deletes:
- The app registration (and its service principal)
- Both security groups
- Both test users
- The `.env` file
- Temporary state files

## How It Works

The scripts use a combination of:
- **`az ad`** commands for app registrations, groups, and users
- **`az rest`** calls to the **Microsoft Graph API** for features the CLI
  doesn't directly support (SPA redirects, group membership claims,
  enterprise app role assignments)

State is passed between scripts via hidden files (`.app_client_id`,
`.reader_group_id`, etc.) in the `setup/` directory. These are cleaned
up by `teardown.sh`.

## Idempotency

All scripts check for existing resources before creating new ones:
- If an app registration already exists, you're asked whether to recreate it
- If a group already exists, it's reused
- If a user already exists, it's reused
- If a group membership already exists, it's skipped

This means you can safely re-run the scripts without creating duplicates.

## Troubleshooting

### "Insufficient privileges to complete the operation"

You need the correct Azure AD roles. Ask your tenant admin to grant you
Application Administrator + Groups Administrator + User Administrator,
or Global Administrator.

### "AADSTS50011: redirect URI does not match"

The script correctly sets a **SPA** redirect (not Web). If you still see this
error, check the app registration in the Portal:
- Go to App registrations → OAuth Python API → Authentication
- The redirect URI should be under **Single-page application**, not Web

### Admin consent fails

Some tenants restrict admin consent to Global Administrators. If the
`admin-consent` step fails, you'll need to:
1. Go to Azure Portal → App registrations → OAuth Python API → API permissions
2. Click "Grant admin consent for [your tenant]"

### Script fails midway

Since the scripts are idempotent, just fix the issue and re-run.
Resources created before the failure will be detected and reused.
