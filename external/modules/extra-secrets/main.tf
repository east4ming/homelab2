resource "kubernetes_secret_v1" "external" {
  metadata {
    name      = var.name
    namespace = var.namespace

    annotations = {
      "app.kubernetes.io/managed-by" = "Terraform"
    }
  }

  data = var.data
}
