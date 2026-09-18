# corp RSFN Account (651684790312) Guardrails

Specific constraints and mandatory parameters for operations in the RSFN environment.

## SCP p-sgjwr2g2 (Explicit Deny)
As of May 2026, the SCP `p-sgjwr2g2` (arn:aws:organizations::123862342651:policy/o-l6thkthly5/service_control_policy/p-sgjwr2g2) imposes a strict `Deny` on `ec2:RunInstances` for most SSO user roles, even with full tags and instance profiles.

### Confirmed Mandatory Parameters for RunInstances (when permitted)
If the SCP is bypassed or the role is whitelisted, the following parameters are strictly required by other guardrails in this account:

1.  **IAM Instance Profile:** Must be `SessionManager` (arn:aws:iam::651684790312:instance-profile/SessionManager).
2.  **Mandatory Tags (All Case-Sensitive):**
    *   `Environment` (e.g., `prod`)
    *   `cost-center` (e.g., `infra`)
    *   `Role` (e.g., `troubleshooting`)
3.  **IMDSv2:** `MetadataOptions={HttpTokens=required}`.
4.  **Tagging on Volumes:** Tags must be applied to both `instance` AND `volume` resource types in the `RunInstances` call.

## Debugging Authorization
Since SSO roles typically lack `sts:DecodeAuthorizationMessage` in this account, failures must be debugged via `dry-run` and parameter elimination.

Example of a "corp-standard" dry-run:
```bash
aws ec2 run-instances \
  --image-id <AMI> \
  --instance-type t3.micro \
  --count 1 \
  --subnet-id <SUBNET> \
  --iam-instance-profile Name=SessionManager \
  --metadata-options "HttpTokens=required" \
  --dry-run \
  --profile rsfn-network \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Environment,Value=prod},{Key=cost-center,Value=infra},{Key=Role,Value=troubleshooting}]' \
    'ResourceType=volume,Tags=[{Key=Environment,Value=prod},{Key=cost-center,Value=infra},{Key=Role,Value=troubleshooting}]'
```
