# Azure Entra ID Setup Guide

This guide walks you through setting up Microsoft Entra ID (formerly Azure AD)
to authenticate users for the FastAPI OAuth Python API.

**Everything in this guide uses the free tier of Entra ID — there is no cost.**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Create the App Registration](#2-create-the-app-registration)
3. [Configure the App Registration](#3-configure-the-app-registration)
4. [Expose an API Scope](#4-expose-an-api-scope)
5. [Configure the Manifest](#5-configure-the-manifest)
6. [Create Security Groups](#6-create-security-groups)
7. [Create Test Users](#7-create-test-users)
8. [Assign Users to Groups](#8-assign-users-to-groups)
9. [Assign Groups to the Enterprise App](#9-assign-groups-to-the-enterprise-app)
10. [Collect Configuration Values](#10-collect-configuration-values)
11. [Setup Service-to-Service Authentication (Optional)](#11-setup-service-to-service-authentication-optional)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

- An **Azure account** (free tier is sufficient)
- Access to the **Azure Portal**: https://portal.azure.com
- **Azure CLI** installed (optional, but commands are provided): https://learn.microsoft.com/en-us/cli/azure/install-azure-cli

### Login to Azure CLI (if using CLI)

```bash
az login
```

### Find Your Tenant ID

**Portal:** Azure Portal → Microsoft Entra ID → Overview → **Tenant ID**

**CLI:**
```bash
az account show --query tenantId --output tsv
```

> **Save this value** — you'll need it for the `.env` file as `AZURE_TENANT_ID`.

---

## 2. Create the App Registration

The app registration tells Azure about your application — what it is, who can
sign in, and what permissions it needs.

### Portal

1. Go to **Azure Portal** → **Microsoft Entra ID** → **App registrations**
2. Click **+ New registration**
3. Fill in:
   - **Name:** `OAuth Python API`
   - **Supported account types:** "Accounts in this organizational directory only" (Single tenant)
   - **Redirect URI:** Select **Single-page application (SPA)** and enter:
     ```
     http://localhost:8000/docs/oauth2-redirect
     ```
4. Click **Register**

### CLI

```bash
az ad app create \
  --display-name "OAuth Python API" \
  --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "http://localhost:8000/docs/oauth2-redirect"
```

> **Note:** The CLI command above creates a "web" redirect. You'll need to change
> it to SPA type in the Portal (see step 3 below) or use the Graph API.

### Save the Application (Client) ID

**Portal:** After registration, you'll see the **Application (client) ID** on the Overview page.

**CLI:**
```bash
az ad app list --display-name "OAuth Python API" --query "[0].appId" --output tsv
```

> **Save this value** — you'll need it for the `.env` file as `AZURE_CLIENT_ID`.

---

## 3. Configure the App Registration

### Set the Redirect URI Platform to SPA

This is critical — it must be **SPA** (not Web) to enable PKCE without a client secret.

1. Go to your app registration → **Authentication**
2. Under **Platform configurations**, you should see your redirect URI
3. If it's listed under "Web", delete it and click **+ Add a platform** → **Single-page application**
4. Enter: `http://localhost:8000/docs/oauth2-redirect`
5. Click **Configure**

### Verify Settings

On the **Authentication** page, ensure:
- ✅ **Access tokens** is checked under "Implicit grant and hybrid flows" → **No, leave unchecked** (we use PKCE, not implicit flow)
- ✅ The redirect URI is listed under **Single-page application**
- ✅ "Supported account types" is "Accounts in this organizational directory only"

---

## 4. Expose an API Scope

This creates a permission scope that tokens can be issued for. Without this,
Azure won't include the correct `aud` (audience) claim in the access token.

### Portal

1. Go to your app registration → **Expose an API**
2. Click **+ Add a scope**
3. If prompted for an **Application ID URI**, accept the default (`api://<client-id>`) and click **Save and continue**
4. Fill in the scope:
   - **Scope name:** `access_as_user`
   - **Who can consent:** "Admins and users"
   - **Admin consent display name:** "Access OAuth Python API"
   - **Admin consent description:** "Allows the user to access the OAuth Python API"
   - **User consent display name:** "Access OAuth Python API"
   - **User consent description:** "Allows you to access the OAuth Python API"
   - **State:** Enabled
5. Click **Add scope**

### CLI

```bash
# Get the app's object ID (not the same as client ID)
APP_OBJECT_ID=$(az ad app list --display-name "OAuth Python API" --query "[0].id" --output tsv)
CLIENT_ID=$(az ad app list --display-name "OAuth Python API" --query "[0].appId" --output tsv)

# Set the Application ID URI
az ad app update --id $APP_OBJECT_ID --identifier-uris "api://$CLIENT_ID"
```

> For the scope itself, it's easiest to use the Portal. The CLI for OAuth2 permission
> scopes is complex and error-prone.

### Grant API Permission to Itself

1. Go to your app registration → **API permissions**
2. Click **+ Add a permission** → **My APIs** → select **OAuth Python API**
3. Check **access_as_user** → **Add permissions**
4. Click **Grant admin consent for [your tenant]** (requires admin role)

---

## 5. Configure the Manifest

The manifest controls what claims appear in tokens. We need to ensure:
- Tokens use the **v2** endpoint
- **Security group IDs** are included in the token

### Portal

1. Go to your app registration → **Manifest**
2. Find and update these values:

```json
{
    "accessTokenAcceptedVersion": 2,
    "groupMembershipClaims": "SecurityGroup"
}
```

3. Click **Save**

### CLI

```bash
APP_OBJECT_ID=$(az ad app list --display-name "OAuth Python API" --query "[0].id" --output tsv)

# Set token version to v2
az ad app update --id $APP_OBJECT_ID --set api.requestedAccessTokenVersion=2

# Note: groupMembershipClaims may need to be set via the Portal or Graph API
```

### What These Do

| Property | Value | Purpose |
|---|---|---|
| `accessTokenAcceptedVersion` | `2` | Uses the modern v2 token format with standard JWT claims |
| `groupMembershipClaims` | `"SecurityGroup"` | Includes the user's security group Object IDs in the `groups` claim of the JWT |

---

## 6. Create Security Groups

We create two security groups:
- **api-readers**: Users who can read data (GET requests)
- **api-writers**: Users who can read AND write data (GET, POST, PUT, DELETE)

### Portal

1. Go to **Microsoft Entra ID** → **Groups** → **+ New group**
2. For the **first group**:
   - **Group type:** Security
   - **Group name:** `api-readers`
   - **Group description:** "Users with read-only access to the OAuth Python API"
   - **Membership type:** Assigned
   - Click **Create**
3. For the **second group**:
   - **Group type:** Security
   - **Group name:** `api-writers`
   - **Group description:** "Users with read and write access to the OAuth Python API"
   - **Membership type:** Assigned
   - Click **Create**

### CLI

```bash
# Create the readers group
az ad group create \
  --display-name "api-readers" \
  --mail-nickname "api-readers" \
  --description "Users with read-only access to the OAuth Python API"

# Create the writers group
az ad group create \
  --display-name "api-writers" \
  --mail-nickname "api-writers" \
  --description "Users with read and write access to the OAuth Python API"
```

### Save the Group Object IDs

**Portal:** Click on each group → **Overview** → **Object ID**

**CLI:**
```bash
# Get reader group ID
az ad group show --group "api-readers" --query id --output tsv

# Get writer group ID
az ad group show --group "api-writers" --query id --output tsv
```

> **Save these values** — you'll need them for the `.env` file as
> `AZURE_READER_GROUP_ID` and `AZURE_WRITER_GROUP_ID`.

---

## 7. Create Test Users

Create two test users — one reader and one writer.

> **Important:** Replace `yourdomain.onmicrosoft.com` with your actual
> Azure tenant domain throughout this section.

### Find Your Tenant Domain

**Portal:** Microsoft Entra ID → Overview → **Primary domain**

**CLI:**
```bash
az rest --method get --url 'https://graph.microsoft.com/v1.0/domains' \
  --query "value[?isDefault].id" --output tsv
```

### Portal

1. Go to **Microsoft Entra ID** → **Users** → **+ New user** → **Create new user**
2. For the **reader user**:
   - **User principal name:** `reader@yourdomain.onmicrosoft.com`
   - **Display name:** `API Reader`
   - **Auto-generate password:** Yes (note the password for first login)
   - Click **Review + create** → **Create**
3. For the **writer user**:
   - **User principal name:** `writer@yourdomain.onmicrosoft.com`
   - **Display name:** `API Writer`
   - **Auto-generate password:** Yes (note the password for first login)
   - Click **Review + create** → **Create**

### CLI

```bash
# Create reader user
az ad user create \
  --display-name "API Reader" \
  --user-principal-name "reader@yourdomain.onmicrosoft.com" \
  --password "TempPass123!" \
  --force-change-password-next-sign-in true

# Create writer user
az ad user create \
  --display-name "API Writer" \
  --user-principal-name "writer@yourdomain.onmicrosoft.com" \
  --password "TempPass123!" \
  --force-change-password-next-sign-in true
```

> **Security:** The `--force-change-password-next-sign-in true` flag ensures
> users must change their password on first login. Always use this for new accounts.

---

## 8. Assign Users to Groups

### Portal

1. Go to **Microsoft Entra ID** → **Groups** → **api-readers**
2. Click **Members** → **+ Add members**
3. Search for `API Reader` → Select → **Select**
4. Repeat for **api-writers** group:
   - Go to **api-writers** → **Members** → **+ Add members**
   - Search for `API Writer` → Select → **Select**

### CLI

```bash
# Get user Object IDs
READER_USER_ID=$(az ad user show --id "reader@yourdomain.onmicrosoft.com" --query id --output tsv)
WRITER_USER_ID=$(az ad user show --id "writer@yourdomain.onmicrosoft.com" --query id --output tsv)

# Add reader to api-readers group
az ad group member add --group "api-readers" --member-id $READER_USER_ID

# Add writer to api-writers group
az ad group member add --group "api-writers" --member-id $WRITER_USER_ID
```

### Verify Membership

```bash
# List members of each group
az ad group member list --group "api-readers" --query "[].displayName" --output tsv
az ad group member list --group "api-writers" --query "[].displayName" --output tsv
```

---

## 9. Assign Groups to the Enterprise App

> **This step is critical!** Without it, Azure will NOT include the `groups`
> claim in tokens issued for your application.

When you created the App Registration, Azure automatically created a matching
**Enterprise Application** (also called a Service Principal). You need to assign
your security groups to it.

### Portal

1. Go to **Microsoft Entra ID** → **Enterprise applications**
2. Search for `OAuth Python API` and click on it
3. Go to **Users and groups** → **+ Add user/group**
4. Under **Users and groups**, click "None Selected"
5. Search for `api-readers` → Select → then search for `api-writers` → Select
6. Click **Select** → **Assign**

### CLI

```bash
# Get the Enterprise Application (Service Principal) Object ID
SP_OBJECT_ID=$(az ad sp list --display-name "OAuth Python API" --query "[0].id" --output tsv)

# If no service principal exists, create one:
# az ad sp create --id $CLIENT_ID

# Note: Assigning groups to enterprise apps via CLI requires the Graph API.
# It's much easier to do this in the Portal.
```

### Why This Matters

The Enterprise Application controls which users/groups can obtain tokens
for your app. By assigning groups:
- Only members of those groups can authenticate
- Group Object IDs appear in the JWT `groups` claim
- Your FastAPI app can then check `groups` for authorisation

---

## 10. Collect Configuration Values

After completing all steps above, you should have four values. Create your
`.env` file by copying the template:

```bash
cp .env.example .env
```

Then fill in the values:

```ini
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_READER_GROUP_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_WRITER_GROUP_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### Where to Find Each Value

| Variable | Location |
|---|---|
| `AZURE_TENANT_ID` | Entra ID → Overview → Tenant ID |
| `AZURE_CLIENT_ID` | App registrations → OAuth Python API → Application (client) ID |
| `AZURE_READER_GROUP_ID` | Groups → api-readers → Object ID |
| `AZURE_WRITER_GROUP_ID` | Groups → api-writers → Object ID |

### Quick CLI Collection

```bash
echo "AZURE_TENANT_ID=$(az account show --query tenantId --output tsv)"
echo "AZURE_CLIENT_ID=$(az ad app list --display-name 'OAuth Python API' --query '[0].appId' --output tsv)"
echo "AZURE_READER_GROUP_ID=$(az ad group show --group 'api-readers' --query id --output tsv)"
echo "AZURE_WRITER_GROUP_ID=$(az ad group show --group 'api-writers' --query id --output tsv)"
```

## 11. Setup Service-to-Service Authentication (Optional)

If you have automated scripts that need to access the API without human interaction, you need to configure App Roles and a Client Application.

### 1. Create App Roles on the API Application
1. Go to your `OAuth Python API` app registration → **App roles**.
2. Click **+ Create app role**.
3. Fill in:
   - **Display name:** `Items.Read.All`
   - **Allowed member types:** `Applications`
   - **Value:** `Items.Read.All`
   - **Description:** `Allows reading items`
   - **Do you want to enable this app role:** Yes
4. Repeat to create `Items.Write.All`.

### 2. Create the Client Application
1. Go to **App registrations** → **+ New registration**.
2. Name it `OAuth Python API - CLI Client` and click **Register**.
3. Go to **Certificates & secrets** and create a **New client secret**. Save the value immediately.
4. Go to **API permissions** → **+ Add a permission** → **My APIs**.
5. Select `OAuth Python API` → **Application permissions**.
6. Check `Items.Write.All` and click **Add permissions**.
7. Click **Grant admin consent for [your tenant]** to approve the permission.

You will need the **Tenant ID**, the Client Application's **Client ID**, and the **Client Secret** to authenticate your scripts using the Client Credentials flow.

---

## 12. Troubleshooting

### "AADSTS50011: The redirect URI does not match"

- Ensure the redirect URI in your app registration is **exactly**:
  `http://localhost:8000/docs/oauth2-redirect`
- Ensure the platform type is **SPA** (not Web)
- Check for trailing slashes — Azure is strict about exact matches

### "AADSTS70011: The provided value for the input parameter 'scope' is not valid"

- Ensure you completed step 4 (Expose an API) and created the `access_as_user` scope
- Ensure you granted API permission (step 4, "Grant API Permission to Itself")
- Ensure admin consent was granted

### "groups" claim is missing from the token

- Verify `groupMembershipClaims` is set to `"SecurityGroup"` in the manifest (step 5)
- Verify groups are assigned to the Enterprise Application (step 9)
- Verify the user is actually a member of a group (step 8)
- Use https://jwt.ms to decode your token and inspect the claims

### "Token validation error" in FastAPI

- Verify `accessTokenAcceptedVersion` is `2` in the manifest
- Verify the `AZURE_TENANT_ID` and `AZURE_CLIENT_ID` in `.env` are correct
- Check that the app is running on `http://localhost:8000` (matching the redirect URI)

### Users can't sign in

- New users must change their password on first sign in — they may need to go to
  https://myaccount.microsoft.com first
- MFA may be required depending on your tenant's Conditional Access policies
- The user must be assigned to the Enterprise Application (either directly or via group)

### Decode a Token for Debugging

Paste your access token into https://jwt.ms to see all claims. Look for:
- `aud`: Should be `api://<your-client-id>`
- `iss`: Should be `https://login.microsoftonline.com/<your-tenant-id>/v2.0`
- `groups`: Should contain group Object IDs
- `exp`: Token expiry (Unix timestamp)
