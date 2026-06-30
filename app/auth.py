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


def require_permissions(allowed_group_ids: list[str], allowed_roles: list[str]):
    """
    Factory that creates a FastAPI dependency enforcing group OR role membership.

    Args:
        allowed_group_ids: List of Azure AD security group Object IDs (for human users).
        allowed_roles: List of Azure AD App Roles (for automated Service Principals).

    Returns:
        A FastAPI dependency function.

    How it works:
        - Human users get a `groups` claim containing their Security Group IDs.
        - Automated scripts (Client Credentials) get a `roles` claim with their App Roles.
        This checks if the caller has AT LEAST ONE valid group OR role.
    """

    async def _verify_permissions(user: User = Depends(get_current_user)) -> User:
        user_groups: list[str] = getattr(user, "groups", None) or []
        user_roles: list[str] = getattr(user, "roles", None) or []

        has_group = any(group_id in user_groups for group_id in allowed_group_ids)
        has_role = any(role in user_roles for role in allowed_roles)

        if not (has_group or has_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have the required permissions to access this resource. "
                    "Ensure you are in the correct security group (for users) or have "
                    "been granted the correct App Role (for applications)."
                ),
            )
        return user

    return _verify_permissions


# ── Convenience Dependencies ───────────────────────────────────
# These are pre-built dependencies for the two access levels used
# in this application. Import and use them directly in routes.


def require_read_access():
    """
    Dependency allowing users in EITHER the reader or writer group,
    OR service principals with the Read or Write App Roles.
    """
    settings = get_settings()
    return require_permissions(
        allowed_group_ids=settings.all_group_ids,
        allowed_roles=["Items.Read.All", "Items.Write.All"]
    )


def require_write_access():
    """
    Dependency allowing ONLY users in the writer group,
    OR service principals with the Write App Role.
    """
    settings = get_settings()
    return require_permissions(
        allowed_group_ids=[settings.azure_writer_group_id],
        allowed_roles=["Items.Write.All"]
    )
