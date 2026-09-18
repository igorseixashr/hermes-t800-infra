# Headless AWS SSO Login for Hermes Agent

When working in a headless environment (like a remote Linux server or a restricted container) where the `browser` tool or local browser is unavailable, follow this workflow to refresh an expired AWS SSO token.

## The Problem
Running `aws sso login` in a foreground terminal often hangs or attempts to open a browser that isn't there. If you use `--use-device-code`, it prints the URL and code, but if the process is blocking, the agent might not see the output immediately if not handled correctly.

## The Solution: Hermes Background Pattern

1. **Start the login process in the background with redirection:**
   Using `bash -c` with redirection is the most reliable way to capture the device code output in headless environments without the process hanging or buffering.

   ```python
   terminal(background=True, command='bash -c "aws sso login --sso-session corp --use-device-code > /tmp/sso_auth.txt 2>&1"', notify_on_complete=True)
   ```

2. **Retrieve and present the device code:**
   Wait 2-3 seconds for the file to be populated, then read it.

   ```python
   # Wait briefly then:
   read_file(path="/tmp/sso_auth.txt")
   ```

3. **Present to the User:**
   Give the user the URL and the Code explicitly.

   > Acesse: https://d-906789a408.awsapps.com/start/#/device
   > Código: `ABCD-EFGH`

4. **Verify:**
   After the user confirms they approved the request, run a test command:
   ```bash
   aws sts get-caller-identity --profile aws-network
   ```

## Troubleshooting Browser Tools (Rocky 9 / RHEL 9)
If `browser_navigate` or `playwright` fail with "error while loading shared libraries" (e.g., `libnspr4.so`, `libnss3.so`), the following packages are required:

```bash
sudo dnf install nspr nss atk at-spi2-atk libXcomposite libXcursor libXdamage libXrandr libXScrnSaver mesa-libgbm alsa-lib pango at-spi2-core -y
```

## Pitfalls
- **Timeout:** Foreground commands with high timeouts might still hide the output until they finish. Backgrounding is safer.
- **Redirection Buffering:** Some versions of `aws` CLI might buffer output. Using `unbuffer` (from `expect` package) helps, but raw redirection usually works for the initial string.
