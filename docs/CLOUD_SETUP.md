# Connecting real clouds (optional, all free)

Connect **one cloud at a time**. After each one, test it locally, then switch it on in GitHub.

> **Golden rules for staying at ₹0**
> 1. Before creating anything, set a **budget alert** on every cloud.
> 2. The tracker only **reads** usage. It never creates paid resources.
> 3. Never commit keys. Use GitHub **Secrets**, or better, OIDC (no keys at all).
> 4. Free-tier rules change. Check the official page and update `config/limits.yaml`.

You'll need the Terraform CLI (free): https://developer.hashicorp.com/terraform/install

The general Terraform flow for each cloud folder is:
```bash
cd terraform/<cloud>
cp terraform.tfvars.example terraform.tfvars   # then edit the values
terraform init
terraform validate
terraform plan        # read what will be created
terraform apply       # type "yes"
```
`terraform.tfvars` and the state files are git-ignored on purpose.

---

## 1. Azure for Students (no credit card)

1. Sign up at https://azure.microsoft.com/free/students/ with your college email.
2. Install the Azure CLI and log in: `az login`
3. Get your subscription ID: `az account show --query id -o tsv`
4. **Test locally:**
   ```bash
   # Windows: $env:AZURE_SUBSCRIPTION_ID="..."; $env:TRACKER_PROVIDERS="azure"
   export AZURE_SUBSCRIPTION_ID=<id>
   TRACKER_PROVIDERS=azure python -m tracker run --dry-run
   ```
   (Locally, `DefaultAzureCredential` reuses your `az login`.)
5. **For GitHub Actions:** run the Terraform in `terraform/azure`, then add these as repo **Variables**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (all printed by `terraform apply`).
6. Set `credit_usd` in `config/limits.yaml` to your actual credit.

> Some university directories block app registrations. If `terraform apply` fails with a permission error, keep using Azure locally only (step 4), and say so in your README. It's an honest limitation, and that's fine.

> Some special subscription offers don't expose usage through the Consumption API. If you see an error mentioning the offer type, that's the reason, and the tracker reports it instead of crashing.

---

## 2. AWS

1. Create an account at https://aws.amazon.com/free/. A card is required for verification (usually a small refundable charge).
2. **Immediately** enable MFA on the root user and create an IAM admin user for yourself.
3. Install the AWS CLI and run `aws configure` with your admin user's keys (these stay on your laptop only).
4. **Test locally:**
   ```bash
   TRACKER_PROVIDERS=aws python -m tracker run --dry-run
   ```
   Then set `starting_credits_usd` in `limits.yaml` to the credits shown in your AWS console.
5. **For GitHub Actions (no keys stored):**
   ```bash
   cd terraform/aws && cp terraform.tfvars.example terraform.tfvars   # edit repo + email
   terraform init && terraform apply
   ```
   This creates a read-only role plus a **$1 budget alert**. Confirm the subscription email AWS sends you.
   Copy the output `role_arn` into a repo **Variable** named `AWS_ROLE_ARN`.

**What the tracker calls:** only `freetier:GetAccountPlanState`, `freetier:GetFreeTierUsage` and `budgets:ViewBudget`. It never calls Cost Explorer, which costs money per request.

---

## 3. Oracle Cloud (Always Free)

1. Sign up at https://www.oracle.com/cloud/free/. A card is used for verification.
2. In the console go to **Profile → My profile → API keys → Add API key**. Download the private key, then copy the config snippet it shows.
3. **Local:** save the snippet to `~/.oci/config` and point `key_file` at the downloaded key. Then run:
   ```bash
   TRACKER_PROVIDERS=oracle python -m tracker run --dry-run
   ```
4. **GitHub Actions:** add these repo **Secrets** (values come from the config snippet):
   - `OCI_TENANCY`, `OCI_USER`, `OCI_FINGERPRINT`, `OCI_REGION`
   - `OCI_KEY_CONTENT`: the full contents of the `.pem` private key file

   Create a separate **read-only** user for this. Put it in a group with a policy such as
   `Allow group UsageReaders to read usage-reports in tenancy`, rather than using your admin key.

The rule for Oracle is simple: Always Free costs 0, so **any cost greater than 0 triggers an alert**.

---

## 4. Google Cloud (GCP)

1. Create an account at https://cloud.google.com/free. A card is used for verification.
2. Create a project, then set a **budget alert**: Billing → Budgets & alerts → ₹100 or lower.
3. Run the Terraform in `terraform/gcp`. It creates the `billing_export` dataset, a read-only service account, and GitHub login via Workload Identity Federation.
4. In the console go to **Billing → Billing export → BigQuery export → Standard usage cost → Edit settings**, and choose your project and the `billing_export` dataset. Data starts arriving within about a day.
5. Find the table name (it looks like `gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`) and set a repo **Variable**:
   `GCP_BILLING_TABLE` = `your-project.billing_export.gcp_billing_export_v1_...`
6. Add repo **Variables** `GCP_WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT` from the Terraform outputs.
7. **Local test:** run `gcloud auth application-default login`, then:
   ```bash
   GCP_BILLING_TABLE=... TRACKER_PROVIDERS=gcp python -m tracker run --dry-run
   ```

**Cost guard:** every query has `maximum_bytes_billed` = 100 MB. If a query would ever scan more, BigQuery **refuses** to run it instead of charging you. A personal billing table is only a few MB.

To match the right SKUs, look at your export once:
```sql
SELECT DISTINCT service.description, sku.description
FROM `your-project.billing_export.gcp_billing_export_v1_...`
```
Then adjust `providers.gcp.skus` in `limits.yaml`.

---

## Turning clouds on in GitHub

Set the repo **Variable** `TRACKER_PROVIDERS` to a comma-separated list, for example:
```
azure,aws,oracle
```
You can keep `mock` in the list too (e.g. `mock,azure`) if you want demo data alongside real data.
