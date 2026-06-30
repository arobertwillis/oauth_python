"""
Authentication and authorisation module.

This module configures:
1. JWT validation via Microsoft Entra ID (Azure AD) using the
   fastapi-azure-auth library.
2. Group-based authorisation dependencies that can be applied to
   any FastAPI route.

How it works:
- The `azure_scheme` validates incoming Bearer tokens by:
  • Fetching the OIDC discovery document from your tenant
  • Downloading the public signing keys (JWKS)
  • Verifying the token signature, expiry, audience, and issuer
- The `require_groups` factory creates FastAPI dependencies that
  additionally check the `groups` claim in the validated JWT.

Security notes:
- Tokens are NEVER stored server-side — the API is fully stateless.
- JWKS keys are cached and rotated automatically by the library.
- See docs/jwt_security.md for a full explanation.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from fastapi_azure_auth.user import User

from app.config import Settings, get_settings

# ── Azure Auth Scheme ───────────────────────────────────────────
# We initialise this at module level so FastAPI can detect it as an
# OpenAPI security scheme when evaluating route dependencies. This
# is what enables the "Authorize" button in the Swagger UI.

settings = get_settings()

azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
    app_client_id=settings.azure_client_id,
    tenant_id=settings.azure_tenant_id,
    scopes={
        settings.openapi_scope: "Access the API",
    },
)


async def get_current_user(
    user: User = Depends(azure_scheme),
) -> User:
    """
    Dependency that returns the current authenticated user.

    The azure_scheme dependency:
    1. Extracts the Bearer token from the Authorization header
    2. Validates the JWT signature against Microsoft's public keys
    3. Checks token expiry, audience, and issuer
    4. Returns a User object with all decoded claims

    If any validation fails, a 401 Unauthorized is raised automatically.
    """
    return user


def require_groups(allowed_group_ids: list[str]):
    """
    Factory that creates a FastAPI dependency enforcing group membership.

    Usage:
        # Allow only writers:
        @router.post("/items", dependencies=[Depends(require_groups([WRITER_GROUP_ID]))])

        # Allow readers OR writers:
        @router.get("/items", dependencies=[Depends(require_groups([READER_ID, WRITER_ID]))])

    Args:
        allowed_group_ids: List of Azure AD security group Object IDs.
                          The user must belong to at least ONE of these groups.

    Returns:
        A FastAPI dependency function.

    How group claims work:
        When a user authenticates, Azure includes their security group
        Object IDs in the JWT's `groups` claim (an array of GUIDs).
        This function checks that at least one of the user's groups
        matches the allowed list.
    """

    async def _verify_groups(user: User = Depends(get_current_user)) -> User:
        # The `groups` claim contains a list of group Object IDs (GUIDs)
        user_groups: list[str] = getattr(user, "groups", None) or []

        if not any(group_id in user_groups for group_id in allowed_group_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have the required group membership to access "
                    "this resource. Contact your administrator to be added to "
                    "the appropriate security group."
                ),
            )
        return user

    return _verify_groups


# ── Convenience Dependencies ───────────────────────────────────
# These are pre-built dependencies for the two access levels used
# in this application. Import and use them directly in routes.


def require_read_access():
    """
    Dependency allowing users in EITHER the reader or writer group.

    Writers can do everything readers can, so both groups are allowed.
    """
    settings = get_settings()
    return require_groups(settings.all_group_ids)


def require_write_access():
    """
    Dependency allowing ONLY users in the writer group.
    """
    settings = get_settings()
    return require_groups([settings.azure_writer_group_id])
