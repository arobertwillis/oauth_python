# OAuth Python API

A FastAPI application secured with Microsoft Entra ID (Azure AD) using JWT tokens
and security group-based authorisation. Built with Python 3.14.

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────────┐
│              │     │                 │     │  Microsoft Entra ID  │
│   Browser    │────▶│   FastAPI API   │     │  (Azure AD)          │
│  (Swagger UI)│     │                 │     │                      │
│              │◀────│  • Validates    │     │  • Issues JWTs       │
│              │     │    JWT tokens   │◀───▶│  • Hosts login page  │
│              │────▶│  • Checks group │     │  • Manages users     │
│              │     │    membership   │     │  • Manages groups    │
└──────────────┘     └─────────────────┘     └──────────────────────┘
```

### Access Control

| Group | Read Endpoints | Write Endpoints |
|---|---|---|
| `api-readers` | ✅ | ❌ |
| `api-writers` | ✅ | ✅ |

## Quick Start

### 1. Set Up Azure

**Option A: Automated (recommended)**

```bash
az login
./setup/setup_all.sh
```

This creates everything in Azure and generates the `.env` file automatically.
See **[setup/README.md](setup/README.md)** for details.

**Option B: Manual**

Follow **[docs/azure_setup.md](docs/azure_setup.md)** step-by-step, then:

```bash
cp .env.example .env
# Edit .env with your Azure values
```

### 3. Install Dependencies

```bash
# Create a virtual environment (Python 3.14)
python3.14 -m venv .venv
source .venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 4. Run the API

**Option A: Run Locally**
```bash
uvicorn app.main:app --reload
```

**Option B: Run with Docker**
```bash
# Easiest way (builds and runs automatically with correct flags)
./run_docker.sh

# Or manually:
docker build -t oauth_python_api .
docker run -p 8000:8000 --env-file .env oauth_python_api
```

### 5. Authenticate

1. Open http://localhost:8000/docs
2. Click the **Authorize** button (🔓)
3. Click **Authorize** in the popup — you'll be redirected to Microsoft login
4. Sign in with one of your test users
5. You're now authenticated — try the endpoints!

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `GET /api/public` | GET | None | Health check |
| `GET /api/me` | GET | Read | Current user's JWT claims |
| `GET /api/items` | GET | Read | List all items |
| `GET /api/items/{id}` | GET | Read | Get single item |
| `POST /api/items` | POST | Write | Create item |
| `PUT /api/items/{id}` | PUT | Write | Update item |
| `DELETE /api/items/{id}` | DELETE | Write | Delete item |

## Documentation

- **[Setup Scripts](setup/README.md)** — Automated Azure setup (recommended)
- **[Azure Setup Guide](docs/azure_setup.md)** — Manual step-by-step Azure configuration
- **[JWT Security Guide](docs/jwt_security.md)** — How JWT authentication works and security practices

## Project Structure

```
oauth_python/
├── app/
│   ├── __init__.py          # Package init
│   ├── config.py            # Settings from environment variables
│   ├── auth.py              # JWT validation + group authorisation
│   ├── main.py              # FastAPI app setup
│   └── routes.py            # API endpoints
├── docs/
│   ├── azure_setup.md       # Manual Azure configuration guide
│   └── jwt_security.md      # JWT security documentation
├── setup/
│   ├── config.sh            # Shared configuration for setup scripts
│   ├── setup_all.sh         # Run all setup steps at once
│   ├── 01_create_app_registration.sh
│   ├── 02_create_groups.sh
│   ├── 03_create_users.sh
│   ├── 04_assign_memberships.sh
│   ├── 05_generate_env.sh
│   ├── teardown.sh          # Remove all Azure resources
│   └── README.md            # Setup scripts documentation
├── .env.example             # Environment variable template
├── .gitignore               # Prevents committing secrets
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Cost

**$0** — This entire setup uses the Microsoft Entra ID Free tier, which is
included with any Azure subscription. App registrations, security groups,
user accounts, and token issuance are all free.

## Security

- **PKCE** (Proof Key for Code Exchange) — no client secrets in the browser
- **Stateless** — no server-side session storage; every request validated independently
- **Automatic key rotation** — Microsoft's signing keys are refreshed automatically
- **Group-based access control** — permissions managed in Azure, not in code
- **Secrets in environment** — `.env` file excluded from version control

See **[docs/jwt_security.md](docs/jwt_security.md)** for a full security deep-dive.

## Requirements

- Python 3.14+
- Azure subscription (free tier sufficient)
- Microsoft Entra ID tenant
