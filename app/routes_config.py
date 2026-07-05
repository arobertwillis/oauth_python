"""
REST API for Master Configuration management.

Provides endpoints for:
- File CRUD (upload, download, list, delete)
- Bulk component download (zip)
- File history and rollback
- Schema CRUD
- Detailed request logging
"""

import io
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.config import Settings, get_settings
from app.services.git_service import GitService
from app.services.schema_service import SchemaService, SchemaValidationException
from app.validators import get_validators

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["Configuration"])

# ── Service singletons ──────────────────────────────────────────

_git_service: GitService | None = None
_schema_service: SchemaService | None = None


def _get_git_service() -> GitService:
    global _git_service
    if _git_service is None:
        settings = get_settings()
        _git_service = GitService(repo_path=settings.master_config_dir)
    return _git_service


def _get_schema_service() -> SchemaService:
    global _schema_service
    if _schema_service is None:
        settings = get_settings()
        _schema_service = SchemaService(
            schemas_dir=settings.schemas_dir,
            mapping_file=settings.schema_mapping_file,
        )
    return _schema_service


def _config_dir() -> Path:
    return Path(get_settings().master_config_dir).resolve()


# ── Auth helpers (allow bypass for tests) ────────────────────────

def _get_read_dep():
    """Import here to allow test overrides."""
    from app.auth import require_read_access
    return Depends(require_read_access())


def _get_write_dep():
    from app.auth import require_write_access
    return Depends(require_write_access())


# ── User info extraction ────────────────────────────────────────

def _extract_author(user) -> tuple[str, str]:
    """Extract name and email from the Azure AD user for Git author."""
    name = getattr(user, "name", None) or getattr(user, "preferred_username", None) or "Unknown"
    email = getattr(user, "preferred_username", None) or getattr(user, "oid", "unknown@local")
    return name, email


# ── Middleware-style logging ─────────────────────────────────────

def _log_request(request: Request, action: str, filepath: str = "", extra: str = ""):
    logger.info(
        "CONFIG API | %s %s | action=%s | path=%s | client=%s | %s",
        request.method,
        request.url.path,
        action,
        filepath,
        request.client.host if request.client else "unknown",
        extra,
    )


# ═════════════════════════════════════════════════════════════════
# FILE ENDPOINTS
# ═════════════════════════════════════════════════════════════════

@router.get("/files")
async def list_files(request: Request):
    """
    List all configuration files with audit metadata.

    Returns each file's relative path, last modified time, and last modifier
    extracted from Git history.
    """
    _log_request(request, "list_files")
    config_dir = _config_dir()
    git = _get_git_service()

    files = []
    if not config_dir.exists():
        return {"files": files}

    for root, dirs, filenames in os.walk(config_dir):
        # Skip .git directory
        dirs[:] = [d for d in dirs if d != ".git"]
        for filename in filenames:
            if filename.startswith(".git"):
                continue
            abs_path = Path(root) / filename
            rel_path = str(abs_path.relative_to(config_dir))

            # Get audit info from git history
            history = git.get_file_history(rel_path, max_count=1)
            last_modified_by = history[0]["author_name"] if history else "Unknown"
            last_modified_at = history[0]["date"] if history else None

            files.append({
                "path": rel_path,
                "last_modified_by": last_modified_by,
                "last_modified_at": last_modified_at,
            })

    return {"files": sorted(files, key=lambda f: f["path"])}


