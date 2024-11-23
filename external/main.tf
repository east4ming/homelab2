module "ntfy" {
  source = "./modules/ntfy"
  auth   = var.ntfy
}

module "extra_secrets" {
  source = "./modules/extra-secrets"
  data   = var.extra_secrets
}
