"""
FastAPI application entry point.

This module:
1. Creates the FastAPI app with OAuth2/PKCE-enabled Swagger UI
2. Configures CORS for local development
3. Manages the OIDC/JWKS lifecycle (key loading on startup)
4. Includes all API routes

Run with:
    uvicorn app.main:app --reload

Then open http://localhost:8000/docs to authenticate via Swagger UI.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import azure_scheme
from app.config import get_settings
from app.routes import router


# ── Lifespan ────────────────────────────────────────────────────
# The lifespan context manager runs code at startup and shutdown.
# We use it to load the OIDC configuration and JWKS signing keys
# from Microsoft's servers, so JWT validation is ready before the
# first request arrives.


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Startup:
      - Fetches OIDC discovery document and JWKS keys from Microsoft

    Shutdown:
      - (nothing to clean up — stateless architecture)
    """

    # Load OpenID Connect metadata and signing keys from Microsoft.
    # This makes an HTTPS call to:
    #   https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration
    # and caches the response. Keys are automatically rotated.
    await azure_scheme.openid_config.load_config()

    yield  # Application runs here

    # Shutdown — nothing to clean up


# ── App Creation ────────────────────────────────────────────────


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    The Swagger UI is configured with OAuth2 Authorization Code + PKCE
    so you can authenticate directly from the /docs page.
    """
    settings = get_settings()

    application = FastAPI(
        title=settings.app_title,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
        # ── Swagger UI OAuth2 Configuration ──
        # This configures the "Authorize" button in Swagger UI to use
        # the Authorization Code flow with PKCE (Proof Key for Code Exchange).
        # PKCE is the secure standard for public clients — no client secret
        # is sent to the browser.
        swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",
        swagger_ui_init_oauth={
            # Use PKCE — the browser generates a random code verifier/challenge
            # pair, so no client secret is needed in the browser.
            "usePkceWithAuthorizationCodeGrant": True,
            # The client ID for the SPA redirect (same app registration).
            "clientId": settings.azure_client_id,
            # The scope to request — this determines what the token grants access to.
            "scopes": settings.openapi_scope,
        },
    )

    # ── CORS Middleware ──
    # Allow requests from local development frontends.
    # In production, restrict this to your actual frontend domain.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # React/Next.js default
            "http://localhost:5173",  # Vite default
            "http://localhost:8000",  # Same-origin (Swagger UI)
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──
    application.include_router(router)

    return application


# Create the app instance — this is what uvicorn imports
app = create_app()
