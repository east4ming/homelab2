# Feature Specification: ewhisper.cn 证书续期搬进集群 CronJob

**Feature Branch**: `014-acme-ewhisper-cronjob`

**Created**: 2026-11-02

**Status**: Implemented

**Input**: User description: 把 `/home/casey/.acme.sh` 那套 ewhisper.cn 证书续期流程「转换为在 homelab2 集群上运行的 cronjob，通过本 repo 标准的 bjw-s-labs chart 方式部署」。动机是「本机是我工作用的台式机，不是服务器，可能 crontab 运行时没启动；放在一直运行的 homelab2 上更合适，且代码可以在 homelab2 repo 中统一管理」。约束：本仓库是 public，转换时不能泄露机密。

## 背景与现状

ewhisper.cn 目前用 acme.sh + Let's Encrypt（DNS-01，DNSPod / 腾讯云）签一张多域名证书，
续期后推给两家 CDN。整套东西跑在一台工作台式机上：

| 位置 | 现状 | 影响 |
| --- | --- | --- |
| 调度 | 台式机 crontab `11 0,6,12,18 * * *  ~/.acme.sh/acme.sh --cron` | 台式机会关机/休眠，续期可能赶不上；没有集中可见的运行记录 |
| 状态 | `~/.acme.sh`：账号密钥、`account.conf`（含 `SAVED_Tencent_*`）、`ewhisper.cn/` 证书与私钥 | 状态只在那一台机器上，换机就要重来 |
| 部署 | `deploy-ewhisper-cdn.sh`（tccli 上传 + 部署腾讯云 CDN）+ `qiniu-deploy.py`（七牛证书与域名） | 依赖台式机上的 tccli / python 环境 |
| 代码 | 独立 public 仓库 `east4ming/acme-ewhisper-certs`，只跟踪脚本与说明 | 与集群的单一来源（homelab2）分离，改动要跨两个仓库 |

证书口径（迁移时保持不变）：`CN=ewhisper.cn`，SAN = `www.ewhisper.cn`、`pic-cdn.ewhisper.cn`；
`pic.ewhisper.cn` 已于 2026-11-02 退役，从下一次签发起不再包含。腾讯云 CDN 覆盖 `@` 与 `www`，
七牛 CDN 只有 `pic-cdn`。集群内没有任何工作负载消费这张证书——它只被推到两家 CDN。

## User Scenarios & Testing

### User Story 1 - 台式机关机也照常续期（Priority: P1）

作为 homelab2 的运维者，我希望续期跟着 7×24 运行的集群跑，不再依赖我那台会关机的台式机。

**Why this priority**: 这是迁移的全部理由。续期失败意味着 CDN 上的证书过期，公网访问直接报错。

**Independent Test**: 台式机连续关机 30 天，集群里的 CronJob 仍在到期窗口内完成签发，
三个域名的线上证书指纹始终与集群日志里的一致。

**Acceptance Scenarios**:

1. **Given** 集群里 PVC 为空，**When** 第一轮 CronJob 运行，**Then** 自动签发一张新证书（无需人工
   `--issue`），并在 Pod 日志里给出 fullchain 的 sha256 与证书指纹。
2. **Given** 证书尚未进入 ACME 续期窗口，**When** CronJob 再次触发，**Then** 不签发、不调 CDN API，
   日志写明「证书与上次部署一致，无需推送」。
3. **Given** 证书进入续期窗口，**When** CronJob 触发，**Then** acme.sh 自动续期，随后两家 CDN 被更新。

### User Story 2 - 续期后照旧自动推两家 CDN（Priority: P1）

作为运维者，我希望原来的「续期即部署」链路不退化：腾讯云 CDN（@、www）与七牛 CDN（pic-cdn）
在续期后自动拿到新证书，而且重跑不会把腾讯云证书列表刷爆。

**Why this priority**: 只续期不部署等于没续期；腾讯 `UploadCertificate --Repeatable true` 每次都会
新增记录，重复执行不幂等就是个真问题。

**Independent Test**: 手动补跑一轮 Job，日志显示「证书未变化」且腾讯云/七牛 API 调用次数为 0。

**Acceptance Scenarios**:

1. **Given** 证书内容变化，**When** 部署脚本运行，**Then** 腾讯云上传证书记录一次、部署到
   `ewhisper.cn|on` 与 `www.ewhisper.cn|on` 各一次；七牛上传一次并绑定 `pic-cdn.ewhisper.cn`。
2. **Given** 上次部署成功后证书未变，**When** 部署脚本再次运行，**Then** 直接退出，不产生任何云端写入。
3. **Given** 腾讯云部署失败，**When** Job 结束，**Then** 退出码非零且不记录「已部署指纹」，
   下一轮（或 Job 重试）会把云端的补齐。

### User Story 3 - public 仓库里没有机密（Priority: P1）

作为仓库维护者，我希望转换后的仓库只含占位符，真实密钥、账号密钥与证书私钥都不进 Git。

**Why this priority**: 仓库是 public，泄露一次就是永久泄露。

**Independent Test**: `git grep` 全历史里搜不到真实的腾讯/七牛密钥；应用 Pod 里的四把钥匙来自
`global-secrets` 的 `external` Secret。

