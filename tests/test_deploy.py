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
_TEMP_DIR = tempfile.mkdtemp(prefix="master_config_deploy_test_")
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

from app.config import get_settings
get_settings.cache_clear()

from app.services.git_service import GitService
import app.routes_config as routes_config
from clients.python.master_config_client.master_config_client.client import MasterConfigClient

def _create_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(routes_config.router)
    
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

test_app = _create_test_app()
client = TestClient(test_app)

@pytest.fixture(autouse=True)
def reset_services():
    os.environ["MASTER_CONFIG_DIR"] = _CONFIG_DIR
    os.environ["SCHEMAS_DIR"] = _SCHEMAS_DIR
    os.environ["SCHEMA_MAPPING_FILE"] = _MAPPING_FILE
    get_settings.cache_clear()

    routes_config._git_service = None
    routes_config._schema_service = None

    for d in [_CONFIG_DIR, _SCHEMAS_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    # Initialize Git repository
    git_svc = GitService(repo_path=_CONFIG_DIR)
    git_svc.commit_file(
        os.path.join(_CONFIG_DIR, ".gitignore"),
        "initial commit",
        author_name="System",
        author_email="system@local"
    )

def create_zip_bytes(files_dict: dict) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for file_name, data in files_dict.items():
            zip_file.writestr(file_name, data)
    return zip_buffer.getvalue()

# ── Tests ────────────────────────────────────────────────────────

def test_deploy_diff_no_changes():
    # Target has a file committed by system
    git_svc = GitService(repo_path=_CONFIG_DIR)
    file_path = os.path.join(_CONFIG_DIR, "cepe/settings.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write('{"key": "value"}')
    git_svc.commit_file(file_path, "add settings", author_name="System", author_email="api@local")

    # Deploy ZIP has the same file
    zip_bytes = create_zip_bytes({"cepe/settings.json": '{"key": "value"}'})
    response = client.post(
        "/api/config/deploy/diff",
        files={"file": ("deploy.zip", zip_bytes)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["changes"]) == 1
    assert data["changes"][0]["path"] == "cepe/settings.json"
    assert data["changes"][0]["status"] == "UNCHANGED"

def test_deploy_diff_new_and_modified_by_system():
    git_svc = GitService(repo_path=_CONFIG_DIR)
    file_path = os.path.join(_CONFIG_DIR, "cepe/settings.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write('{"key": "old"}')
    git_svc.commit_file(file_path, "add settings", author_name="System", author_email="api@local")

    zip_bytes = create_zip_bytes({
        "cepe/settings.json": '{"key": "new"}',
        "wasabi/new_config.json": '{"foo": "bar"}'
    })
    response = client.post(
        "/api/config/deploy/diff",
        files={"file": ("deploy.zip", zip_bytes)}
    )
    assert response.status_code == 200
    changes = response.json()["changes"]
    
    # Sort changes by path for assertion stability
    changes.sort(key=lambda c: c["path"])
    assert changes[0]["path"] == "cepe/settings.json"
    assert changes[0]["status"] == "MODIFIED"  # modified but by system, so safe
    assert changes[1]["path"] == "wasabi/new_config.json"
    assert changes[1]["status"] == "NEW"

def test_deploy_diff_conflict_with_end_user():
    # File committed by an end-user
    git_svc = GitService(repo_path=_CONFIG_DIR)
    file_path = os.path.join(_CONFIG_DIR, "cepe/settings.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write('{"key": "user_edits"}')
    git_svc.commit_file(
        file_path,
        "manual config edit",
        author_name="Alice User",
        author_email="alice@company.com"
    )

    zip_bytes = create_zip_bytes({"cepe/settings.json": '{"key": "incoming"}'})
    response = client.post(
        "/api/config/deploy/diff",
        files={"file": ("deploy.zip", zip_bytes)}
    )
    assert response.status_code == 200
    changes = response.json()["changes"]
    assert changes[0]["status"] == "CONFLICT"
    assert changes[0]["last_modified_by"] == "Alice User"

def test_deploy_apply_no_conflict():
    zip_bytes = create_zip_bytes({
        "cepe/settings.json": '{"key": "value"}',
    })
    response = client.post(
        "/api/config/deploy/apply",
        files={"file": ("deploy.zip", zip_bytes)},
        data={"resolutions": "{}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Verify file was written
    target_file = Path(_CONFIG_DIR) / "cepe/settings.json"
    assert target_file.exists()
    assert target_file.read_text() == '{"key": "value"}'

def test_deploy_apply_unresolved_conflict_fails():
    git_svc = GitService(repo_path=_CONFIG_DIR)
    file_path = os.path.join(_CONFIG_DIR, "cepe/settings.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write('{"key": "user_edits"}')
    git_svc.commit_file(
        file_path, 
        "manual edit", 
        author_name="Alice User", 
        author_email="alice@company.com"
    )

    zip_bytes = create_zip_bytes({"cepe/settings.json": '{"key": "incoming"}'})
    response = client.post(
        "/api/config/deploy/apply",
        files={"file": ("deploy.zip", zip_bytes)},
        data={"resolutions": "{}"}  # no resolutions
    )
    assert response.status_code == 409
    assert "Conflict detected" in response.json()["detail"]

def test_deploy_apply_resolved_accept_incoming():
    git_svc = GitService(repo_path=_CONFIG_DIR)
    file_path = os.path.join(_CONFIG_DIR, "cepe/settings.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write('{"key": "user_edits"}')
    git_svc.commit_file(
        file_path, 
        "manual edit", 
        author_name="Alice User", 
        author_email="alice@company.com"
    )

    zip_bytes = create_zip_bytes({"cepe/settings.json": '{"key": "incoming"}'})
    resolutions = json.dumps({"cepe/settings.json": "ACCEPT_INCOMING"})
    response = client.post(
        "/api/config/deploy/apply",
        files={"file": ("deploy.zip", zip_bytes)},
        data={"resolutions": resolutions}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    target_file = Path(_CONFIG_DIR) / "cepe/settings.json"
    assert target_file.read_text() == '{"key": "incoming"}'

def test_deploy_apply_resolved_keep_existing():
    git_svc = GitService(repo_path=_CONFIG_DIR)
    file_path = os.path.join(_CONFIG_DIR, "cepe/settings.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write('{"key": "user_edits"}')
    git_svc.commit_file(
        file_path, 
        "manual edit", 
        author_name="Alice User", 
        author_email="alice@company.com"
    )

    zip_bytes = create_zip_bytes({"cepe/settings.json": '{"key": "incoming"}'})
    resolutions = json.dumps({"cepe/settings.json": "KEEP_EXISTING"})
    response = client.post(
        "/api/config/deploy/apply",
        files={"file": ("deploy.zip", zip_bytes)},
        data={"resolutions": resolutions}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    target_file = Path(_CONFIG_DIR) / "cepe/settings.json"
    assert target_file.read_text() == '{"key": "user_edits"}'  # unchanged

class HttpxToRequestsWrapper:
    def __init__(self, test_client):
        self.test_client = test_client

    def get(self, url, *args, **kwargs):
        res = self.test_client.get(url, *args, **kwargs)
        # Add ok attribute for requests compatibility
        res.ok = 200 <= res.status_code < 300
        return res

    def post(self, url, *args, **kwargs):
        res = self.test_client.post(url, *args, **kwargs)
        res.ok = 200 <= res.status_code < 300
        return res

def test_python_client_deploy():
    mc_client = MasterConfigClient(base_url="http://test/api/config")
    mc_client.session = HttpxToRequestsWrapper(client)

    zip_bytes = create_zip_bytes({"wasabi/config.json": '{"test": 1}'})
    
    # 1. Test deploy_diff
    diff_res = mc_client.deploy_diff(zip_bytes)
    assert diff_res["status"] == "success"
    assert diff_res["changes"][0]["path"] == "wasabi/config.json"
    assert diff_res["changes"][0]["status"] == "NEW"

    # 2. Test deploy_apply
    apply_res = mc_client.deploy_apply(zip_bytes, resolutions={})
    assert apply_res["status"] == "success"
    
    target_file = Path(_CONFIG_DIR) / "wasabi/config.json"
    assert target_file.exists()
    assert target_file.read_text() == '{"test": 1}'
