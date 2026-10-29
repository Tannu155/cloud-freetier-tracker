# Creates (all free):
#  1. A READ-ONLY IAM role GitHub Actions can assume via OIDC (no access keys stored anywhere)
#  2. A $1 monthly budget that emails you if you are ever charged

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

variable "github_repo" {
  description = "Your repo as owner/name, e.g. rahul/cloud-freetier-tracker"
  type        = string
}

variable "alert_email" {
  description = "Email for the $1 budget alert"
  type        = string
}

variable "create_oidc_provider" {
  description = "Set false if your account already has the GitHub OIDC provider"
  type        = bool
  default     = true
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

# Only workflows on the main branch of YOUR repo can assume this role
data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "tracker" {
  name                 = "freetier-tracker-readonly"
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = 3600
}

# Least privilege: only the free, read-only Free Tier + Budgets APIs
data "aws_iam_policy_document" "read_usage" {
  statement {
    actions = [
      "freetier:GetFreeTierUsage",
      "freetier:GetAccountPlanState",
      "budgets:ViewBudget",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "read_usage" {
  name   = "read-free-tier-usage"
  role   = aws_iam_role.tracker.id
  policy = data.aws_iam_policy_document.read_usage.json
}

# Safety net: email if actual or forecasted spend goes above $1
resource "aws_budgets_budget" "safety_net" {
  name         = "free-tier-safety-net"
  budget_type  = "COST"
  limit_amount = "1.0"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

output "role_arn" {
  description = "Put this in GitHub -> Settings -> Variables as AWS_ROLE_ARN"
  value       = aws_iam_role.tracker.arn
}
