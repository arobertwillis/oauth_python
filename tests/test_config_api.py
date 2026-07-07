"""
Comprehensive test suite for the Master Configuration REST API.

Tests cover:
- File upload with and without schema validation
- CSV upload with pandera validation
- File size limit enforcement
- Protected file deletion prevention
- File history and rollback
- Bulk component download
- Schema CRUD
- Filename-to-schema auto-mapping

All tests use a temporary directory and a fresh Git repo to avoid
interfering with real data.  Azure AD auth is bypassed via env overrides.
"""

import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Setup ────────────────────────────────────────────────────────
# We need to set environment variables BEFORE importing app modules
# so that Settings() reads from env instead of requiring a .env file.

_TEMP_DIR = tempfile.mkdtemp(prefix="master_config_test_")
_CONFIG_DIR = os.path.join(_TEMP_DIR, "master_config")
_SCHEMAS_DIR = os.path.join(_TEMP_DIR, "schemas")
_MAPPING_FILE = os.path.join(_SCHEMAS_DIR, "mapping.json")

os.environ["AZURE_TENANT_ID"] = "test-tenant"
os.environ["AZURE_CLIENT_ID"] = "test-client"
os.environ["AZURE_READER_GROUP_ID"] = "test-readers"
os.environ["AZURE_WRITER_GROUP_ID"] = "test-writers"
os.environ["MASTER_CONFIG_DIR"] = _CONFIG_DIR
os.environ["SCHEMAS_DIR"] = _SCHEMAS_DIR
os.environ["SCHEMA_MAPPING_FILE"] = _MAPPING_FILE

# Now import app modules
from app.config import Settings, get_settings

# Clear the lru_cache so our env vars are picked up
get_settings.cache_clear()

from app.services.git_service import GitService
from app.services.schema_service import SchemaService, SchemaValidationException
import app.routes_config as routes_config


# ── Build a test app without Azure AD auth ───────────────────────

