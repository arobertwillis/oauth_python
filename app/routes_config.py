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

from app.auth import require_read_access, require_write_access, get_current_user

read_access_dep = require_read_access()
write_access_dep = require_write_access()


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

@router.get("/files", dependencies=[Depends(read_access_dep)])
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


@router.get("/files/{filepath:path}", dependencies=[Depends(read_access_dep)])
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


@router.post("/files/{filepath:path}", dependencies=[Depends(write_access_dep)])
async def upload_file(
    filepath: str,
    request: Request,
    file: UploadFile = File(...),
    schema_name: Optional[str] = Form(None),
    user=Depends(get_current_user),
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
    if user:
        author_name, author_email = _extract_author(user)
    else:
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


@router.delete("/files/{filepath:path}", dependencies=[Depends(write_access_dep)])
async def delete_file(
    filepath: str,
    request: Request,
    user=Depends(get_current_user),
):
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
    if user:
        author_name, author_email = _extract_author(user)
    else:
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

@router.get("/history/{filepath:path}", dependencies=[Depends(read_access_dep)])
async def file_history(filepath: str, request: Request):
    """Get the version history for a specific file."""
    _log_request(request, "file_history", filepath)
    git = _get_git_service()
    history = git.get_file_history(filepath)
    return {"filepath": filepath, "history": history}


@router.post("/restore/{filepath:path}/{commit_sha}", dependencies=[Depends(write_access_dep)])
async def restore_file(
    filepath: str,
    commit_sha: str,
    request: Request,
    user=Depends(get_current_user),
):
    """Restore a file to a previous version identified by commit SHA."""
    _log_request(request, "restore_file", filepath, f"commit={commit_sha}")
    git = _get_git_service()

    if user:
        author_name, author_email = _extract_author(user)
    else:
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

@router.get("/components/{component_name}", dependencies=[Depends(read_access_dep)])
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

@router.get("/schemas", dependencies=[Depends(read_access_dep)])
async def list_schemas(request: Request):
    """List all available validation schemas."""
    _log_request(request, "list_schemas")
    schema_svc = _get_schema_service()
    schema_svc.load_schemas()
    return {"schemas": schema_svc.get_available_schemas()}


@router.get("/schemas/{name}", dependencies=[Depends(read_access_dep)])
async def get_schema(name: str, request: Request):
    """Get a specific schema definition."""
    _log_request(request, "get_schema", name)
    schema_svc = _get_schema_service()
    schema = schema_svc.get_schema(name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Schema '{name}' not found")
    return {"name": name, "schema": schema}


@router.post("/schemas/{name}", dependencies=[Depends(write_access_dep)])
async def create_or_update_schema(name: str, request: Request):
    """Create or update a validation schema."""
    _log_request(request, "create_schema", name)
    body = await request.json()
    schema_svc = _get_schema_service()
    schema_svc.create_or_update_schema(name, body)
    return {"status": "success", "message": f"Schema '{name}' saved."}


@router.delete("/schemas/{name}", dependencies=[Depends(write_access_dep)])
async def delete_schema(name: str, request: Request):
    """Delete a validation schema."""
    _log_request(request, "delete_schema", name)
    schema_svc = _get_schema_service()
    if not schema_svc.delete_schema(name):
        raise HTTPException(status_code=404, detail=f"Schema '{name}' not found")
    return {"status": "success", "message": f"Schema '{name}' deleted."}


@router.get("/schemas-mapping", dependencies=[Depends(read_access_dep)])
async def get_schema_mapping(request: Request):
    """Get the current filename-to-schema mapping."""
    _log_request(request, "get_mapping")
    schema_svc = _get_schema_service()
    return {"mapping": schema_svc.get_mapping()}


# ═════════════════════════════════════════════════════════════════
# DEPLOYMENT ENDPOINTS (REQ-6)
# ═════════════════════════════════════════════════════════════════

@router.post("/deploy/diff", dependencies=[Depends(read_access_dep)])
async def deploy_diff(
    request: Request,
    file: UploadFile = File(...),
):
    """
    Dry-run deployment. Analyzes the uploaded ZIP of configuration files
    and compares it to the target environment's repository.
    Flags any conflicts where target files have been edited by end-users.
    """
    _log_request(request, "deploy_diff")
    content_bytes = await file.read()
    
    settings = get_settings()
    if len(content_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Deployment package exceeds maximum upload size",
        )

    config_dir = _config_dir()
    git = _get_git_service()

    try:
        zf = zipfile.ZipFile(io.BytesIO(content_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")

    changes = []
    
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        
        target_path = (config_dir / name).resolve()
        if not str(target_path).startswith(str(config_dir)):
            continue

        try:
            incoming_content = zf.read(name)
        except Exception:
            continue

        status_val = "UNCHANGED"
        last_modified_by = "System"
        last_modified_at = None

        if target_path.exists() and target_path.is_file():
            with open(target_path, "rb") as f:
                existing_content = f.read()

            if incoming_content != existing_content:
                history = git.get_file_history(name, max_count=1)
                if history:
                    last_commit = history[0]
                    last_modified_by = last_commit["author_name"]
                    last_modified_at = last_commit["date"]
                    email = last_commit["author_email"]
                    # End-user modification check (non-system commit)
                    if not email.endswith("@local") and email != "api@local":
                        status_val = "CONFLICT"
                    else:
                        status_val = "MODIFIED"
                else:
                    status_val = "MODIFIED"
        else:
            status_val = "NEW"

        changes.append({
            "path": name,
            "status": status_val,
            "last_modified_by": last_modified_by,
            "last_modified_at": last_modified_at,
        })

    return {"status": "success", "changes": changes}


@router.post("/deploy/apply", dependencies=[Depends(write_access_dep)])
async def deploy_apply(
    request: Request,
    file: UploadFile = File(...),
    resolutions: str = Form("{}"),
    user=Depends(get_current_user),
):
    """
    Apply a deployment package. Overwrites target configuration files except
    for conflicted files marked as KEEP_EXISTING.
    """
    import json
    _log_request(request, "deploy_apply")
    content_bytes = await file.read()
    
    settings = get_settings()
    if len(content_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail="Deployment package exceeds maximum upload size",
        )

    try:
        res_dict = json.loads(resolutions)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid resolutions JSON")

    config_dir = _config_dir()
    git = _get_git_service()

    try:
        zf = zipfile.ZipFile(io.BytesIO(content_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")

    if user:
        author_name, author_email = _extract_author(user)
    else:
        author_name = "Deploy System"
        author_email = "deploy@local"

    to_commit = []
    backups = {}
    
    try:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            
            target_path = (config_dir / name).resolve()
            if not str(target_path).startswith(str(config_dir)):
                continue

            incoming_content = zf.read(name)
            
            is_conflict = False
            if target_path.exists() and target_path.is_file():
                with open(target_path, "rb") as f:
                    existing_content = f.read()
                
                if incoming_content != existing_content:
                    history = git.get_file_history(name, max_count=1)
                    if history:
                        email = history[0]["author_email"]
                        if not email.endswith("@local") and email != "api@local":
                            is_conflict = True

            if is_conflict:
                resolution = res_dict.get(name)
                if resolution == "KEEP_EXISTING":
                    continue
                elif resolution == "ACCEPT_INCOMING":
                    pass
                else:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Conflict detected on '{name}' with no resolution specified (ACCEPT_INCOMING or KEEP_EXISTING required)",
                    )

            # Enforce max size limit per file
            if len(incoming_content) > settings.max_upload_size_bytes:
                raise HTTPException(status_code=413, detail=f"File {name} exceeds max size")

            # Backup for manual rollback if git fails
            if target_path.exists():
                with open(target_path, "rb") as f:
                    backups[name] = f.read()
            else:
                backups[name] = None

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(incoming_content)

            to_commit.append(str(target_path))

        if to_commit:
            success = git.commit_multiple_files(
                to_commit,
                "Apply deployment configuration package",
                author_name=author_name,
                author_email=author_email,
            )
            if not success:
                # Rollback files manually to working state
                for name, prev_content in backups.items():
                    target_path = config_dir / name
                    if prev_content is not None:
                        with open(target_path, "wb") as f:
                            f.write(prev_content)
                    elif target_path.exists():
                        target_path.unlink()
                raise HTTPException(status_code=500, detail="Git deployment commit failed — target rolled back")

        return {"status": "success", "message": f"Deployment applied successfully. {len(to_commit)} files updated."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Deploy apply unexpected error: %s", e)
        # Rollback files manually to working state
        for name, prev_content in backups.items():
            target_path = config_dir / name
            if prev_content is not None:
                with open(target_path, "wb") as f:
                    f.write(prev_content)
            elif target_path.exists():
                target_path.unlink()
        raise HTTPException(status_code=500, detail=f"Unexpected deployment failure: {str(e)}")
