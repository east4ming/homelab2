# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains Kubernetes deployment manifests for self-hosting [Lobe Chat](https://github.com/lobehub/lobe-chat) - an open-source, modern AI chatbot framework. The deployment includes:

- **Lobe Chat**: Primary application (database variant with PostgreSQL support)
- **Casdoor**: Authentication and single sign-on service
- **PostgreSQL with pgvector**: Vector database for embeddings and knowledge base
- **External S3-compatible storage**: Object storage for file uploads (configured to use rustfs)

The manifests are generated from Docker Compose using `kompose` and optimized for homelab Kubernetes clusters with Tailscale networking.

## Common Commands

### Deployment
```bash
# Create namespace (if not managed by ArgoCD)
kubectl create ns lobe-chat

# Apply all manifests
kubectl apply -f . -n lobe-chat

# Apply specific component
kubectl apply -f deploy-lobe.yaml -n lobe-chat
```

### Verification and Debugging
```bash
# Check pod status
kubectl get pods -n lobe-chat -w

# View logs
kubectl logs deployment/lobe -n lobe-chat
kubectl logs deployment/casdoor -n lobe-chat
kubectl logs deployment/postgresql -n lobe-chat

# Check ingress status
kubectl get ingress -n lobe-chat

# Check services
kubectl get svc -n lobe-chat

# Check external services
kubectl get svc -n lobe-chat | grep egress

# Describe resources for detailed status
kubectl describe deployment/lobe -n lobe-chat
```

### Updates and Maintenance
```bash
# Update image versions (edit deployment files first)
kubectl apply -f deploy-lobe.yaml -n lobe-chat

# Restart deployments
kubectl rollout restart deployment/lobe -n lobe-chat

# Scale deployments
kubectl scale deployment/lobe --replicas=2 -n lobe-chat
```

## Architecture and Key Patterns

### Component Interactions
1. **Lobe Chat** depends on:
   - PostgreSQL for database (via `DATABASE_URL` secret)
   - Casdoor for authentication (via `AUTH_CASDOOR_*` environment variables)
   - S3-compatible storage for file uploads (via `S3_*` environment variables)
   - Optional: Ollama for local models (via `OLLAMA_PROXY_URL`)

2. **Casdoor** depends on:
   - PostgreSQL for its own database (separate from Lobe's database)

3. **PostgreSQL** includes:
   - pgvector extension for vector embeddings
   - PVC for data persistence
   - `rm-lost-found` initContainer to handle filesystem issues

### Networking Configuration
- **Tailscale Ingress**: All components use Tailscale Ingress Controller with annotation `tailscale.com/experimental-forward-cluster-traffic-via-ingress: "true"` to enable both internal and external access.
- **External Services**: Each component has an `egress-*` ExternalName service with Tailscale annotations (`tailscale.com/tailnet-fqdn`, `tailscale.com/proxy-group`, `tailscale.com/proxy-class`) for cluster-internal access via Tailscale FQDN.
- **Domain Configuration**: All components use `*.west-beta.ts.net` domains (Tailscale MagicDNS).

### Configuration Management
- **Secrets**: Sensitive information (API keys, database URLs, S3 credentials) are stored in Kubernetes Secrets, not in this repository.
- **Environment Variables**: Critical configuration passed via environment variables in deployments:
  - `APP_URL`, `NEXTAUTH_URL`: Public URLs for Lobe Chat
  - `AUTH_CASDOOR_ISSUER`: Casdoor endpoint
  - `S3_ENDPOINT`, `S3_PUBLIC_DOMAIN`: S3 storage endpoints
  - `DEFAULT_FILES_CONFIG`: Embedding model configuration
- **ConfigMaps**: Casdoor configuration (`casdoor-cm0-configmap.yaml.example`) provides initial setup template.

### Storage Configuration
- **PostgreSQL**: 10Gi PVC with pgvector extension
- **S3 Storage**: Currently configured for rustfs. Bucket `lobe` with anonymous read access required for frontend file access.
- **File Processing**: Lobe Chat uses configured embedding models (`zhipu/embedding-3` or `ollama/snowflake-arctic-embed2:latest`) for knowledge base functionality.

## Important Notes for Development

### Repository Structure
- **Deployment manifests**: `deploy-*.yaml` for each component
- **Services**: `svc-*.yaml` for internal cluster communication
- **External services**: `svc-egress-*.yaml` for Tailscale-based cluster-internal access
- **Ingress**: `ingress-*.yaml` for external access via Tailscale
- **Examples**: `examples/` contains Docker Compose template and example ConfigMap
- **Documentation**: README files in Chinese and English

### Security Considerations
- No sensitive data in repository (secrets managed externally)
- All authentication via Casdoor with OAuth/OIDC
- S3 buckets configured with anonymous read access for frontend file display
- Tailscale provides encrypted network transport

### Integration Points
1. **Authentication**: Configured to use Casdoor SSO with `NEXT_AUTH_SSO_PROVIDERS=casdoor`
2. **File Storage**: S3-compatible API with path-style addressing enabled (`S3_ENABLE_PATH_STYLE=1`)
3. **AI Models**: Supports multiple providers via environment variables (DeepSeek, Ollama, etc.)
4. **Vector Database**: pgvector enables knowledge base functionality with configurable embedding models

### Common Modification Points
1. **Domain names**: Update all occurrences of `*.west-beta.ts.net` to match your Tailscale domain
2. **S3 endpoint**: Modify `S3_ENDPOINT` and `S3_PUBLIC_DOMAIN` in `deploy-lobe.yaml`
3. **Embedding model**: Adjust `DEFAULT_FILES_CONFIG` environment variable
4. **Resource limits**: Modify CPU/memory requests/limits in deployment specs
5. **PVC sizes**: Adjust storage sizes in PVC manifests

## Troubleshooting Guide

### Common Issues
1. **PostgreSQL won't start**: Check for `lost+found` directory in PVC (initContainer should handle this)
2. **Lobe cannot connect to Casdoor**: Verify `AUTH_CASDOOR_ISSUER` URL and Tailscale ingress configuration
3. **File uploads fail**: Check S3 credentials, endpoint accessibility, and bucket permissions
4. **Ingress not working**: Verify Tailscale Ingress Controller is running and annotations are correct
5. **External services unreachable**: Ensure Tailscale proxy annotations match your Tailnet configuration

### Verification Steps
1. Check all pods are running: `kubectl get pods -n lobe-chat`
2. Verify ingress resources: `kubectl get ingress -n lobe-chat`
3. Test external access: `curl -I https://lobe.west-beta.ts.net`
4. Check application logs for specific errors
5. Validate secrets exist: `kubectl get secrets -n lobe-chat`

## Related Documentation
- [Lobe Chat Self-hosting Guide](https://lobehub.com/zh/docs/self-hosting/server-database/docker-compose)
- [Casdoor Documentation](https://casdoor.org/docs/)
- [Tailscale Kubernetes Operator](https://tailscale.com/kb/1260/kubernetes-operator/)
- [pgvector Extension](https://github.com/pgvector/pgvector)
