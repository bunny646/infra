from _common import (
    app_namespace,
    aws_region,
    configure_kubectl,
    fail_on_error,
    kubectl_apply,
    require_commands,
    run,
)


def external_secret(name: str, namespace: str, data: list[dict[str, object]]) -> dict[str, object]:
    return {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "refreshInterval": "1h",
            "secretStoreRef": {
                "name": "pharma-aws-secrets",
                "kind": "ClusterSecretStore",
            },
            "target": {
                "name": name,
                "creationPolicy": "Owner",
                "template": {
                    "type": "Opaque",
                    "data": {"DB_NAME": "pharmadb", "DB_PORT": "5432"},
                },
            },
            "data": data,
        },
    }


def main() -> None:
    require_commands("aws", "kubectl")
    configure_kubectl()
    namespace = app_namespace()
    region = aws_region()

    run(
        [
            "kubectl",
            "wait",
            "--for=condition=Established",
            "--timeout=120s",
            "crd/clustersecretstores.external-secrets.io",
            "crd/externalsecrets.external-secrets.io",
        ]
    )
    kubectl_apply(
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace},
        }
    )
    kubectl_apply(
        {
            "apiVersion": "external-secrets.io/v1",
            "kind": "ClusterSecretStore",
            "metadata": {"name": "pharma-aws-secrets"},
            "spec": {
                "provider": {
                    "aws": {
                        "service": "SecretsManager",
                        "region": region,
                        "auth": {
                            "jwt": {
                                "serviceAccountRef": {
                                    "name": "external-secrets",
                                    "namespace": "external-secrets",
                                }
                            }
                        },
                    }
                }
            },
        }
    )
    kubectl_apply(
        external_secret(
            "pharma-app-secrets",
            namespace,
            [
                {
                    "secretKey": "DB_USERNAME",
                    "remoteRef": {
                        "key": "/pharma/dev/db-credentials",
                        "property": "username",
                    },
                },
                {
                    "secretKey": "DB_PASSWORD",
                    "remoteRef": {
                        "key": "/pharma/dev/db-credentials",
                        "property": "password",
                    },
                },
                {
                    "secretKey": "DB_HOST",
                    "remoteRef": {
                        "key": "/pharma/dev/db-credentials",
                        "property": "host",
                    },
                },
                {
                    "secretKey": "JWT_SECRET",
                    "remoteRef": {
                        "key": "/pharma/dev/jwt-secret",
                        "property": "secret",
                    },
                },
            ],
        )
    )
    print(
        f"Created ClusterSecretStore and ExternalSecret in {namespace}; "
        "workload values should reference secret pharma-app-secrets."
    )


if __name__ == "__main__":
    fail_on_error(main)
