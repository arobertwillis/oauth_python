# Master Configuration System Usage Guide

This guide provides practical examples and code snippets for using all features of the Master Configuration System.

---

## 1. Authentication & API Headers

The API is strictly secured with Microsoft Entra ID (Azure AD). You must include a valid Bearer Token in the `Authorization` header of all requests.

```http
Authorization: Bearer <azure-ad-jwt-token>
```

---

## 2. File CRUD Operations

### 2.1 Upload a Configuration File (JSON/YAML)
Upload files to arbitrary paths within the master configuration directory.

**Request:**
```bash
curl -X POST http://localhost:8000/api/config/files/cepe/app_settings.json \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my_local_settings.json"
```

**Request (with Explicit Schema Validation):**
```bash
curl -X POST http://localhost:8000/api/config/files/cepe/app_settings.json \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my_local_settings.json" \
  -F "schema_name=app_settings"
```

### 2.2 List Configuration Files
Retrieves all files with audit metadata parsed from Git history.

**Request:**
```bash
curl -X GET http://localhost:8000/api/config/files \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "files": [
    {
      "path": "cepe/app_settings.json",
      "last_modified_by": "John Doe",
      "last_modified_at": "2026-07-05T14:00:00Z"
    }
  ]
}
```

### 2.3 Download a File
```bash
curl -X GET http://localhost:8000/api/config/files/cepe/app_settings.json \
  -H "Authorization: Bearer $TOKEN" \
  --output downloaded_settings.json
```

---

## 3. CSV File Validation (Pandera)

CSV files can be uploaded and validated using the `pandera` engine. You must define a Pandera-compatible CSV schema first.

### 3.1 Upload a CSV Schema
Define a JSON schema indicating the `columns` structure:

```bash
curl -X POST http://localhost:8000/api/config/schemas/csv_sales_data \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "columns": {
      "transaction_id": {"dtype": "int", "nullable": false},
      "amount": {"dtype": "float", "nullable": false},
      "customer_email": {"dtype": "str", "nullable": true}
    }
  }'
```

### 3.2 Upload & Validate the CSV File
```bash
curl -X POST http://localhost:8000/api/config/files/cepe/daily_sales.csv \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sales.csv" \
  -F "schema_name=csv_sales_data"
```

---

## 4. Custom Validator Plugins

You can write custom Python validators to perform deep validation rules (business logic checks, checking DB connections, etc.).

### 4.1 Write a Validator Plugin
Create a new file in `app/validators/db_connection_validator.py` inheriting from `BaseValidator`:

```python
from app.validators.base_validator import BaseValidator

class DbConnectionValidator(BaseValidator):
    def should_validate(self, filename: str, ext: str) -> bool:
        # Run this validator only on database settings files
        return filename == "database.json"

    def validate(self, filename: str, data: dict) -> list[str]:
        errors = []
        # Custom business logic check
        if "conn_string" not in data:
            errors.append("Missing 'conn_string' property in database settings")
        elif not data["conn_string"].startswith("postgresql://"):
            errors.append("Connection string must be a postgresql URL")
            
        return errors
```
*Note: The plugin will be automatically discovered and executed on the next file upload!*

---

## 5. Environment Synchronization & Deployment

Deploy configurations from Staging to Production, complete with dry-run conflict detection.

### 5.1 Step 1: Run a Deployment Diff (Dry-Run)
Upload a zip of the configuration package to compare it against the target environment.

```bash
curl -X POST http://localhost:8000/api/config/deploy/diff \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@deploy_package.zip"
```

**Response:**
```json
{
  "status": "success",
  "changes": [
    {
      "path": "cepe/settings.json",
      "status": "CONFLICT",
      "last_modified_by": "Jane Admin",
      "last_modified_at": "2026-07-05T14:30:00Z"
    },
    {
      "path": "wasabi/new.json",
      "status": "NEW",
      "last_modified_by": "System",
      "last_modified_at": null
    }
  ]
}
```

### 5.2 Step 2: Apply the Deployment with Resolutions
If there are conflicted files, specify whether to keep the environment's edits or override them with the incoming version.

```bash
curl -X POST http://localhost:8000/api/config/deploy/apply \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@deploy_package.zip" \
  -F 'resolutions={"cepe/settings.json": "ACCEPT_INCOMING"}'
```

---

## 6. Python Client Library (`master_config_client`)

Embed this minimal client into your Python batch runs or CI/CD pipelines.

### 6.1 Initialize Client
```python
from master_config_client import MasterConfigClient

client = MasterConfigClient(
    base_url="http://localhost:8000/api/config", 
    token="YOUR_AZURE_JWT_TOKEN"
)
```

### 6.2 Synchronize Component for a Batch Run (REQ-8.5 & 11.5)
Downloads the full component folder and shared dependencies into a local, dated directory snapshot.

```python
local_path = client.sync(
    component="cepe",
    shared_files=["shared/db_conn.json"],
    base_dir="config"
)

print(f"Isolated config snapshot created at: {local_path}")
# Output: config/cepe/2026-07-05T21-30-00/
```

### 6.3 Programmatic Deployment
```python
with open("deploy.zip", "rb") as f:
    zip_bytes = f.read()

# Check for conflicts
diff = client.deploy_diff(zip_bytes)
print(diff["changes"])

# Apply deployment
client.deploy_apply(
    zip_bytes, 
    resolutions={"cepe/settings.json": "KEEP_EXISTING"}
)
```
