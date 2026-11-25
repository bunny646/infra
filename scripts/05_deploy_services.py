from _common import (
    ScriptError,
    app_namespace,
    app_project_name,
    configure_kubectl,
    env_value,
    fail_on_error,
    gitops_repo_url,
    kubectl_apply,
    require_commands,
)


SERVICES = [
    "api-gateway",
    "auth-service",
    "drug-catalog-service",
    "inventory-service",
    "manufacturing-service",
    "notification-service",
    "qc-service",
    "supplier-service",
    "pharma-ui",
]


def main() -> None:
    require_commands("aws", "kubectl")
    configure_kubectl()
    repo_url = gitops_repo_url()
    branch = env_value("GITOPS_BRANCH", "main")
    chart_path = env_value("GITOPS_CHART_PATH", "helm-charts")
    values_path = env_value("GITOPS_VALUES_PATH", "envs/dev")
    namespace = app_namespace()

    if not branch or not chart_path or not values_path:
        raise ScriptError(
            "GITOPS_BRANCH, GITOPS_CHART_PATH, and GITOPS_VALUES_PATH cannot be empty."
        )

    for service in SERVICES:
        kubectl_apply(
            {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Application",
                "metadata": {
                    "name": f"pharma-{service}-dev",
                    "namespace": "argocd",
                    "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                },
                "spec": {
                    "project": app_project_name(),
                    "sources": [
                        {
                            "repoURL": repo_url,
                            "targetRevision": branch,
                            "path": chart_path,
                            "helm": {
                                "releaseName": service,
                                "valueFiles": [
                                    f"$values/{values_path}/values-{service}.yaml"
                                ],
                            },
                        },
                        {
                            "repoURL": repo_url,
                            "targetRevision": branch,
                            "ref": "values",
                        },
                    ],
                    "destination": {
                        "server": "https://kubernetes.default.svc",
                        "namespace": namespace,
                    },
                    "syncPolicy": {
                        "automated": {"prune": True, "selfHeal": True},
                        "syncOptions": ["CreateNamespace=true"],
                    },
                },
            }
        )
    print(f"Created {len(SERVICES)} Argo CD Applications in namespace {namespace}.")


if __name__ == "__main__":
    fail_on_error(main)
