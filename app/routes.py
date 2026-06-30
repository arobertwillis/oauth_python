"""
API routes demonstrating group-based authorisation.

Routes are divided into three access levels:
- Public:  No authentication required (health check)
- Read:    Requires membership in the api-readers OR api-writers group
- Write:   Requires membership in the api-writers group ONLY

The in-memory "items" store is for demonstration purposes.
Replace it with a real database in production.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_azure_auth.user import User
from pydantic import BaseModel, Field

from app.auth import get_current_user, require_read_access, require_write_access

# ── Pydantic Models ─────────────────────────────────────────────


class ItemCreate(BaseModel):
    """Request body for creating a new item."""

    name: str = Field(..., min_length=1, max_length=200, examples=["My Item"])
    description: str = Field(
        default="", max_length=1000, examples=["A description of the item"]
    )


class ItemUpdate(BaseModel):
    """Request body for updating an existing item."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class ItemResponse(BaseModel):
    """Response body for an item."""

    id: str
    name: str
    description: str
    created_by: str


# ── In-Memory Store (replace with a real database) ──────────────

_items: dict[str, ItemResponse] = {}

# ── Router ──────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["API"])


# ── Public Endpoints ────────────────────────────────────────────


@router.get(
    "/public",
    summary="Health check",
    response_model=dict,
)
async def health_check():
    """
    Public endpoint — no authentication required.

    Use this to verify the API is running.
    """
    return {
        "status": "healthy",
        "message": "API is running. Authenticate via /docs to access protected endpoints.",
    }


# ── Authenticated (any group) ──────────────────────────────────


@router.get(
    "/me",
    summary="Current user info",
    response_model=dict,
    dependencies=[Depends(require_read_access())],
)
async def get_current_user_info(user: User = Depends(get_current_user)):
    """
    Returns the authenticated user's JWT claims.

    Useful for debugging — see exactly what Azure included in your token,
    including your group memberships, name, email, etc.
    """
    return {
        "name": user.name,
        "preferred_username": getattr(user, "preferred_username", None),
        "oid": str(user.oid) if user.oid else None,
        "groups": getattr(user, "groups", []),
        "claims": user.claims if hasattr(user, "claims") else {},
    }


# ── Read Endpoints (api-readers + api-writers) ──────────────────


@router.get(
    "/items",
    summary="List all items",
    response_model=list[ItemResponse],
    dependencies=[Depends(require_read_access())],
)
async def list_items():
    """
    List all items. Requires read access (api-readers or api-writers group).
    """
    return list(_items.values())


@router.get(
    "/items/{item_id}",
    summary="Get a single item",
    response_model=ItemResponse,
    dependencies=[Depends(require_read_access())],
)
async def get_item(item_id: str):
    """
    Get a single item by ID. Requires read access.
    """
    if item_id not in _items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found.",
        )
    return _items[item_id]


# ── Write Endpoints (api-writers only) ──────────────────────────


@router.post(
    "/items",
    summary="Create an item",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access())],
)
async def create_item(
    item: ItemCreate,
    user: User = Depends(get_current_user),
):
    """
    Create a new item. Requires write access (api-writers group only).

    The item is tagged with the creating user's name from their JWT.
    """
    item_id = str(uuid4())
    new_item = ItemResponse(
        id=item_id,
        name=item.name,
        description=item.description,
        created_by=user.name or "unknown",
    )
    _items[item_id] = new_item
    return new_item


@router.put(
    "/items/{item_id}",
    summary="Update an item",
    response_model=ItemResponse,
    dependencies=[Depends(require_write_access())],
)
async def update_item(item_id: str, item: ItemUpdate):
    """
    Update an existing item. Requires write access (api-writers group only).
    """
    if item_id not in _items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found.",
        )

    existing = _items[item_id]

    if item.name is not None:
        existing = existing.model_copy(update={"name": item.name})
    if item.description is not None:
        existing = existing.model_copy(update={"description": item.description})

    _items[item_id] = existing
    return existing


@router.delete(
    "/items/{item_id}",
    summary="Delete an item",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_write_access())],
)
async def delete_item(item_id: str):
    """
    Delete an item. Requires write access (api-writers group only).
    """
    if item_id not in _items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found.",
        )
    del _items[item_id]
