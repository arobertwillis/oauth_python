# JWT Security Guide

This document explains the security practices used in this application for
handling JSON Web Tokens (JWTs) issued by Microsoft Entra ID.

---

## Table of Contents

1. [What Is a JWT?](#1-what-is-a-jwt)
2. [The OAuth2 Flow: Authorization Code + PKCE](#2-the-oauth2-flow-authorization-code--pkce)
3. [How Token Validation Works](#3-how-token-validation-works)
4. [Group-Based Authorisation](#4-group-based-authorisation)
5. [Security Measures in This Application](#5-security-measures-in-this-application)
6. [What Could Go Wrong (and How We Prevent It)](#6-what-could-go-wrong-and-how-we-prevent-it)
7. [Production Checklist](#7-production-checklist)

---

## 1. What Is a JWT?

A JSON Web Token (JWT) is a compact, URL-safe token format used to represent
claims between two parties. It consists of three parts separated by dots:

```
xxxxx.yyyyy.zzzzz
  │       │       │
  │       │       └─ Signature (verifies the token hasn't been tampered with)
  │       └───────── Payload   (contains claims: who the user is, what they can do)
  └───────────────── Header    (algorithm used to sign the token)
```

### Example Decoded Payload

```json
{
  "aud": "api://12345678-abcd-efgh-ijkl-123456789012",
  "iss": "https://login.microsoftonline.com/your-tenant-id/v2.0",
  "sub": "user-object-id",
  "name": "API Writer",
  "preferred_username": "writer@yourdomain.onmicrosoft.com",
  "groups": [
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  ],
  "exp": 1735689600,
  "iat": 1735686000
}
```

Key claims explained:

| Claim | Meaning |
|---|---|
| `aud` (audience) | Who the token is intended for (your API's client ID) |
| `iss` (issuer) | Who issued the token (Microsoft Entra ID) |
| `sub` (subject) | Unique identifier of the user |
| `name` | Display name of the user |
| `groups` | Array of security group Object IDs the user belongs to |
| `exp` (expiry) | When the token expires (Unix timestamp, typically 1 hour) |
| `iat` (issued at) | When the token was issued |

---

## 2. The OAuth2 Flow: Authorization Code + PKCE

This application uses the **Authorization Code flow with PKCE** (Proof Key for
Code Exchange). This is the most secure OAuth2 flow for browser-based clients.

### Why Not Other Flows?

| Flow | Used Here? | Why / Why Not |
|---|---|---|
| **Auth Code + PKCE** | ✅ Yes | Most secure for public clients (browsers). No secrets in the browser. |
| **Implicit** | ❌ No | Deprecated. Tokens exposed in URL fragments. No refresh tokens. |
| **Client Credentials** | ❌ No | For service-to-service only. No user involved. |
| **Resource Owner Password** | ❌ No | Sends passwords directly. Cannot support MFA. Insecure. |

### How PKCE Works (Step by Step)

```
1. Browser generates a random "code_verifier" (a long random string)
2. Browser hashes it to create a "code_challenge" (SHA-256)
3. Browser redirects to Microsoft login with the code_challenge
4. User enters credentials at Microsoft's login page
   (Your app NEVER sees the password)
5. Microsoft redirects back with an "authorization code"
6. Browser sends the authorization code + original code_verifier to Microsoft
7. Microsoft verifies: SHA-256(code_verifier) == code_challenge
8. If valid, Microsoft returns an access token (JWT)
9. Browser sends the JWT to your API in the Authorization header
```

### Why PKCE Is Secure

- **No client secret in the browser**: Unlike the basic Authorization Code flow,
  PKCE doesn't require a secret. This is important because anything in a browser
  is visible to the user and potentially to malicious scripts.
- **Code exchange is protected**: Even if an attacker intercepts the authorization
  code, they can't exchange it for a token without the code_verifier (which was
  never sent over the network).
- **Passwords never touch your app**: Users authenticate directly with Microsoft.
  Your API never sees, handles, or stores passwords.

---

## 3. How Token Validation Works

When your API receives a request with a Bearer token, here's what happens:

### Step 1: Extract the Token

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

The `fastapi-azure-auth` library extracts the token from the `Authorization` header.

### Step 2: Fetch Microsoft's Public Keys (JWKS)

Microsoft publishes its public signing keys at a well-known URL:

```
https://login.microsoftonline.com/{tenant-id}/discovery/v2.0/keys
```

These keys are **cached** by the library and automatically rotated when Microsoft
updates them (typically every 24 hours). Your API never needs to store any
Microsoft secrets.

### Step 3: Verify the Signature

The token's signature is verified using Microsoft's public RSA key:

1. Take the token header + payload
2. Apply the RSA-SHA256 algorithm using Microsoft's public key
3. Compare the result with the token's signature

If they don't match, the token was tampered with → **401 Unauthorized**

### Step 4: Validate Claims

After signature verification, the library checks:

| Check | What It Verifies | Failure Result |
|---|---|---|
| **Audience** (`aud`) | Token was issued for YOUR API, not some other app | 401 |
| **Issuer** (`iss`) | Token came from YOUR Azure tenant, not an attacker's | 401 |
| **Expiry** (`exp`) | Token hasn't expired (typically valid for 1 hour) | 401 |
| **Not Before** (`nbf`) | Token isn't being used before it's valid | 401 |

### Step 5: Return User Claims

If all checks pass, the decoded claims are returned as a `User` object that your
route handlers can use.

---

## 4. Group-Based Authorisation

After authentication (proving WHO the user is), we do authorisation (checking
WHAT they can do) using Azure security groups.

### How It Works

1. When a user authenticates, Azure includes their group Object IDs in the
   JWT's `groups` claim
2. Our API checks if any of the user's groups match the required groups for
   the endpoint
3. If the user is in an allowed group → access granted
4. If not → **403 Forbidden**

### Access Level Matrix

| Group | Can Read (`GET`) | Can Write (`POST/PUT/DELETE`) |
|---|---|---|
| `api-readers` | ✅ | ❌ |
| `api-writers` | ✅ | ✅ |
| Neither group | ❌ | ❌ |

### Groups vs App Roles

This API uses **both** Security Groups and App Roles to authorise requests, depending on *who* or *what* is making the request:

| Feature | Security Groups (Humans) | App Roles (Machines) |
|---|---|---|
| **Used for** | Human users (Swagger UI, Web Apps) | Automated scripts, daemons, background jobs |
| **Token Claim** | `groups` claim | `roles` claim |
| **Management** | Azure Portal / Azure CLI | App Registration manifest |
| **Flow** | Authorization Code Flow (PKCE) | Client Credentials Flow |

**Why the split?**
- **Security Groups** are universally understood by administrators for managing human access, and work identically on the free tier.
- **App Roles (Application Permissions)** are the OAuth2 standard for machine-to-machine authentication (Client Credentials Flow). When a script requests a token as a "Service Principal", Azure AD issues the token with the `roles` claim rather than the `groups` claim.

Our FastAPI authorization logic (`app/auth.py`) is built to seamlessly accept EITHER a valid Group Object ID OR a valid App Role, allowing the API to serve both human users and automated scripts simultaneously.

---

## 5. Security Measures in This Application

### ✅ Stateless Architecture

The API stores **nothing** about user sessions. Every request is independently
validated using the JWT. This means:
- No session cookies to steal
- No session store to compromise
- Horizontal scaling works without session affinity

### ✅ No Secrets in the Browser

PKCE eliminates the need for a client secret in the browser. The Swagger UI
only uses the client ID (which is public) and a dynamically generated PKCE
code verifier.

### ✅ Secrets in Environment Variables

All sensitive configuration (tenant ID, client ID, group IDs) is loaded from
environment variables via a `.env` file. The `.gitignore` prevents `.env` from
being committed to source control.

### ✅ Automatic Key Rotation

Microsoft rotates its token signing keys periodically. The `fastapi-azure-auth`
library handles this automatically — it re-fetches keys when it encounters a
token signed with an unknown key ID.

### ✅ Token Expiry

Azure access tokens expire after **1 hour** by default. This limits the window
of opportunity if a token is somehow compromised.

### ✅ Audience Validation

The API only accepts tokens intended for `api://<your-client-id>`. A token
issued for a different Azure application will be rejected, even if it was
signed by Microsoft.

### ✅ Issuer Validation

Tokens must be issued by your specific Azure tenant. Tokens from other tenants
(even legitimate Microsoft tenants) are rejected.

### ✅ CORS Restrictions

Cross-Origin Resource Sharing (CORS) is configured to only allow requests from
known origins (localhost during development). In production, this should be
restricted to your actual frontend domain.

---

## 6. What Could Go Wrong (and How We Prevent It)

### Token Theft (Man-in-the-Middle)

**Risk:** An attacker intercepts the JWT in transit.
**Prevention:**
- Always use **HTTPS** in production (tokens are sent in HTTP headers)
- In development, tokens are only sent to `localhost`
- Tokens expire after 1 hour, limiting damage

### Token Replay

**Risk:** An attacker captures a valid token and re-uses it.
**Prevention:**
- Tokens have short expiry (1 hour)
- Audience validation ensures tokens can only be used against your API
- Use HTTPS to prevent interception

### Forged Tokens

**Risk:** An attacker creates a fake JWT with elevated permissions.
**Prevention:**
- Tokens are signed with Microsoft's private RSA key
- We verify the signature using Microsoft's published public key
- Without Microsoft's private key, a valid signature cannot be created

### Group Escalation

**Risk:** A user modifies their JWT to add group IDs they don't belong to.
**Prevention:**
- This is the same as forging a token — the signature would be invalid
- Group membership is set by Azure at token issuance time
- The API verifies the signature before reading any claims

### Compromised .env File

**Risk:** An attacker gets your `.env` file.
**Impact:** They would know your tenant ID, client ID, and group IDs — but these
are NOT secrets that grant access. They still can't create valid tokens without
authenticating through Microsoft.
**Prevention:** The `.gitignore` excludes `.env` from source control.

---

## 7. Production Checklist

Before deploying to production, ensure:

- [ ] **HTTPS everywhere**: Configure TLS/SSL. Never send JWTs over plain HTTP.
- [ ] **Remove localhost from CORS**: Only allow your actual frontend domain.
- [ ] **Remove localhost from redirect URIs**: Add your production URL to the
  app registration and remove `http://localhost:8000/docs/oauth2-redirect`.
- [ ] **Enable logging**: Log authentication failures for security monitoring.
- [ ] **Consider token caching**: If using a frontend, implement proper token
  refresh to avoid forcing re-login every hour.
- [ ] **Review Conditional Access**: Consider adding Azure Conditional Access
  policies (requires P1 licence) for:
  - Requiring MFA for all users
  - Blocking sign-ins from risky locations
  - Requiring compliant devices
- [ ] **Set up monitoring**: Use Azure Monitor or Application Insights to track
  sign-in activity and detect anomalies.
- [ ] **Regular group reviews**: Periodically audit group membership to ensure
  only authorised users have access.
- [ ] **Secret scanning**: Enable GitHub secret scanning (or equivalent) to
  catch accidentally committed credentials.
