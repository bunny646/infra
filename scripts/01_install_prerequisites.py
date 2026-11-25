import os

from _common import (
    ScriptError,
    aws_output,
    aws_region,
    cluster_name,
    configure_kubectl,
    fail_on_error,
    require_commands,
    run,
)


def install_chart(
    release: str,
    chart: str,
    namespace: str,
    version_variable: str,
    values: list[str] | None = None,
) -> None:
    command = [
        "helm",
        "upgrade",
        "--install",
        release,
        chart,
        "--namespace",
        namespace,
        "--create-namespace",
        "--wait",
        "--timeout",
        "10m",
    ]
    version = os.environ.get(version_variable, "").strip()
    if version:
        command.extend(["--version", version])
    if values:
        command.extend(values)
    run(command)


def main() -> None:
    require_commands("aws", "kubectl", "helm")
    region = aws_region()
    name = cluster_name()
    configure_kubectl(region)

    vpc_id = aws_output(
        region,
        "eks",
        "describe-cluster",
        "--name",
        name,
        "--query",
        "cluster.resourcesVpcConfig.vpcId",
    )
    alb_role_arn = aws_output(
        region,
        "iam",
        "get-role",
        "--role-name",
        "pharma-dev-alb-controller-role",
        "--query",
        "Role.Arn",
    )
    eso_role_arn = aws_output(
        region,
        "iam",
        "get-role",
        "--role-name",
        "pharma-dev-eso-role",
        "--query",
        "Role.Arn",
    )

    repositories = [
        ("eks", "https://aws.github.io/eks-charts"),
        ("argo", "https://argoproj.github.io/argo-helm"),
        ("external-secrets", "https://charts.external-secrets.io"),
    ]
    for name_, url in repositories:
        run(["helm", "repo", "add", name_, url, "--force-update"])
    run(["helm", "repo", "update"])

    install_chart(
        "aws-load-balancer-controller",
        "eks/aws-load-balancer-controller",
        "kube-system",
        "ALB_CONTROLLER_CHART_VERSION",
        [
            "--set-string",
            f"clusterName={name}",
            "--set-string",
            f"region={region}",
            "--set-string",
            f"vpcId={vpc_id}",
            "--set",
            "serviceAccount.create=true",
            "--set-string",
            "serviceAccount.name=aws-load-balancer-controller",
            "--set-string",
            rf"serviceAccount.annotations.eks\.amazonaws\.com/role-arn={alb_role_arn}",
        ],
    )
    install_chart(
        "argocd",
        "argo/argo-cd",
        "argocd",
        "ARGOCD_CHART_VERSION",
    )
    install_chart(
        "external-secrets",
        "external-secrets/external-secrets",
        "external-secrets",
        "EXTERNAL_SECRETS_CHART_VERSION",
        [
            "--set",
            "serviceAccount.create=true",
            "--set-string",
            "serviceAccount.name=external-secrets",
            "--set-string",
            rf"serviceAccount.annotations.eks\.amazonaws\.com/role-arn={eso_role_arn}",
        ],
    )

    run(
        [
            "kubectl",
            "wait",
            "--for=condition=Established",
            "--timeout=180s",
            "crd/clustersecretstores.external-secrets.io",
            "crd/externalsecrets.external-secrets.io",
        ]
    )
    print("ALB Controller, Argo CD, and External Secrets Operator are installed.")


if __name__ == "__main__":
    fail_on_error(main)
