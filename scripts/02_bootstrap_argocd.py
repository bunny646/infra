from _common import (
    app_project_name,
    configure_kubectl,
    fail_on_error,
    gitops_repo_secret,
    gitops_repo_url,
    kubectl_apply,
    require_commands,
    run,
)


def main() -> None:
    require_commands("aws", "kubectl")
    configure_kubectl()
    run(
        [
            "kubectl",
            "rollout",
            "status",
            "deployment/argocd-server",
            "--namespace",
            "argocd",
            "--timeout=5m",
        ]
    )
    run(
        [
            "kubectl",
            "wait",
            "--for=condition=Established",
            "--timeout=120s",
            "crd/appprojects.argoproj.io",
        ]
    )

    repo_url = gitops_repo_url()
    kubectl_apply(gitops_repo_secret(repo_url))
    kubectl_apply(
        {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AppProject",
            "metadata": {
                "name": app_project_name(),
                "namespace": "argocd",
            },
            "spec": {
                "description": "Development applications for Pharma",
                "sourceRepos": [repo_url],
                "destinations": [
                    {
                        "namespace": "*",
                        "server": "https://kubernetes.default.svc",
                    }
                ],
                "clusterResourceWhitelist": [
                    {"group": "", "kind": "Namespace"},
                    {
                        "group": "external-secrets.io",
                        "kind": "ClusterSecretStore",
                    },
                ],
                "namespaceResourceWhitelist": [{"group": "*", "kind": "*"}],
            },
        }
    )
    print(f"Registered {repo_url} and created AppProject {app_project_name()}.")


if __name__ == "__main__":
    fail_on_error(main)
