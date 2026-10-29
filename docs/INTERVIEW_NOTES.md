# How to present this project

## 30-second pitch
"Students and small teams often get surprise cloud bills because free tiers differ on every
cloud and the native alerts fire *after* you're charged. I built a multi-cloud free tier tracker
that reads usage from AWS, Azure, GCP and Oracle every day, forecasts month-end usage from the
recent trend, and warns me on Telegram *before* I cross a limit. It runs serverless on GitHub
Actions, logs in with OIDC so there are no stored cloud keys, and the access is provisioned with
Terraform. It costs zero rupees to run."

## Resume bullet points (pick 2–3)
- Built a multi-cloud free-tier monitoring tool (AWS, Azure, GCP, OCI) in Python with a pluggable provider architecture, Telegram alerting and a Streamlit dashboard.
- Implemented trend-based forecasting that predicts the date a free-tier limit will be crossed, using a 7-day rolling usage rate.
- Eliminated long-lived cloud credentials by using GitHub OIDC / Workload Identity Federation with least-privilege, read-only IAM roles provisioned via Terraform.
- Designed for zero cost: chose free APIs over paid ones (e.g. AWS Free Tier API over Cost Explorer) and enforced BigQuery `maximum_bytes_billed` caps.
- Wrote 20 unit tests using fake cloud SDKs, run in CI before every scheduled job.

## Questions interviewers may ask, and how to answer

**Why GitHub Actions instead of Lambda / Azure Functions?**
It's free for public repos, the schedule lives next to the code, and it can log in to all four
clouds. In production I'd move it to a Lambda or Cloud Run job triggered by EventBridge or
Cloud Scheduler, with DynamoDB or Firestore instead of SQLite.

**Why not store AWS access keys as GitHub secrets?**
Long-lived keys can leak. With OIDC, GitHub gets a short-lived token, and the role trust policy
only allows the `main` branch of my repository. Nothing is stored that could be stolen.

**How does the forecast work?**
I take the usage change over the last ~7 days divided by the days elapsed. If there's no
history, I use the month-to-date average. Projected usage = used + rate × days left. If AWS
supplies its own forecast, I use that instead.

**How do you avoid alert spam?**
Each metric alerts once per level (projected → warn → critical → over) per month. That state
is stored in an `alerts` table. Alerts are only marked as sent if Telegram actually confirms delivery.

**What happens if one cloud's API fails?**
Each provider runs in isolation. A failure is logged and sent as an error message, and the
other clouds are still processed.

**How did you test code that talks to 4 clouds without paying?**
Mock mode for end-to-end runs, plus unit tests that inject fake SDK modules. These test
pagination, field fallbacks, input validation (for example, rejecting a malformed BigQuery
table name to prevent SQL injection), and the cost cap.

**What would you improve?**
Auto-remediation (stop tagged instances when a limit is close), multi-account support,
storing history in a managed database, and a Slack/Teams notifier.

## Demo script (2 minutes)
1. Show the README architecture diagram.
2. Open the live dashboard and point at a red metric and its forecast date.
3. Show the Telegram alert on your phone.
4. Open `.github/workflows/tracker.yml` and point out the OIDC logins and the commit-history step.
5. Open `terraform/aws/main.tf` and point out the least-privilege policy and the trust condition on your repo.