def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with only the config routes (no Azure AD)."""
    test_app = FastAPI()
    test_app.include_router(routes_config.router)
    
    # Override Azure AD dependencies
    from app.auth import require_read_access, require_write_access, get_current_user
    from fastapi_azure_auth.user import User
    
    def mock_read(): return None
    def mock_write(): return None
    def mock_user(): 
        return User(
            name="API User", 
            preferred_username="api@local", 
            oid="123", 
            claims={}, 
            scp="", 
            tid="123", 
            aud="123", 
            iss="123", 
            iat=0, 
            nbf=0, 
            exp=0, 
            sub="123",
            ver="1.0",
            access_token="mock_token"
        )
        
    from app.routes_config import read_access_dep, write_access_dep
        
    test_app.dependency_overrides[read_access_dep] = mock_read
    test_app.dependency_overrides[write_access_dep] = mock_write
    test_app.dependency_overrides[get_current_user] = mock_user
    
    return test_app


@pytest.fixture(autouse=True)
def reset_services():
    """Reset service singletons and temp directories before each test."""
    os.environ["MASTER_CONFIG_DIR"] = _CONFIG_DIR
    os.environ["SCHEMAS_DIR"] = _SCHEMAS_DIR
    os.environ["SCHEMA_MAPPING_FILE"] = _MAPPING_FILE
    get_settings.cache_clear()

    # Reset singletons
    routes_config._git_service = None
    routes_config._schema_service = None

    # Clear and recreate temp dirs
    for d in [_CONFIG_DIR, _SCHEMAS_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    # Create component folders
    for comp in ["cepe", "wasabi", "gvmerge", "shared"]:
        os.makedirs(os.path.join(_CONFIG_DIR, comp), exist_ok=True)

    # Create initial master_configuration.json
    mc = {
        "environment": "test",
        "version": "1.0.0",
        "components": {
            "cepe": {"description": "CEPE", "shared_files": []},
            "wasabi": {"description": "Wasabi", "shared_files": []},
            "gvmerge": {"description": "GVMerge", "shared_files": []},
        },
    }
    mc_path = os.path.join(_CONFIG_DIR, "master_configuration.json")
    with open(mc_path, "w") as f:
        json.dump(mc, f)

    # Create app_settings schema
    app_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "app_name": {"type": "string"},
            "debug_mode": {"type": "boolean"},
        },
        "required": ["app_name", "debug_mode"],
    }
    with open(os.path.join(_SCHEMAS_DIR, "app_settings.json"), "w") as f:
        json.dump(app_schema, f)

    # Create CSV schema
    csv_schema = {
        "columns": {
            "id": {"dtype": "int", "nullable": False},
            "name": {"dtype": "str", "nullable": False},
        }
    }
    with open(os.path.join(_SCHEMAS_DIR, "csv_test.json"), "w") as f:
        json.dump(csv_schema, f)

    # Create mapping.json
    mapping = {"^.*app_settings.*\\.json$": "app_settings"}
    with open(_MAPPING_FILE, "w") as f:
        json.dump(mapping, f)

    # Init git repo and commit initial files
    from git import Repo
    repo = Repo.init(_CONFIG_DIR)
    repo.index.add(".")
    repo.index.commit("Initial commit")

    yield

    get_settings.cache_clear()


@pytest.fixture
def client():
    app = _create_test_app()
    return TestClient(app)


# ═════════════════════════════════════════════════════════════════
# FILE LISTING
# ═════════════════════════════════════════════════════════════════

class TestListFiles:
    def test_list_files_returns_master_config(self, client):
        resp = client.get("/api/config/files")
        assert resp.status_code == 200
        data = resp.json()
        paths = [f["path"] for f in data["files"]]
        assert "master_configuration.json" in paths

    def test_list_files_includes_audit_metadata(self, client):
        resp = client.get("/api/config/files")
        data = resp.json()
        for f in data["files"]:
            assert "last_modified_by" in f
            assert "last_modified_at" in f


# ═════════════════════════════════════════════════════════════════
# FILE UPLOAD — WITH SCHEMA
# ═════════════════════════════════════════════════════════════════

class TestUploadWithSchema:
    def test_upload_valid_json_with_explicit_schema(self, client):
        content = json.dumps({"app_name": "Test", "debug_mode": True})
        resp = client.post(
            "/api/config/files/cepe/settings.json",
            files={"file": ("settings.json", content)},
            data={"schema_name": "app_settings"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["schema_used"] == "app_settings"
        assert data["schema_method"] == "explicit"

    def test_upload_invalid_json_with_schema_returns_422(self, client):
        content = json.dumps({"app_name": "Test"})  # missing debug_mode
        resp = client.post(
            "/api/config/files/cepe/settings.json",
            files={"file": ("settings.json", content)},
            data={"schema_name": "app_settings"},
        )
        assert resp.status_code == 422
        assert "debug_mode" in resp.json()["detail"]

    def test_upload_auto_mapped_schema(self, client):
        """File named *app_settings*.json should auto-map to app_settings schema."""
        content = json.dumps({"app_name": "Auto", "debug_mode": False})
        resp = client.post(
            "/api/config/files/cepe/app_settings_v2.json",
            files={"file": ("app_settings_v2.json", content)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_used"] == "app_settings"
        assert data["schema_method"] == "auto-mapped"

    def test_upload_auto_mapped_invalid_returns_422(self, client):
        """Auto-mapped schema should also reject invalid files."""
        content = json.dumps({"wrong_field": "value"})
        resp = client.post(
            "/api/config/files/wasabi/app_settings_bad.json",
            files={"file": ("app_settings_bad.json", content)},
        )
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════
# FILE UPLOAD — WITHOUT SCHEMA
# ═════════════════════════════════════════════════════════════════

class TestUploadWithoutSchema:
    def test_upload_json_no_schema(self, client):
        content = json.dumps({"anything": "goes"})
        resp = client.post(
            "/api/config/files/cepe/custom.json",
            files={"file": ("custom.json", content)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_used"] is None
        assert data["schema_method"] == "none"

    def test_upload_yaml_no_schema(self, client):
        content = "key: value\nlist:\n  - a\n  - b\n"
        resp = client.post(
            "/api/config/files/wasabi/data.yaml",
            files={"file": ("data.yaml", content)},
        )
        assert resp.status_code == 200

    def test_upload_plain_text_no_schema(self, client):
        content = "This is a plain text config file."
        resp = client.post(
            "/api/config/files/cepe/notes.txt",
            files={"file": ("notes.txt", content)},
        )
        assert resp.status_code == 200

    def test_upload_invalid_json_syntax_returns_422(self, client):
        content = "{broken json"
        resp = client.post(
            "/api/config/files/cepe/bad.json",
            files={"file": ("bad.json", content)},
        )
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════
# CSV UPLOAD
# ═════════════════════════════════════════════════════════════════

class TestCSVUpload:
    def test_upload_valid_csv_with_schema(self, client):
        content = "id,name\n1,Alice\n2,Bob\n"
        resp = client.post(
            "/api/config/files/cepe/data.csv",
            files={"file": ("data.csv", content)},
            data={"schema_name": "csv_test"},
        )
        assert resp.status_code == 200
        assert resp.json()["schema_used"] == "csv_test"

    def test_upload_csv_missing_column_returns_422(self, client):
        content = "id,wrong_column\n1,Alice\n"
        resp = client.post(
            "/api/config/files/cepe/data.csv",
            files={"file": ("data.csv", content)},
            data={"schema_name": "csv_test"},
        )
        assert resp.status_code == 422
        assert "name" in resp.json()["detail"]

    def test_upload_csv_no_schema(self, client):
        content = "any,columns,here\n1,2,3\n"
        resp = client.post(
            "/api/config/files/cepe/unvalidated.csv",
            files={"file": ("unvalidated.csv", content)},
        )
        assert resp.status_code == 200
        assert resp.json()["schema_used"] is None

    def test_upload_invalid_csv_syntax(self, client):
        # pandas is lenient but we'll test malformed content
        content = ""  # empty file
        resp = client.post(
            "/api/config/files/cepe/empty.csv",
            files={"file": ("empty.csv", content)},
            data={"schema_name": "csv_test"},
        )
        # Empty CSV should fail if schema expects columns
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════
# FILE SIZE LIMIT
# ═════════════════════════════════════════════════════════════════

class TestFileSizeLimit:
    def test_upload_exceeding_size_limit_returns_413(self, client):
        # Temporarily set a tiny limit
        settings = get_settings()
        original = settings.max_upload_size_bytes
        settings.max_upload_size_bytes = 100  # 100 bytes

        content = "x" * 200
        resp = client.post(
            "/api/config/files/cepe/big.txt",
            files={"file": ("big.txt", content)},
        )
        assert resp.status_code == 413
        settings.max_upload_size_bytes = original  # restore


# ═════════════════════════════════════════════════════════════════
# PROTECTED FILE DELETION
# ═════════════════════════════════════════════════════════════════

class TestProtectedFiles:
    def test_delete_protected_file_returns_403(self, client):
        resp = client.delete("/api/config/files/master_configuration.json")
        assert resp.status_code == 403
        assert "protected" in resp.json()["detail"].lower()

    def test_delete_normal_file_succeeds(self, client):
        # First upload a file
        content = json.dumps({"temp": True})
        client.post(
            "/api/config/files/cepe/temp.json",
            files={"file": ("temp.json", content)},
        )

        resp = client.delete("/api/config/files/cepe/temp.json")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# ═════════════════════════════════════════════════════════════════
# FILE DOWNLOAD
# ═════════════════════════════════════════════════════════════════

class TestFileDownload:
    def test_download_existing_file(self, client):
        resp = client.get("/api/config/files/master_configuration.json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["environment"] == "test"

    def test_download_nonexistent_file_returns_404(self, client):
        resp = client.get("/api/config/files/does_not_exist.json")
        assert resp.status_code == 404

    def test_directory_traversal_blocked(self, client):
        resp = client.get("/api/config/files/../../etc/passwd")
        # FastAPI normalizes the path, so it resolves to a 400 or 404
        assert resp.status_code in (400, 404)


# ═════════════════════════════════════════════════════════════════
# FILE HISTORY & ROLLBACK
# ═════════════════════════════════════════════════════════════════

class TestHistoryAndRollback:
    def test_file_history_returns_commits(self, client):
        # Upload a file so there's a trackable per-file commit
        content = json.dumps({"history_test": True})
        client.post("/api/config/files/cepe/hist.json", files={"file": ("hist.json", content)})

        resp = client.get("/api/config/history/cepe/hist.json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["history"]) >= 1
        assert "commit_sha" in data["history"][0]
        assert "author_name" in data["history"][0]

    def test_upload_creates_history(self, client):
        # Upload two versions
        v1 = json.dumps({"version": 1})
        v2 = json.dumps({"version": 2})

        client.post("/api/config/files/cepe/versioned.json", files={"file": ("versioned.json", v1)})
        client.post("/api/config/files/cepe/versioned.json", files={"file": ("versioned.json", v2)})

        resp = client.get("/api/config/history/cepe/versioned.json")
        data = resp.json()
        assert len(data["history"]) == 2

    def test_rollback_restores_previous_version(self, client):
        v1 = json.dumps({"version": 1})
        v2 = json.dumps({"version": 2})

        client.post("/api/config/files/cepe/rollback_test.json", files={"file": ("rollback_test.json", v1)})
        client.post("/api/config/files/cepe/rollback_test.json", files={"file": ("rollback_test.json", v2)})

        # Get commit SHA of v1
        resp = client.get("/api/config/history/cepe/rollback_test.json")
        history = resp.json()["history"]
        v1_sha = history[1]["commit_sha"]  # Second entry is the older one

        # Restore
        resp = client.post(f"/api/config/restore/cepe/rollback_test.json/{v1_sha}")
        assert resp.status_code == 200

        # Verify content is back to v1
        resp = client.get("/api/config/files/cepe/rollback_test.json")
        data = json.loads(resp.content)
        assert data["version"] == 1


# ═════════════════════════════════════════════════════════════════
# BULK COMPONENT DOWNLOAD
# ═════════════════════════════════════════════════════════════════

class TestBulkComponentDownload:
    def test_download_component_as_zip(self, client):
        # Upload files to cepe
        client.post("/api/config/files/cepe/a.json", files={"file": ("a.json", '{"a": 1}')})
        client.post("/api/config/files/cepe/b.json", files={"file": ("b.json", '{"b": 2}')})

        resp = client.get("/api/config/components/cepe")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        # Verify zip contents
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = z.namelist()
        assert "a.json" in names
        assert "b.json" in names

    def test_download_nonexistent_component_returns_404(self, client):
        resp = client.get("/api/config/components/nonexistent")
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════
# SCHEMA CRUD
# ═════════════════════════════════════════════════════════════════

class TestSchemaCRUD:
    def test_list_schemas(self, client):
        resp = client.get("/api/config/schemas")
        assert resp.status_code == 200
        assert "app_settings" in resp.json()["schemas"]

    def test_get_schema(self, client):
        resp = client.get("/api/config/schemas/app_settings")
        assert resp.status_code == 200
        schema = resp.json()["schema"]
        assert "properties" in schema

    def test_get_nonexistent_schema_returns_404(self, client):
        resp = client.get("/api/config/schemas/nope")
        assert resp.status_code == 404

    def test_create_schema(self, client):
        new_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        resp = client.post("/api/config/schemas/new_one", json=new_schema)
        assert resp.status_code == 200

        resp = client.get("/api/config/schemas/new_one")
        assert resp.status_code == 200

    def test_delete_schema(self, client):
        resp = client.delete("/api/config/schemas/app_settings")
        assert resp.status_code == 200

        resp = client.get("/api/config/schemas/app_settings")
        assert resp.status_code == 404

    def test_get_schema_mapping(self, client):
        resp = client.get("/api/config/schemas-mapping")
        assert resp.status_code == 200
        assert "mapping" in resp.json()


# ═════════════════════════════════════════════════════════════════
# GIT AUTHOR ATTRIBUTION
# ═════════════════════════════════════════════════════════════════

class TestGitAuthorAttribution:
    def test_commit_records_author(self, client):
        content = json.dumps({"test": "author"})
        client.post("/api/config/files/cepe/author_test.json", files={"file": ("author_test.json", content)})

        resp = client.get("/api/config/history/cepe/author_test.json")
        history = resp.json()["history"]
        assert len(history) == 1
        assert history[0]["author_name"] == "API User"
        assert history[0]["author_email"] == "api@local"
