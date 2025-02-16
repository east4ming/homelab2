# lobe-chat

## 安装

参考文档:

- <https://lobehub.com/zh/docs/self-hosting/server-database/docker-compose>

1. 参见 [快速启动](https://lobehub.com/zh/docs/self-hosting/server-database/docker-compose#快速启动). 先使用 docker compose 部署, 了解各个组件的用途和环境变量的使用.
2. 分析后得出初步结论:
   1. `network-service` (基于alpine) 不需要, 它的用途类似 ingress
   2. `minio` 需要(我曾尝试使用 qnap 的对象存储, 但失败), 但是将它作为单独的服务使用 helm 部署在单独的 namespace 中.
3. 基于上述结论, 删除 `network-service` 和 `minio` 相关的配置, 并修改 `docker-compose.yml` 文件. 修改后的文件在 [这里](./examples/docker-compose-remove-minio-and-network-service.yml.example)
4. 使用 `kompose` 将上述文件转换为 k8s 资源文件. 得到:
   1. lobe
      1. deploy
      2. service
   2. casdoor
      1. deploy
      2. service
      3. cm (快速启动 生成的 casdoor 配置文件)
   3. pgvector
      1. deploy
      2. service
      3. PVC

### Helm 安装 MinIO

> 这里使用 helm-dashboard 进行安装.

最终 helm values 配置如下:

```yaml
deploymentUpdate:
    type: Recreate
ingress:
    annotations:
        tailscale.com/experimental-forward-cluster-traffic-via-ingress: "true"
    enabled: true
    hosts:
        - minio.west-beta.ts.net
    ingressClassName: tailscale
    tls:
        - hosts:
            - minio.west-beta.ts.net
mode: standalone
persistence:
    size: 100Gi
replicas: 1
```

说明如下:

- `deploymentUpdate`: 使用 `Recreate` 更新策略, 避免 pod 升级时因为PVC 为 RWO 卡住.
- `ingress`: 使用 tailscale ingress. 并 `forward-cluster-traffic-via-ingress` (因为后面 lobe 服务会用到)
- `mode: standalone` 使用单节点模式. 暂不考虑分布式.
- `persistence`: 使用 100Gi 的 PVC.
- `replicas`: 设置为 1. (默认为 16)

> 📝**Notes**:
>
> 2025年2月16日 已被 ArgoCD 管理.

### MinIO 额外手动配置

> 🐾**Warning:**
>
> "快速启动" 脚本中已经创建了, 但我们不使用 docker compose 部署, 所以需要手动创建

1. 创建 bucket: lobe
2. 修改 bucket: lobe 的匿名访问权限以允许读取(否则 lobe 前端页面无法访问. TODO: 应该可以通过设置 `S3_SET_ACL: "0"`, 从而避免匿名读.)
   1. Prefix: `/`
   2. Access: `readonly`
3. 创建 AKSK

### 修改 K8s 资源文件

#### casdoor

- 修改 `cm` 文件中的 `redirectUris`, 改为正式地址: `https://lobe.west-beta.ts.net...`
- 修改 `deploy` 文件中的 `env` 中的 `origin: https://casdoor.west-beta.ts.net` (因为需要浏览器端访问, 所以需要修改)
- 新增 `casdoor-ingress.yaml`, 创建 tailscale ingress. 添加 `forward-cluster-traffic-via-ingress`, 因为集群内也要访问.
- 新增 `casdoor-externalservice.yaml`, 因为集群内也要访问.

#### pgvector

- PVC size 扩到 10Gi
- 增加 `rm-lost-found` initContainer, 执行操作: `rm -rf /var/lib/postgresql/data/lost+found` (启动 pgvector 时, 如果发现 `/var/lib/postgresql/data/` 文件夹内非空, 具体为 `lost+found` 文件夹存在, 则无法启动, 因此需要删除)

#### lobe

- 修改 `deploy` 文件中的 `env` 中的:
  - `APP_URL: https://lobe.west-beta.ts.net`
  - `AUTH_CASDOOR_ISSUER: https://casdoor.west-beta.ts.net`
  - `NEXTAUTH_URL: https://lobe.west-beta.ts.net/api/auth` (`AUTH_URL` 改为 `NEXTAUTH_URL`)
  - `S3_ENDPOINT: https://minio.west-beta.ts.net`
  - `S3_PUBLIC_DOMAIN: https://minio.west-beta.ts.net` (如果是公有云, 则不同, 这个应为自己的域名)
  - `OLLAMA_PROXY_URL: http://ollama.ollama:11434`
  - `DEFAULT_FILES_CONFIG: embedding_model=embedding_model=zhipu/embedding-3`
  - 与 casdoor 类似, 也创建 ingress 和 externalservice

> 📝**Notes**:
>
> 如果是 Ollama, 则可以是:
> `DEFAULT_FILES_CONFIG: embedding_model=ollama/snowflake-arctic-embed2:latest`
> 📚️参考文档: <https://ollama.com/search?c=embedding>

### 部署

1. 创建 namespace: `kubectl create ns lobe-chat`
2. 将 k8s 资源文件部署到集群中: `kubectl apply -f . -n lobe-chat`

> 📝**Notes**:
>
> 2025年2月16日后, 已被 ArgoCD 管理

#### 2025年2月14日 update

- 移除所有敏感信息, 包括:
  - `docker-compose.yml` 和 `casdoor-cm0-configmap.yaml`: repo 只放 examples, 真实文件位于 Homelab K8s集群中.
  - ENV 中的所有敏感信息: 都改为 Secrets, Secrets 不在 repo 中存放, 真实文件位于 Homelab K8s集群中.
    - AUTH 相关
    - s3 相关
    - AI API KEY 相关
    - DB 相关

#### 2025年2月16日 update

- minio 使用 ArgoCD 管理
- Ollama 使用 ArgoCD 管理, 并移除 openwebui.

### 🐾特别注意

再次强调下, lobe/casdoor/minio 都需要确保域名在集群内外都可以访问到, 为此需要确保:

- 创建 ingress, 并添加 annotations:
  - `tailscale.com/experimental-forward-cluster-traffic-via-ingress: "true"`
- 创建 externalservice

### 测试及验证

1. 访问 minio console(通过 pod ip:9001)
2. 访问 casdoor: <https://casdoor.west-beta.ts.net>
3. 访问 lobe: <https://lobe.west-beta.ts.net>
4. 登录 lobe(验证 ["身份验证"](https://lobehub.com/zh/docs/self-hosting/environment-variables/auth) 相关服务)
5. 使用 deepseek saas 服务聊天 (验证 ["模型服务商"](https://lobehub.com/zh/docs/self-hosting/environment-variables/model-provider) 相关功能)
6. 使用 本地 ollama 模型聊天 (验证 ollama 是否已正常启动并且 lobe 已正确配置.)
7. 上传文件 (验证["s3存储服务"](https://lobehub.com/zh/docs/self-hosting/environment-variables/s3)相关配置.)
8. 查看文件 (验证 `S3_PUBLIC_DOMAIN` 和 minio 匿名化只读配置.)
9. 对文件进行 向量化 (验证 `embedding_model` 相关配置. 参考文档: [LobeChat 知识库 / 文件上传 · LobeChat Docs · LobeHub](https://lobehub.com/zh/docs/self-hosting/advanced/knowledge-base))
10. 基于知识库聊天 (验证以上全流程)

## TODO: 待优化

- [ ] 语音朗读功能不可用
- [ ] 应该可以通过设置 `S3_SET_ACL: "0"`, 从而避免匿名读.
- [ ] MinIO 应该可以通过 Helm 直接设置 bucket 及 policy, 而不用手动创建.
- [x] 安装插件并持久化(可能不需要持久化? -- 目前看不需要持久化)
- [x] 当前 embedding_model 效果不好, 后面选择一个效果好/性能好的模型. (使用 `zhipu/embedding-3`)
- ~~改为 helm chart~~
- [x] argocd 部署
- [x] 移除敏感信息
- [x] ollama 镜像部署(enable gpu/shm)
- [x] minio argocd 部署
