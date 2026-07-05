import io
import os
import zipfile
from pathlib import Path

import pytest
import responses

from master_config_client import MasterConfigClient
from master_config_client.exceptions import AuthenticationError, FileNotFoundError, SchemaValidationError

BASE_URL = "http://test-server/api/config"


@pytest.fixture
def client():
    return MasterConfigClient(base_url=BASE_URL, token="test-token")


@responses.activate
def test_list_files(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/files",
        json={"files": [{"path": "cepe/test.json"}]},
        status=200,
    )
    files = client.list_files()
    assert len(files) == 1
    assert files[0]["path"] == "cepe/test.json"


@responses.activate
def test_download_file(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/files/test.json",
        body=b'{"key":"value"}',
        status=200,
    )
    content = client.download_file("test.json")
    assert content == b'{"key":"value"}'


@responses.activate
def test_upload_file(client):
    responses.add(
        responses.POST,
        f"{BASE_URL}/files/cepe/test.json",
        json={"status": "success", "schema_used": "test_schema"},
        status=200,
    )
    res = client.upload_file("cepe/test.json", '{"key":"value"}', schema_name="test_schema")
    assert res["status"] == "success"
    assert res["schema_used"] == "test_schema"


@responses.activate
def test_api_error_handling(client):
    responses.add(
        responses.GET,
        f"{BASE_URL}/files/missing.json",
        json={"detail": "File not found"},
        status=404,
    )
    with pytest.raises(FileNotFoundError) as exc:
        client.download_file("missing.json")
    assert "File not found" in str(exc.value)

    responses.add(
        responses.POST,
        f"{BASE_URL}/files/bad.json",
        json={"detail": "Schema invalid"},
        status=422,
    )
    with pytest.raises(SchemaValidationError):
        client.upload_file("bad.json", '{"bad":1}')

    responses.add(
        responses.GET,
        f"{BASE_URL}/files",
        json={"detail": "Missing token"},
        status=401,
    )
    with pytest.raises(AuthenticationError):
        client.list_files()


@responses.activate
def test_sync(client, tmp_path):
    # Mock the component zip download
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("a.json", '{"a": 1}')
    
    responses.add(
        responses.GET,
        f"{BASE_URL}/components/cepe",
        body=zip_buffer.getvalue(),
        status=200,
    )

    # Mock the shared file download
    responses.add(
        responses.GET,
        f"{BASE_URL}/files/shared/db.json",
        body=b'{"db": "conn"}',
        status=200,
    )

    local_dir = client.sync("cepe", shared_files=["shared/db.json"], base_dir=str(tmp_path))
    
    # Verify files were written
    local_path = Path(local_dir)
    assert local_path.exists()
    assert (local_path / "a.json").exists()
    assert (local_path / "shared" / "db.json").exists()
    assert (local_path / "shared" / "db.json").read_bytes() == b'{"db": "conn"}'
