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

## 5. Client Credentials Flow (Service-to-Service)

If you are building an automated script or background job that needs to access this API, it cannot use a browser to log in. Instead, it must authenticate as an application using the **Client Credentials Flow** with **X.509 Certificate Authentication**.

Our setup scripts automatically create a second "Client" App Registration, assign it the correct **App Roles** (`Items.Write.All`), generate a secure **Self-Signed Certificate** in the `.certs/` folder, and create a `.env.client` file with the certificate thumbprint.

### Example Clients

We have provided two complete example clients that natively load the `.pem` certificate, securely request a JWT from Azure AD, and call the API.

#### Python Client
```bash
cd clients/python
pip install -r requirements.txt
python cli.py
```

#### C# Client
```bash
cd clients/csharp/CliClient
dotnet run
```

---

## 6. Project Structure

```text
oauth_python/
├── app/
│   ├── main.py              # FastAPI application
│   ├── auth.py              # Authentication & Authorization logic
│   ├── routes.py            # API endpoints
│   └── config.py            # Environment variables
├── clients/
│   ├── python/              # Python CLI Client example
│   └── csharp/              # C# CLI Client example
├── setup/                   # Automation scripts for Azure AD
├── docs/                    # Architectural documentation
├── .env                     # Server configuration (generated)
├── .env.client              # Client configuration (generated)
└── requirements.txt         # Server Python dependencies
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

## Deployment & Backup Prerequisite (REQ-1.9)

The master configuration Git repository MUST reside on a filesystem that is independently backed up. Production and staging environments must have scheduled filesystem snapshots, replication, or enterprise backup tooling enabled to guarantee recovery in the event of hardware or storage failure.

## Requirements

- Python 3.14+
- Azure subscription (free tier sufficient)
- Microsoft Entra ID tenant
