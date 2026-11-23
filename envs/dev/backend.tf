
terraform {
  backend "s3" {
    bucket       = "pharma-terraform-state-bunny"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true

  }
}