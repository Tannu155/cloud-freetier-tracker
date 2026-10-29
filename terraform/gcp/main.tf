# Creates (all free):
#  - BigQuery dataset for the billing export
#  - Service account with read-only BigQuery access to that dataset
#  - Workload Identity Federation so GitHub Actions logs in with no JSON key
#
# After apply: Console -> Billing -> Billing export -> BigQuery export ->
# "Standard usage cost" -> choose this project + dataset "billing_export".

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "github_repo" {
  description = "Your repo as owner/name"
  type        = string
}

variable "location" {
  type    = string
  default = "US"
}

provider "google" {
  project = var.project_id
}

resource "google_project_service" "apis" {
  for_each = toset([
    "bigquery.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "billing" {
  dataset_id  = "billing_export"
  location    = var.location
  description = "Cloud Billing export read by the free tier tracker"
  depends_on  = [google_project_service.apis]
}

resource "google_service_account" "tracker" {
  account_id   = "freetier-tracker"
  display_name = "Free tier tracker (read-only)"
}

resource "google_bigquery_dataset_iam_member" "viewer" {
  dataset_id = google_bigquery_dataset.billing.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.tracker.email}"
}

resource "google_project_iam_member" "job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.tracker.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "wif" {
  service_account_id = google_service_account.tracker.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

output "GCP_WIF_PROVIDER" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "GCP_SERVICE_ACCOUNT" {
  value = google_service_account.tracker.email
}

output "billing_dataset" {
  value = "${var.project_id}.${google_bigquery_dataset.billing.dataset_id}"
}
