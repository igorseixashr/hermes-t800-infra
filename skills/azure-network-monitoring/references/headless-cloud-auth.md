# Headless Cloud-CLI Authentication on this Hermes Host

Cross-provider patterns for Azure and AWS device-code login when the agent runs in a non-interactive shell. The user's browser is on a different host, so any auth flow that opens a local browser or expects a 127.0.0.1 callback **will not work** — only true device-code flows do.

> Scope note: this lives under `azure-network-monitoring` because the cloud-network-monitoring work that drives most of these auth events lives here. When/if an `aws-network-monitoring` umbrella is created, mirror this file or move it under a shared parent.

## Universal capture pattern

Both Azure and AWS CLIs print the device URL+code to `/dev/tty`, never to stdout/stderr. Background processes started by Hermes therefore see no output. Use `script` to attach a fake TTY whose output gets logged:

```bash
script -qfc '<auth command>' /tmp/<provider>_login.log
```

Then poll the log after ~5s. `setterm: terminal xterm does not support --blank` is harmless noise.

## Azure (`az login`)

```bash
# Background launch with capture
script -qfc 'az login --use-device-code' /tmp/azlogin.log
# (extract URL+code from /tmp/azlogin.log, give to user)
# After user authenticates, az enters an interactive subscription picker if >1 sub:
#   "Select a subscription and tenant (Type a number or Enter for no changes):"
# Send empty input (Enter) via mcp_process action=submit data="" to accept default and exit.
```

Profile defaults persist in `~/.azure/`. Override per-call with `--subscription <id>` or pin globally with `az account set --subscription <id>`.

## AWS (`aws sso login`)

**Critical:** AWS CLI v2 has THREE auth flow modes that look similar but behave differently:

| Invocation                                              | Flow                                  | Works headless?      |
|---------------------------------------------------------|---------------------------------------|----------------------|
| `aws sso login --sso-session <name>`                    | OIDC PKCE w/ 127.0.0.1 callback       | ❌ no                |
| `aws sso login --sso-session <name> --no-browser`       | OIDC PKCE w/ 127.0.0.1 callback       | ❌ no (just suppresses `xdg-open`) |
| `aws sso login --sso-session <name> --use-device-code`  | RFC 8628 device code                  | ✅ yes               |

The CLI prints a helpful hint if it detects the situation: `"run this command again with the '--use-device-code' option"` — but only after you've already failed once. Use `--use-device-code` from the start.

### Setup config first

```bash
mkdir -p ~/.aws
cat > ~/.aws/config <<EOF
[sso-session <name>]
sso_start_url = https://d-XXXXXXXXXX.awsapps.com/start
sso_region = <identity-center-region>          # e.g. us-east-1
sso_registration_scopes = sso:account:access
EOF
```

### Background-safe login

```bash
# Hermes: terminal(background=true) + script wrapper
script -qfc 'aws sso login --sso-session <name> --use-device-code' /tmp/aws_sso.log
# Read /tmp/aws_sso.log after ~6s — it shows:
#   https://<start_url>/#/device
#   Then enter the code:
#   XXXX-XXXX
```

### Generating per-account profiles after login

After SSO login succeeds, the access token is cached in `~/.aws/sso/cache/`. To enumerate accounts and create one CLI profile per account/role:

```bash
ACCESS_TOKEN=$(jq -r .accessToken ~/.aws/sso/cache/$(ls -t ~/.aws/sso/cache/ | head -1))
aws sso list-accounts --access-token "$ACCESS_TOKEN" --region <sso_region> -o json
# For each account, list available roles:
aws sso list-account-roles --access-token "$ACCESS_TOKEN" --account-id <id> --region <sso_region> -o json
# Then write profiles:
cat >> ~/.aws/config <<EOF
[profile <account-name>]
sso_session = <name>
sso_account_id = <id>
sso_role_name = <role>
region = <default region for ops>
output = json
EOF
```

For 50+ accounts, script this loop instead of doing it by hand.

## Killing a stuck OIDC PKCE flow

If you accidentally start the wrong flow (browser-PKCE) and the agent is hanging waiting for a 127.0.0.1 callback that will never come, kill via the Hermes process tool:

```
mcp_process(action='kill', session_id='<proc id from terminal background=true>')
```

The PKCE state is ephemeral — no cleanup needed. Just relaunch with `--use-device-code`.

## Pitfalls observed in production sessions

1. `--no-browser` is a vestigial Azure-isms-meets-AWS confusion — sounds like it should switch to device code, doesn't.
2. PKCE flow accepts the auth in your browser BUT the token won't be saved on the agent host because the redirect lands on the wrong loopback. You'll see "successful" in the browser yet `aws sts get-caller-identity` keeps failing.
3. Device-code tokens for AWS SSO default to ~8h; Azure default ~12h. For long-running cron jobs, prefer service principals / IAM roles instead.
4. On AWS, `aws configure sso` (the wizard) ALSO triggers the wrong flow by default — use `aws configure sso --use-device-code` or write `~/.aws/config` by hand and then run `aws sso login --use-device-code`.

## Verification snippets

```bash
# Azure
az account show --query "{name:name, id:id, user:user.name}" -o table

# AWS (default profile)
aws sts get-caller-identity

# AWS (specific SSO profile after generation)
aws --profile <account-name> sts get-caller-identity
```
