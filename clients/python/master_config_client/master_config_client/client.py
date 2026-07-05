import datetime
import io
import os
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .exceptions import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    FileNotFoundError,
    FileTooLargeError,
    MasterConfigError,
    SchemaValidationError,
)


class MasterConfigClient:
    """Client for the Master Configuration REST API."""

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _handle_response(self, response: requests.Response) -> requests.Response:
        """Handle common API error responses."""
        if response.status_code == 401:
            raise AuthenticationError("Authentication failed. Missing or invalid token.")
        elif response.status_code == 403:
            raise AuthorizationError(response.json().get("detail", "Access forbidden."))
        elif response.status_code == 404:
            raise FileNotFoundError(response.json().get("detail", "Resource not found."))
        elif response.status_code == 413:
            raise FileTooLargeError(response.json().get("detail", "File too large."))
        elif response.status_code == 422:
            raise SchemaValidationError(response.json().get("detail", "Validation failed."))
        elif not response.ok:
            try:
                msg = response.json().get("detail", response.text)
            except ValueError:
                msg = response.text
            raise ApiError(f"API Error {response.status_code}: {msg}")

        return response

    # ── File Operations ──────────────────────────────────────────

    def list_files(self) -> List[Dict]:
        """List all configuration files."""
        res = self.session.get(f"{self.base_url}/files")
        self._handle_response(res)
        return res.json().get("files", [])

    def download_file(self, filepath: str) -> bytes:
        """Download a specific configuration file."""
        res = self.session.get(f"{self.base_url}/files/{filepath}")
        self._handle_response(res)
        return res.content

    def upload_file(self, filepath: str, content: str, schema_name: Optional[str] = None) -> Dict:
        """Upload a configuration file."""
        files = {"file": (Path(filepath).name, content)}
        data = {"schema_name": schema_name} if schema_name else {}
        
        res = self.session.post(f"{self.base_url}/files/{filepath}", files=files, data=data)
        self._handle_response(res)
        return res.json()

    def delete_file(self, filepath: str) -> Dict:
        """Delete a configuration file."""
        res = self.session.delete(f"{self.base_url}/files/{filepath}")
        self._handle_response(res)
        return res.json()

    # ── History & Rollback ───────────────────────────────────────

    def get_history(self, filepath: str) -> List[Dict]:
        """Get version history for a file."""
        res = self.session.get(f"{self.base_url}/history/{filepath}")
        self._handle_response(res)
        return res.json().get("history", [])

    def restore_file(self, filepath: str, commit_sha: str) -> Dict:
        """Restore a file to a previous version."""
        res = self.session.post(f"{self.base_url}/restore/{filepath}/{commit_sha}")
        self._handle_response(res)
        return res.json()

    # ── Batch Synchronisation ────────────────────────────────────

    def sync(self, component: str, shared_files: Optional[List[str]] = None, base_dir: str = "config") -> str:
        """
        Synchronise a component's configuration for a batch run.
        
        Downloads the entire component folder (as a zip) and any requested shared files
        into a local, timestamped snapshot directory (e.g., config/{component}/2026-07-05T14-00-00/).
        
        Returns:
            The absolute path to the local timestamped directory.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        target_dir = Path(base_dir).resolve() / component / timestamp
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Download the component folder as a zip
        res = self.session.get(f"{self.base_url}/components/{component}")
        self._handle_response(res)
        
        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            zf.extractall(path=target_dir)

        # 2. Download any explicitly requested shared files
        if shared_files:
            shared_dir = target_dir / "shared"
            shared_dir.mkdir(exist_ok=True)
            for shared_file in shared_files:
                # The filepath is relative to the master config root, e.g., 'shared/db.json'
                content = self.download_file(shared_file)
                # We save it keeping its name inside the 'shared' folder
                local_path = target_dir / shared_file
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(content)

        return str(target_dir)

    def deploy_diff(self, zip_content: bytes) -> Dict:
        """
        Perform a dry-run deployment comparison.
        """
        files = {"file": ("deploy.zip", zip_content)}
        res = self.session.post(f"{self.base_url}/deploy/diff", files=files)
        self._handle_response(res)
        return res.json()

    def deploy_apply(self, zip_content: bytes, resolutions: Optional[Dict[str, str]] = None) -> Dict:
        """
        Apply a deployment package, resolving conflicts as specified.
        """
        import json
        files = {"file": ("deploy.zip", zip_content)}
        data = {"resolutions": json.dumps(resolutions or {})}
        res = self.session.post(f"{self.base_url}/deploy/apply", files=files, data=data)
        self._handle_response(res)
        return res.json()
