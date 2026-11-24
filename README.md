# Pharma Infrastructure

Terraform configuration for provisioning the Pharma platform's AWS infrastructure.

## What it provisions

The development environment composes these Terraform modules:

- **VPC** — public, private, and database subnets.
- **EKS** — Kubernetes cluster and managed worker nodes.
- **RDS** — PostgreSQL database in the database subnets.
- **ECR** — container image repositories for the platform services.
- **IAM** — GitHub Actions OIDC roles and cluster identity resources.
- **Secrets Manager** — application database credentials and JWT secret.

## Repository layout

```text
envs/
  dev/                  # Development root module and S3 backend configuration
modules/
  ecr/
  eks/
  iam/
  rds/
  secrete-manager/        # Directory name as currently checked in
  vpc/
```

The dev configuration refers to the Secrets Manager module as
`modules/secrets-manager`; make sure its source path matches the directory name
before initializing Terraform.

## Prerequisites

- Terraform 1.11 or later.
- AWS CLI configured with credentials authorized to manage the resources.
- The configured S3 state bucket (`pharma-terraform-state-bunny`) available in `us-east-1`.
- Values for the required database password and JWT secret.

## Initialize and review a plan

Run these commands from the repository root:

```bash
terraform -chdir=envs/dev init
terraform -chdir=envs/dev validate
terraform -chdir=envs/dev plan
```

Terraform reads the sensitive input variables `db_password` and `jwt_secret`.
Set them locally as `TF_VAR_db_password` and `TF_VAR_jwt_secret`, or provide
them through another secure local secret-injection method. Do not commit secret
values or populated `.tfvars` files.

Review the plan before applying infrastructure changes:

```bash
terraform -chdir=envs/dev apply
```

## State and environment

The dev backend stores state in S3 at key `envs/dev/terraform.tfstate` in
`us-east-1`, with encryption and S3 lockfile locking enabled. The environment
currently targets AWS region `us-east-1`.

Provisioning EKS, NAT gateways, and RDS incurs AWS charges. Review resource
changes and estimated costs before applying.
