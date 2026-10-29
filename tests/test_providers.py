"""Provider tests with fake cloud SDKs - no account, no network, no cost."""
import sys
import types
from datetime import date, datetime
from types import SimpleNamespace as NS

import pytest

from tracker.providers import ProviderError, get_provider

TODAY = date(2026, 10, 28)


def install(monkeypatch, name, module):
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        mod_name = ".".join(parts[:i])
        mod = module if i == len(parts) else sys.modules.get(mod_name) or types.ModuleType(mod_name)
        monkeypatch.setitem(sys.modules, mod_name, mod)
        if i > 1:
            setattr(sys.modules[".".join(parts[:i - 1])], parts[i - 1], mod)


# ---------------- AWS ----------------
class FakeFreeTier:
    def get_account_plan_state(self):
        return {"accountPlanType": "FREE", "accountPlanRemainingCredits": {"amount": 62.5, "unit": "USD"},
                "accountPlanExpirationDate": datetime(2027, 4, 1)}

    def get_free_tier_usage(self, **kwargs):
        if "nextToken" not in kwargs:
            return {"freeTierUsages": [{"service": "Amazon EC2", "description": "750 hours t3.micro",
                                        "actualUsageAmount": 600, "forecastedUsageAmount": 790,
                                        "limit": 750, "unit": "Hrs", "freeTierType": "12 Months Free"}],
                    "nextToken": "p2"}
        return {"freeTierUsages": [{"service": "AWS Lambda", "usageType": "Request",
                                    "actualUsageAmount": 10, "limit": 1000000, "unit": "Requests"}]}


@pytest.fixture
def fake_boto(monkeypatch):
    boto3 = types.ModuleType("boto3")
    boto3.session = NS(Session=lambda **kw: NS(client=lambda name: FakeFreeTier()))
    install(monkeypatch, "boto3", boto3)
    exc = types.ModuleType("botocore.exceptions")
    exc.ClientError = type("ClientError", (Exception,), {})
    exc.BotoCoreError = type("BotoCoreError", (Exception,), {})
    install(monkeypatch, "botocore.exceptions", exc)


def test_aws_credits_and_paginated_usage(fake_boto):
    cfg = {"providers": {"aws": {"starting_credits_usd": 100}}}
    recs = get_provider("aws", cfg, TODAY).fetch()
    by_service = {r.service: r for r in recs}
    assert by_service["Free plan"].used == 37.5
    assert by_service["Amazon EC2"].forecast == 790
    assert by_service["AWS Lambda"].metric == "Request"   # second page was read


# ---------------- Azure ----------------
def test_azure_spend(monkeypatch):
    identity = types.ModuleType("azure.identity")
    identity.DefaultAzureCredential = lambda: "cred"
    install(monkeypatch, "azure.identity", identity)
    consumption = types.ModuleType("azure.mgmt.consumption")
    items = [NS(cost_in_billing_currency=3.0, meter_category="Virtual Machines"),
             NS(cost=1.5, consumed_service="Storage"),
             NS(cost_in_billing_currency=2.0, meter_category="Virtual Machines")]
    consumption.ConsumptionManagementClient = lambda cred, sub: NS(
        usage_details=NS(list=lambda scope: items))
    install(monkeypatch, "azure.mgmt.consumption", consumption)
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "sub-123")

    recs = get_provider("azure", {"providers": {"azure": {"credit_usd": 100}}}, TODAY).fetch()
    assert recs[0].metric == "Credit spent" and recs[0].used == 6.5
    assert recs[1].service == "Virtual Machines" and recs[1].used == 5.0


def test_azure_needs_subscription(monkeypatch):
    install(monkeypatch, "azure.identity", types.ModuleType("azure.identity"))
    install(monkeypatch, "azure.mgmt.consumption", types.ModuleType("azure.mgmt.consumption"))
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    with pytest.raises(ProviderError):
        get_provider("azure", {"providers": {"azure": {}}}, TODAY).fetch()


# ---------------- GCP ----------------
def test_gcp_billing_export(monkeypatch):
    captured = {}
    bq = types.ModuleType("google.cloud.bigquery")
    bq.ScalarQueryParameter = lambda *a: a
    bq.QueryJobConfig = lambda **kw: captured.setdefault("job", kw)
    rows = [NS(service="Cloud Run", sku="Requests", amount=1_500_000, unit="requests", cost=0.4, credits=-0.4),
            NS(service="BigQuery", sku="Analysis", amount=0.2, unit="tebibyte", cost=0.0, credits=0.0)]
    bq.Client = lambda project: NS(query=lambda q, job_config: NS(result=lambda: rows))
    install(monkeypatch, "google.cloud.bigquery", bq)
    monkeypatch.setenv("GCP_BILLING_TABLE", "proj.billing_export.gcp_billing_export_v1_ABC")

    settings = {"skus": [{"service": "Cloud Run", "sku_contains": "Requests", "label": "Requests", "limit": 2000000},
                         {"service": "BigQuery", "sku_contains": "Analysis", "label": "Scanned", "limit": 1}]}
    recs = get_provider("gcp", {"providers": {"gcp": settings}}, TODAY).fetch()
    assert recs[0].metric == "Net cost after credits" and recs[0].used == 0
    assert recs[1].used == 1_500_000 and recs[2].used == 0.2
    assert captured["job"]["maximum_bytes_billed"] == 100 * 1024 * 1024   # cost guard is on


def test_gcp_rejects_bad_table(monkeypatch):
    install(monkeypatch, "google.cloud.bigquery", types.ModuleType("google.cloud.bigquery"))
    monkeypatch.setenv("GCP_BILLING_TABLE", "x; DROP TABLE y")
    with pytest.raises(ProviderError):
        get_provider("gcp", {"providers": {"gcp": {}}}, TODAY).fetch()


# ---------------- Oracle ----------------
def test_oracle_cost_outside_always_free(monkeypatch):
    oci = types.ModuleType("oci")
    oci.config = NS(validate_config=lambda c: None, from_file=lambda profile_name: {})
    data = NS(items=[NS(service="Compute", computed_amount=0.0),
                     NS(service="Block Storage", computed_amount=1.25)])
    oci.usage_api = NS(
        UsageapiClient=lambda cfg: NS(request_summarized_usages=lambda d: NS(data=data)),
        models=NS(RequestSummarizedUsagesDetails=lambda **kw: kw),
    )
    install(monkeypatch, "oci", oci)
    for k, v in {"OCI_TENANCY": "t", "OCI_USER": "u", "OCI_FINGERPRINT": "f",
                 "OCI_REGION": "ap-mumbai-1", "OCI_KEY_CONTENT": "k"}.items():
        monkeypatch.setenv(k, v)

    recs = get_provider("oracle", {"providers": {"oracle": {}}}, TODAY).fetch()
    assert recs[0].used == 1.25 and recs[0].limit == 0      # -> OVER
    assert [r.service for r in recs[1:]] == ["Block Storage"]