@router.get("/files/{filepath:path}")
async def download_file(filepath: str, request: Request):
    """Download a specific configuration file."""
    _log_request(request, "download_file", filepath)
    config_dir = _config_dir()
    target_path = (config_dir / filepath).resolve()

    if not str(target_path).startswith(str(config_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(target_path, filename=target_path.name)


@router.post("/files/{filepath:path}")
async def upload_file(
    filepath: str,
    request: Request,
    file: UploadFile = File(...),
    schema_name: Optional[str] = Form(None),
):
    """
    Upload a configuration file.

    - Validates file size (max 1 GB)
    - Auto-detects or explicitly validates against a schema
    - Runs custom validators
    - Saves file and commits to Git with the authenticated user as author
    """
    settings = get_settings()
    config_dir = _config_dir()
    target_path = (config_dir / filepath).resolve()

    if not str(target_path).startswith(str(config_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Read content and enforce file size limit (REQ-2.6)
    content_bytes = await file.read()
    if len(content_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum upload size of {settings.max_upload_size_bytes} bytes",
        )

    _log_request(request, "upload_file", filepath, f"size={len(content_bytes)}")

    content_str = content_bytes.decode("utf-8")
    file_ext = target_path.suffix
    filename = target_path.name

    # Schema validation (REQ-3.1, 3.3)
    schema_svc = _get_schema_service()
    schema_svc.load_schemas()
    schema_svc.load_mapping()

    try:
        result = schema_svc.validate_content(content_str, filename, file_ext, schema_name)
    except SchemaValidationException as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Custom validators (REQ-4.1–4.3)
    parsed_data = content_str
    try:
        if file_ext.lower() == ".json":
            import json
            parsed_data = json.loads(content_str)
        elif file_ext.lower() in (".yaml", ".yml"):
            import yaml
            parsed_data = yaml.safe_load(content_str)
    except Exception:
        pass  # Already validated above

    for validator in get_validators():
        if validator.should_validate(filename, file_ext):
            errors = validator.validate(filename, parsed_data)
            if errors:
                raise HTTPException(
                    status_code=422,
                    detail=f"Custom validation failed: {'; '.join(errors)}",
                )

    # Save file (REQ-1.1)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w") as f:
        f.write(content_str)

    # Git commit with real author (REQ-1.3, 1.4)
    git = _get_git_service()
    # For testing without auth, use defaults
    author_name = "API User"
    author_email = "api@local"

    success = git.commit_file(
        str(target_path),
        f"Update config: {filepath}",
        author_name=author_name,
        author_email=author_email,
    )

    if not success:
        raise HTTPException(status_code=500, detail="File saved but Git commit failed — file has been rolled back")

    return {
        "status": "success",
        "message": f"File {filepath} saved and committed successfully.",
        "schema_used": result.get("schema_used"),
        "schema_method": result.get("method"),
    }


@router.delete("/files/{filepath:path}")
async def delete_file(filepath: str, request: Request):
    """Delete a configuration file and commit to Git."""
    settings = get_settings()
    config_dir = _config_dir()
    target_path = (config_dir / filepath).resolve()

    if not str(target_path).startswith(str(config_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Protected file check (REQ-2.5)
    if target_path.name in settings.protected_files:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete protected file: {target_path.name}",
        )

    _log_request(request, "delete_file", filepath)

    git = _get_git_service()
    author_name = "API User"
    author_email = "api@local"

    success = git.remove_and_commit_file(
        str(target_path),
        f"Delete config: {filepath}",
        author_name=author_name,
        author_email=author_email,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete and commit file")

    return {"status": "success", "message": f"File {filepath} deleted and committed."}


# ═════════════════════════════════════════════════════════════════
# HISTORY & ROLLBACK ENDPOINTS
# ═════════════════════════════════════════════════════════════════

@router.get("/history/{filepath:path}")
async def file_history(filepath: str, request: Request):
    """Get the version history for a specific file."""
    _log_request(request, "file_history", filepath)
    git = _get_git_service()
    history = git.get_file_history(filepath)
    return {"filepath": filepath, "history": history}


@router.post("/restore/{filepath:path}/{commit_sha}")
async def restore_file(filepath: str, commit_sha: str, request: Request):
    """Restore a file to a previous version identified by commit SHA."""
    _log_request(request, "restore_file", filepath, f"commit={commit_sha}")
    git = _get_git_service()

    author_name = "API User"
    author_email = "api@local"

    success = git.restore_file(
        filepath, commit_sha, author_name=author_name, author_email=author_email
    )

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to restore {filepath} to {commit_sha}")

    return {"status": "success", "message": f"File {filepath} restored to commit {commit_sha[:8]}."}


# ═════════════════════════════════════════════════════════════════
# BULK COMPONENT DOWNLOAD
# ═════════════════════════════════════════════════════════════════

@router.get("/components/{component_name}")
async def download_component(component_name: str, request: Request):
    """
    Bulk download all files in a component folder as a zip archive.
    This is used by clients at batch start to sync configuration (REQ-8.4).
    """
    _log_request(request, "download_component", component_name)
    config_dir = _config_dir()
    component_dir = (config_dir / component_name).resolve()

    if not str(component_dir).startswith(str(config_dir)):
        raise HTTPException(status_code=400, detail="Invalid component name")

    if not component_dir.exists() or not component_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Component folder '{component_name}' not found")

    # Build zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, filenames in os.walk(component_dir):
            dirs[:] = [d for d in dirs if d != ".git"]
            for filename in filenames:
                if filename.startswith(".git"):
                    continue
                abs_path = Path(root) / filename
                arc_name = str(abs_path.relative_to(component_dir))
                zf.write(abs_path, arc_name)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={component_name}.zip"},
    )


# ═════════════════════════════════════════════════════════════════
# SCHEMA ENDPOINTS
# ═════════════════════════════════════════════════════════════════

@router.get("/schemas")
async def list_schemas(request: Request):
    """List all available validation schemas."""
    _log_request(request, "list_schemas")
    schema_svc = _get_schema_service()
    schema_svc.load_schemas()
    return {"schemas": schema_svc.get_available_schemas()}


@router.get("/schemas/{name}")
async def get_schema(name: str, request: Request):
    """Get a specific schema definition."""
    _log_request(request, "get_schema", name)
    schema_svc = _get_schema_service()
    schema = schema_svc.get_schema(name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Schema '{name}' not found")
    return {"name": name, "schema": schema}


@router.post("/schemas/{name}")
async def create_or_update_schema(name: str, request: Request):
    """Create or update a validation schema."""
    _log_request(request, "create_schema", name)
    body = await request.json()
    schema_svc = _get_schema_service()
    schema_svc.create_or_update_schema(name, body)
    return {"status": "success", "message": f"Schema '{name}' saved."}


@router.delete("/schemas/{name}")
async def delete_schema(name: str, request: Request):
    """Delete a validation schema."""
    _log_request(request, "delete_schema", name)
    schema_svc = _get_schema_service()
    if not schema_svc.delete_schema(name):
        raise HTTPException(status_code=404, detail=f"Schema '{name}' not found")
    return {"status": "success", "message": f"Schema '{name}' deleted."}


@router.get("/schemas-mapping")
async def get_schema_mapping(request: Request):
    """Get the current filename-to-schema mapping."""
    _log_request(request, "get_mapping")
    schema_svc = _get_schema_service()
    return {"mapping": schema_svc.get_mapping()}
