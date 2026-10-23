# Role — m365_app_registration

This role doesn't run anything against M365. It's a documentation
shell: setting up the Azure AD app registration this collection
needs is an interactive operation that requires Global
Administrator privileges. We don't automate it — operators do it
once per tenant.

## What you need to do once per tenant

1. **Sign in to the Microsoft Entra admin center** as a user with
   Global Administrator role:
   `https://entra.microsoft.com → Applications → App registrations`

2. **Click "New registration"** and fill in:
   - Name: `aac-m365-readonly` (or whatever your conventions are)
   - Supported account types: *single tenant*
   - Redirect URI: leave empty (we don't use the user-flow)

3. **Note the IDs.** On the Overview page, copy:
   - **Application (client) ID** → goes into `m365_client_id`
   - **Directory (tenant) ID** → goes into `m365_tenant_id`

4. **Create a client secret.** Certificates & secrets →
   New client secret → set expiry to your rotation cadence (CIS
   recommends ≤ 1 year). Copy the **Value** (NOT the Secret ID).
   → goes into `m365_client_secret`. Store in Ansible Vault.

5. **Grant API permissions.** API permissions → Add a permission
   → Microsoft Graph → **Application permissions** (not Delegated):
   - `Directory.Read.All`
   - `Policy.Read.All`
   - `RoleManagement.Read.Directory`
   - `UserAuthenticationMethod.Read.All`

6. **Click "Grant admin consent for <tenant>"**. This is the step
   most easily forgotten. Without it, the app gets 403 from Graph
   on any of the permissions above.

7. **Store the three values in Ansible Vault.** Suggested layout:

   ```yaml
   # ansible/vars/vault_secrets.yml (encrypted)
   vault_m365_tenant_id:     <tenant guid>
   vault_m365_client_id:     <client guid>
   vault_m365_client_secret: <secret value from step 4>
   ```

   Then reference them in playbooks as `m365_tenant_id: "{{
   vault_m365_tenant_id }}"` etc.

## Verification

After step 6, the simplest smoke test from the operator's machine:

```bash
TENANT_ID=...
CLIENT_ID=...
CLIENT_SECRET=...
TOKEN=$(curl -s "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" \
    -d "grant_type=client_credentials" \
    -d "client_id=$CLIENT_ID" \
    -d "client_secret=$CLIENT_SECRET" \
    -d "scope=https://graph.microsoft.com/.default" | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" \
    "https://graph.microsoft.com/v1.0/policies/identitySecurityDefaultsEnforcementPolicy" | jq .
```

If you see a JSON object with `isEnabled`, the credential chain is
healthy. If you see `403`, admin consent (step 6) is missing.

## Why we don't automate the app registration

The Graph API can in principle automate steps 1–6, but doing so
requires a Global Admin token in the first place, which means
running an interactive flow somewhere. That's strictly more
complex than asking the operator to do it once via the admin
center. If your tenant has many sub-tenants to onboard, look at
Microsoft's `New-AzADApplication` PowerShell flow — it's the
canonical script for bulk provisioning.
