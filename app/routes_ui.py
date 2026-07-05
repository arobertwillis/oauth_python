from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path

from app.services.schema_service import schema_service

router = APIRouter(tags=["UI"])

# Setup Jinja2 templates directory
templates = Jinja2Templates(directory="app/ui/templates")

CONFIG_DIR = Path("data/master_config").resolve()

@router.get("/config", response_class=HTMLResponse)
async def config_dashboard(request: Request):
    """
    Renders the Master Configuration UI dashboard.
    Note: For simplicity in this demo, the UI doesn't strictly enforce Azure AD login on the initial page load, 
    but the REST API calls made from the UI *do* require a token if security is enabled.
    """
    files = []
    if CONFIG_DIR.exists():
        for root, _, filenames in os.walk(CONFIG_DIR):
            for filename in filenames:
                if filename == ".gitkeep" or filename == ".git":
                    continue
                abs_path = Path(root) / filename
                rel_path = abs_path.relative_to(CONFIG_DIR)
                files.append(str(rel_path))
    
    schema_service.load_schemas()
    schemas = schema_service.get_available_schemas()
    
    return templates.TemplateResponse(
        "config_ui.html", 
        {"request": request, "files": sorted(files), "schemas": sorted(schemas)}
    )
