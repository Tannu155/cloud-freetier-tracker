# Creates (all free):
#  - An app registration + service principal with a GitHub OIDC federated credential
#    (no client secret is ever created)
#  - "Cost Management Reader" role on your subscription (read-only)

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
  }
}

variable "subscription_id" {
  description = "Your Azure subscription ID (az account show --query id -o tsv)"
  type        = string
}

variable "github_repo" {
  description = "Your repo as owner/name"
  type        = string
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

data "azuread_client_config" "current" {}

resource "azuread_application" "tracker" {
  display_name = "freetier-tracker"
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "tracker" {
  client_id = azuread_application.tracker.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_federated_identity_credential" "github_main" {
  application_id = azuread_application.tracker.id
  display_name   = "github-main"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_repo}:ref:refs/heads/main"
}

resource "azurerm_role_assignment" "cost_reader" {
  scope                = "/subscriptions/${var.subscription_id}"
  role_definition_name = "Cost Management Reader"
  principal_id         = azuread_service_principal.tracker.object_id
}

output "AZURE_CLIENT_ID" {
  value = azuread_application.tracker.client_id
}

output "AZURE_TENANT_ID" {
  value = data.azuread_client_config.current.tenant_id
}

output "AZURE_SUBSCRIPTION_ID" {
  value = var.subscription_id
}
