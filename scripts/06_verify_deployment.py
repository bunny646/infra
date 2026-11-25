import json
import os
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from _common import (
    ScriptError,
    app_namespace,
    configure_kubectl,
    fail_on_error,
    kubectl_json,
    require_commands,
)


APPLICATIONS = [
    "pharma-api-gateway-dev",
    "pharma-auth-service-dev",
    "pharma-drug-catalog-service-dev",
    "pharma-inventory-service-dev",
    "pharma-manufacturing-service-dev",
    "pharma-notification-service-dev",
    "pharma-qc-service-dev",
    "pharma-supplier-service-dev",
    "pharma-pharma-ui-dev",
]


def ready_nodes() -> None:
    nodes = kubectl_json("get", "nodes").get("items", [])
    if not nodes:
        raise ScriptError("The EKS cluster has no nodes.")
    not_ready = []
    for node in nodes:
        conditions = node.get("status", {}).get("conditions", [])
        if not any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in conditions
        ):
            not_ready.append(node.get("metadata", {}).get("name", "<unknown>"))
    if not_ready:
        raise ScriptError(f"Nodes are not Ready: {', '.join(not_ready)}")
    print(f"All {len(nodes)} EKS node(s) are Ready.")


def ready_workloads(namespace: str, require_items: bool = True) -> list[str]:
    pending: list[str] = []
    for kind in ("deployments", "statefulsets"):
        items = kubectl_json("get", kind, "--namespace", namespace).get("items", [])
        if kind == "deployments" and require_items and not items:
            pending.append(f"{namespace}: no deployments found")
        for item in items:
            metadata = item.get("metadata", {})
            name = metadata.get("name", "<unknown>")
            spec = item.get("spec", {})
            status = item.get("status", {})
            desired = int(spec.get("replicas", 1))
            ready = int(status.get("readyReplicas", 0))
            if desired < 1 or ready < desired:
                pending.append(f"{namespace}/{kind[:-1]}/{name}: {ready}/{desired} ready")
    return pending


def application_statuses() -> list[str]:
    data = kubectl_json("get", "applications.argoproj.io", "--namespace", "argocd")
    by_name = {
        item.get("metadata", {}).get("name"): item
        for item in data.get("items", [])
    }
    pending = []
    for name in APPLICATIONS:
        item = by_name.get(name)
        if item is None:
            pending.append(f"{name}: Application missing")
            continue
        status = item.get("status", {})
        sync = status.get("sync", {}).get("status", "Unknown")
        health = status.get("health", {}).get("status", "Unknown")
        if sync != "Synced" or health != "Healthy":
            pending.append(f"{name}: sync={sync}, health={health}")
    return pending


def external_secret_status(namespace: str) -> list[str]:
    data = kubectl_json("get", "externalsecrets.external-secrets.io", "--namespace", namespace)
    by_name = {
        item.get("metadata", {}).get("name"): item
        for item in data.get("items", [])
    }
    item = by_name.get("pharma-app-secrets")
    if item is None:
        return [f"{namespace}/pharma-app-secrets: ExternalSecret missing"]
    conditions = item.get("status", {}).get("conditions", [])
    ready = any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in conditions
    )
    return [] if ready else [f"{namespace}/pharma-app-secrets: not Ready"]


def check_http_urls() -> None:
    urls = [
        url.strip()
        for url in os.environ.get("HEALTHCHECK_URLS", "").split(",")
        if url.strip()
    ]
    for url in urls:
        try:
            with urlopen(url, timeout=10) as response:
                if response.status < 200 or response.status >= 400:
                    raise ScriptError(f"Health check returned HTTP {response.status}: {url}")
        except (URLError, TimeoutError) as error:
            raise ScriptError(f"Health check failed for {url}: {error}") from error
        print(f"HTTP health check passed: {url}")


def wait_for_deployment(namespace: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    pending: list[str] = []
    while time.monotonic() < deadline:
        pending = []
        pending.extend(ready_workloads("kube-system", require_items=False))
        pending.extend(ready_workloads("argocd"))
        pending.extend(ready_workloads("external-secrets"))
        pending.extend(ready_workloads(namespace))
        pending.extend(application_statuses())
        pending.extend(external_secret_status(namespace))
        if not pending:
            check_http_urls()
            print("All Argo CD applications, external secrets, and workloads are healthy.")
            return
        time.sleep(15)

    details = "\n".join(f"- {item}" for item in pending)
    raise ScriptError(f"Deployment did not become healthy within {timeout}s:\n{details}")


def main() -> None:
    require_commands("aws", "kubectl")
    configure_kubectl()
    ready_nodes()
    try:
        timeout = int(os.environ.get("DEPLOYMENT_HEALTH_TIMEOUT_SECONDS", "900"))
    except ValueError as error:
        raise ScriptError("DEPLOYMENT_HEALTH_TIMEOUT_SECONDS must be an integer.") from error
    if timeout <= 0:
        raise ScriptError("DEPLOYMENT_HEALTH_TIMEOUT_SECONDS must be greater than zero.")
    wait_for_deployment(app_namespace(), timeout)


if __name__ == "__main__":
    fail_on_error(main)
