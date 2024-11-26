terraform {
  required_version = "~> 1.8"

  backend "remote" {
    hostname     = "app.terraform.io"
    organization = "example-org-5dfb85"

    workspaces {
      name = "homelab-external"
    }
  }

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.26.0"
    }

    http = {
      source  = "hashicorp/http"
      version = "~> 3.4.0"
    }
  }
}

provider "kubernetes" {
  # Use KUBE_CONFIG_PATH environment variables
  # Or in cluster service account
}