**Acceptance Scenarios**:

1. **Given** 应用部署完成，**When** 查看 Pod 环境变量，**Then** 密钥来自 ESO 同步的 Secret，而非清单字面量。
2. **Given** 需要补种密钥，**When** 阅读文档，**Then** 能按文档把四把钥匙加进 `external` Secret，
   且不会覆盖里面的 `restic-*` 键。

### User Story 4 - 可验证、可回退的迁移（Priority: P2）

作为运维者，我希望在删掉台式机 crontab 之前，能用指纹证明线上已经是集群签的那张证书。

**Independent Test**: 按文档跑三条命令，得到「日志里的证书指纹 == 三个域名 `openssl s_client` 的指纹」。

**Acceptance Scenarios**:

1. **Given** 第一轮 Job 成功，**When** 对比日志与线上指纹，**Then** 三者一致。
2. **Given** 需要立刻更新 CDN，**When** `kubectl create job --from=cronjob/acme-ewhisper <name>`，
   **Then** 手动补跑与定时运行走同一套逻辑。

### Edge Cases

- **PVC 丢失**：下一轮走「首签」分支重新签发；代价是 Let's Encrypt 每域名 5 次/周的上限被占用一次，
  且 CDN 指纹重置后必然重推一次。
- **证书未变但上次部署失败**：指纹文件没写，重跑会补做云端部署而不是重签。
- **Job 卡住**：`activeDeadlineSeconds: 1800` 兜底，避免 `concurrencyPolicy: Forbid` 被永久占位。
- **密钥未同步 / 缺少环境变量**：部署脚本在任何网络调用之前退出并说明缺哪个变量。
- **域名退役**：`pic.ewhisper.cn` 不再纳入 SAN，七牛只处理 `pic-cdn`。
- **PVC 不支持 ReadWriteMany**：单控制器 + Forbid 下 RWO 足够，不需要 RWX。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 证书续期 MUST 以 Kubernetes CronJob 形式常驻集群，`Asia/Shanghai` 时区下每 6 小时
  触发一次（与原 crontab 同墙钟：`11 0,6,12,18 * * *`）。
- **FR-002**: 状态目录为空时 MUST 自动完成首次签发；已有证书时 MUST 走 `--cron`，由 ACME ARI 窗口决定是否真签。
- **FR-003**: 签发 MUST 使用 Let's Encrypt + DNS-01（`dns_tencent`），RSA 2048。
- **FR-004**: 续期后 MUST 把证书推到腾讯云 CDN（`ewhisper.cn`、`www.ewhisper.cn`）与七牛 CDN
  （`pic-cdn.ewhisper.cn`），调用口径与原脚本一致。
- **FR-005**: 部署 MUST 幂等——证书内容未变时不产生任何云端写入。
- **FR-006**: 账号密钥、证书与私钥 MUST 只存在于集群内的持久卷，MUST NOT 出现在 Git 里。
- **FR-007**: 云端密钥 MUST 通过 External Secrets 从 `global-secrets` 注入，仓库里只能有占位符。
- **FR-008**: 部署 MUST 以 bjw-s `app-template` chart 的形式纳入本仓库，交给 ArgoCD 自动同步。
- **FR-009**: 失败 MUST 可观测：非零退出码、保留失败 Job、日志包含本地指纹与证书指纹。
- **FR-010**: 文档 MUST 说明四把密钥的 tfvars 键名、手工补种方式（不破坏 `restic-*`）与旧 crontab 的下线步骤。

### Key Entities

- **证书状态卷**（PVC `acme-ewhisper-data`）：acme.sh 的 `--config-home`，含账号密钥、`account.conf`、
  `ewhisper.cn/` 证书与私钥，以及「已部署指纹」文件。
- **外部机密**（`global-secrets/external` 的四项）：腾讯 SecretId/SecretKey、七牛 AK/SK。
- **部署指纹**：`fullchain.cer` 的 sha256，用来判断是否需要对两家 CDN 做写入。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 台式机停机 30 天，续期仍在该证书到期前完成，且不需要人工干预。
- **SC-002**: 三个 CDN 域名的线上证书指纹，与 Job 日志里的证书指纹完全一致。
- **SC-003**: 单轮 CronJob 在 5 分钟内结束；每个续期窗口内 Let's Encrypt 只被签发一次。
- **SC-004**: 连续 3 轮「证书未变」的触发中，腾讯云与七牛 API 写入次数为 0。
- **SC-005**: 仓库（含本次新增文件）搜索不到真实密钥；`detect-private-key` hook 通过。

## Assumptions

- 集群出网可达 Let's Encrypt、DNSPod/腾讯云 API、七牛 API（既有应用已在用公网出站）。
- 集群有默认可用的 RWO StorageClass（其他应用已在用）。
- 那对腾讯云密钥同时有 DNSPod（签发）与 SSL/CDN（上传、部署）权限；七牛 AK/SK 有证书与域名配置权限。
- acme.sh 注册不需要邮箱（原台式机账号同样未保存 `ACCOUNT_EMAIL`，已实测可用）。
- 集群内没有工作负载需要这张证书，因此不需要把证书同步成 TLS Secret。
- `pic.ewhisper.cn` 已退役，不需要再签进 SAN。
