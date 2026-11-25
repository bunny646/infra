import argparse
import json
import os
import time
from typing import Any

from _common import ScriptError, env_value, fail_on_error, require_commands, run


BACKEND_WORKFLOWS = [
    "ci-api-gateway.yml",
    "ci-auth-service.yml",
    "ci-drug-catalog.yml",
    "ci-inventory-service.yml",
    "ci-manufacturing-service.yml",
    "ci-notification.yml",
    "ci-qc-service.yml",
    "ci-supplier-service.yml",
]
FRONTEND_WORKFLOWS = ["ci-pharma-ui.yml"]


def run_ids(repo: str, workflow: str) -> set[int]:
    result = run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            "develop",
            "--event",
            "workflow_dispatch",
            "--limit",
            "100",
            "--json",
            "databaseId",
        ],
        capture_output=True,
    )
    try:
        runs: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ScriptError(f"GitHub CLI returned invalid run data for {repo}/{workflow}.") from error
    return {int(item["databaseId"]) for item in runs if "databaseId" in item}


def dispatch(repo: str, workflow: str, wait: bool, timeout: int) -> None:
    existing_ids = run_ids(repo, workflow) if wait else set()
    run(
        [
            "gh",
            "workflow",
            "run",
            workflow,
            "--repo",
            repo,
            "--ref",
            "develop",
        ]
    )
    print(f"Triggered {repo}/{workflow} on develop.")
    if not wait:
        return

    deadline = time.monotonic() + timeout
    run_id = None
    while time.monotonic() < deadline:
        current_ids = run_ids(repo, workflow)
        new_ids = current_ids - existing_ids
        if new_ids:
            run_id = max(new_ids)
            break
        time.sleep(5)
    if run_id is None:
        raise ScriptError(f"Timed out waiting for the {repo}/{workflow} run to appear.")

    run(
        [
            "gh",
            "run",
            "watch",
            str(run_id),
            "--repo",
            repo,
            "--exit-status",
            "--interval",
            "10",
        ],
        timeout=timeout,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dispatch the backend and frontend develop CI workflows."
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Dispatch builds and exit without waiting for ECR pushes to finish.",
    )
    args = parser.parse_args()

    require_commands("gh")
    backend_repo = env_value("BACKEND_REPO", required=True)
    frontend_repo = env_value("FRONTEND_REPO", required=True)
    try:
        timeout = int(os.environ.get("GH_RUN_TIMEOUT_SECONDS", "3600"))
    except ValueError as error:
        raise ScriptError("GH_RUN_TIMEOUT_SECONDS must be an integer.") from error
    if timeout <= 0:
        raise ScriptError("GH_RUN_TIMEOUT_SECONDS must be greater than zero.")

    run(["gh", "auth", "status"])
    for workflow in BACKEND_WORKFLOWS:
        dispatch(backend_repo, workflow, not args.no_wait, timeout)
    for workflow in FRONTEND_WORKFLOWS:
        dispatch(frontend_repo, workflow, not args.no_wait, timeout)
    print("All CI workflows completed successfully." if not args.no_wait else "All CI workflows were dispatched.")


if __name__ == "__main__":
    fail_on_error(main)
