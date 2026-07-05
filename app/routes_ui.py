from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path

from app.services.schema_service import SchemaService
from app.config import get_settings

router = APIRouter(tags=["UI"])

# Setup Jinja2 templates directory
templates = Jinja2Templates(directory="app/ui/templates")

@router.get("/config", response_class=HTMLResponse)
async def config_dashboard(request: Request):
    """
    Renders the Master Configuration UI dashboard.
    """
    settings = get_settings()
    config_dir = Path(settings.master_config_dir).resolve()
    
    files = []
    if config_dir.exists():
        for root, dirs, filenames in os.walk(config_dir):
            dirs[:] = [d for d in dirs if d != ".git"]
            for filename in filenames:
                if filename.startswith(".git"):
                    continue
                abs_path = Path(root) / filename
                rel_path = abs_path.relative_to(config_dir)
                files.append(str(rel_path))
    
    schema_service = SchemaService(
        schemas_dir=settings.schemas_dir,
        mapping_file=settings.schema_mapping_file,
    )
    schema_service.load_schemas()
    schemas = schema_service.get_available_schemas()
    
    return templates.TemplateResponse(
        request=request,
        name="config_ui.html", 
        context={
            "request": request, 
            "files": sorted(files), 
            "schemas": sorted(schemas),
            "azure_client_id": settings.azure_client_id,
            "azure_tenant_id": settings.azure_tenant_id,
        }
    )
