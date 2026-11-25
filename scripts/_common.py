import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


INFRA_DIR = Path(__file__).resolve().parents[1]


class ScriptError(RuntimeError):
    pass


def env_value(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if value is None or not value.strip():
        if required:
            raise ScriptError(f"Set the {name} environment variable before continuing.")
        return ""
    return value.strip()


def require_commands(*commands: str) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise ScriptError(f"Missing required command(s): {', '.join(missing)}")


def run(
    args: Sequence[str],
    *,
    capture_output: bool = False,
    input_text: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=capture_output,
            input=input_text,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ScriptError(f"Required command not found: {args[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise ScriptError(f"Command timed out: {args[0]}") from error

    if result.returncode:
        detail = result.stderr.strip() if result.stderr else ""
        message = f"Command failed ({result.returncode}): {' '.join(args)}"
        if detail:
            message = f"{message}\n{detail}"
        raise ScriptError(message)
    return result


def aws_region() -> str:
    return env_value("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


def cluster_name() -> str:
    return env_value("EKS_CLUSTER_NAME", "pharma-dev-cluster")


def aws_output(region: str, *args: str) -> str:
    result = run(
        ["aws", *args, "--region", region, "--output", "text"],
        capture_output=True,
    )
    value = result.stdout.strip()
    if not value or value == "None":
        raise ScriptError(f"AWS CLI returned no value for: {' '.join(args)}")
    return value


def configure_kubectl(region: str | None = None) -> None:
    region = region or aws_region()
    try:
        account_id = aws_output(
            region,
            "sts",
            "get-caller-identity",
            "--query",
            "Account",
        )
    except ScriptError as error:
        raise ScriptError(
            "AWS credentials are invalid or expired. Refresh the credentials used by "
            "the AWS CLI, then verify with `aws sts get-caller-identity`."
        ) from error

    print(f"Using AWS account {account_id} in {region}.")
    run(
        [
            "aws",
            "eks",
            "update-kubeconfig",
            "--name",
            cluster_name(),
            "--region",
            region,
        ]
    )
    run(["kubectl", "get", "nodes", "--request-timeout=20s"], timeout=30)


def kubectl_json(*args: str) -> dict[str, Any]:
    result = run(["kubectl", *args, "-o", "json"], capture_output=True)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ScriptError(f"kubectl returned invalid JSON for: {' '.join(args)}") from error
    if not isinstance(value, dict):
        raise ScriptError(f"kubectl returned an unexpected response for: {' '.join(args)}")
    return value


def kubectl_apply(resource: dict[str, Any]) -> None:
    manifest = json.dumps(resource)
    run(["kubectl", "apply", "-f", "-"], input_text=manifest)


def gitops_repo_url() -> str:
    repo = env_value("GITOPS_REPO", required=True)
    if repo.startswith("https://") or repo.startswith("ssh://"):
        return repo
    if repo.startswith("git@"):
        return repo
    if "/" not in repo or repo.count("/") != 1:
        raise ScriptError("GITOPS_REPO must be an owner/repository name or a Git URL.")
    return f"https://github.com/{repo}.git"


def gitops_repo_secret(repo_url: str) -> dict[str, Any]:
    secret: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "gitops-repository",
            "namespace": "argocd",
            "labels": {"argocd.argoproj.io/secret-type": "repository"},
        },
        "stringData": {"type": "git", "url": repo_url},
    }
    token = env_value("GITOPS_TOKEN")
    username = env_value("GITOPS_USERNAME", "x-access-token")
    if token:
        secret["stringData"]["username"] = username
        secret["stringData"]["password"] = token
    return secret


def app_project_name() -> str:
    return env_value("ARGOCD_PROJECT", "pharma-dev")


def app_namespace() -> str:
    return env_value("APP_NAMESPACE", "pharma-dev")


def fail_on_error(function: Any) -> None:
    try:
        function()
    except ScriptError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error

