# Account: rsfn-network (651684790312)

## Constraints & Requirements

### 1. Service Control Policy (SCP)
- **Policy ID**: `p-sgjwr2g2` (Explicit Deny)
- **Blocked Operations**: `ec2:RunInstances` is blocked for most roles including `AWSNetworkAdministratorV2`.
- **Bypass**: Requires specific conditions (Tags + IAM Profile) or delegation to Cloud-Core.

### 2. IAM Instance Profile
- **Mandatory Profile**: `SessionManager`
- **Terraform Config**:
  ```hcl
  iam_instance_profile = "SessionManager"
  ```
- **Purpose**: Enables SSM access and complies with security guardrails.

### 3. Mandatory Tags
Provisioning without these tags will trigger an explicit deny in the SCP:
- `Environment`: Typically `rsfn-network` (or `Production` depending on the sub-segment).
- `cost-center`: `870301920` (Standard for Network Core).
- `Role`: `compute`.
- `Provider`: `terraform`.

### 4. Storage Encryption
- All EBS volumes **must** be encrypted.
- Volume type `gp3` is preferred for performance/cost balance.

### 5. Multi-Region Pattern
The account spans `us-east-1` and `sa-east-1`. Use provider aliases for simultaneous management.
