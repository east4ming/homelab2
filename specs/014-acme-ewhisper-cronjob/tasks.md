# Tasks: ewhisper.cn 证书续期搬进集群 CronJob

**Input**: Design documents from `specs/014-acme-ewhisper-cronjob/`

**Prerequisites**: plan.md (required), spec.md (required)

**Organization**: 按交付链路分组，每个任务可独立验证。

## Phase 1: 设计

- [x] T001 读源实现：`~/.acme.sh` 的 acme.sh 版本（v3.1.7）、crontab、`deploy-ewhisper-cdn.sh`、`qiniu-deploy.py`、`account.conf` 里保存的键
- [x] T002 确认 acme.sh 的运行时语义：`--home`（脚本/dnsapi）与 `--config-home`（账号与证书）分离；`dns_tencent` 只认 `Tencent_SecretId/Key`；`AUTO_UPGRADE` 仅在值为 `1` 时触发
- [x] T003 确认镜像能力：`neilpang/acme.sh:3.1.6` 自带 `dnsapi/dns_tencent.sh`、`curl`、`openssl`、`jq`、`coreutils`，入口 `/entry.sh` 可被覆盖
- [x] T004 对照本仓库部署惯例：`apps/*` 自动发现、`app-template` 5.3.0、`templates/secret.yaml` 走 ESO、`files/` + `.Files.Glob` 装脚本
- [x] T005 确认机密链路：`external/terraform.tfvars` → `global-secrets/external` → `ExternalSecret`；`external` 里已有 `restic-*`，只能 merge
- [x] T006 定幂等策略：`fullchain.cer` 的 sha256 落盘为「已部署指纹」，变了才推 CDN

## Phase 2: 实现

- [x] T007 `apps/acme-ewhisper/Chart.yaml`：`app-template` 5.3.0 依赖
- [x] T008 `apps/acme-ewhisper/values.yaml`：`type: cronjob`、`11 0,6,12,18 * * *` / `Asia/Shanghai`、Forbid、`activeDeadlineSeconds: 1800`、`backoffLimit: 2`、`AUTO_UPGRADE=0`、资源限额
- [x] T009 `apps/acme-ewhisper/files/renew.sh`：PVC 无证书则 `--issue`，否则 `--cron`，随后 `exec deploy.sh`
- [x] T010 `apps/acme-ewhisper/files/deploy.sh`：指纹判重、TC3-HMAC-SHA256 调腾讯云 `UploadCertificate` + `DeployCertificateInstance`、七牛 `POST /sslcert` + `PUT /domain/<d>/httpsconf`
- [x] T011 `apps/acme-ewhisper/templates/scripts.yaml`：`(.Files.Glob "files/*.sh").AsConfig` → ConfigMap `acme-ewhisper-scripts`
- [x] T012 `apps/acme-ewhisper/templates/secret.yaml`：ExternalSecret 显式 `data[]` 四项
- [x] T013 `apps/acme-ewhisper/values.yaml`：PVC `acme-ewhisper-data` 挂 `/acme.sh`、ConfigMap 挂 `/scripts`
- [x] T014 `scripts/backup-coverage`：`acme-ewhisper/acme-ewhisper-data` 列入豁免并写明理由

## Phase 3: 验证

- [x] T015 `helm dependency update` + `helm template`：CronJob / PVC / ConfigMap / ExternalSecret 与挂载名逐个核对
- [x] T016 `helm lint`、`shellcheck -s sh files/*.sh` 通过
- [x] T017 渲染后的 ConfigMap 内容与 `files/*.sh` 逐字节一致
- [x] T018 腾讯云 TC3 签名对 `ssl:DescribeCertificates` 只读调用返回 200（真密钥）
- [x] T019 七牛 `QBox`（`GET /sslcert`）与 `Qiniu`（`GET /domain/<name>`）只读调用均 200（真 AK/SK）
- [x] T020 真实镜像内 stub 跑通：首签分支、续期分支、指纹跳过、腾讯 API 报错（非零退出且不写指纹）、缺环境变量快速失败
- [x] T021 `pre-commit run`（yamllint/shellcheck/helmlint/eof/detect-private-key）与 `mkdocs build --strict` 通过
- [x] T022 全仓库搜索真实密钥模式：无命中，只有占位符

## Phase 4: 文档

- [x] T023 `docs/concepts/certificate-management.md`：新增 ewhisper.cn 章节（链路图、调度、状态、机密表、运维命令、已知坑、迁移步骤）
- [x] T024 `external/terraform.tfvars.example`：四个键的占位符与所需云 API 权限
- [x] T025 `specs/014-acme-ewhisper-cronjob/{spec,plan,tasks}.md` + `checklists/requirements.md`
- [x] T026 `AGENTS.md` 当前 Plan 指向 014
- [x] T027 本地 `external/terraform.tfvars` 按集群现状补齐（`ntfy` + `restic-*` + 四把 acme 键），避免以后 import 进 state 时删键

## Phase 5: 线上应用与交付流程（versioning.md）

- [x] T028 集群补种机密：`kubectl -n global-secrets patch secret external --type=merge` 写入四项，校验 `restic-*` 未变、ESO ClusterSecretStore `Ready=True`
- [x] T029 关联资源现状核对：5 个命名空间已存在、`monitoring-system/webhook-transformer` 已存在，`make external` 无剩余工作
- [x] T030 主题分支 `014-acme-ewhisper-cronjob` + Conventional Commits
- [x] T031 推送分支、在 Gitea 开 PR 并合入 `master`
- [x] T032 `docs/reference/changelog.md` 增加 `v2026.11.02` 条目（含本次聚合的三次 Renovate 合并）
- [x] T033 打 annotated tag `v2026.11.02`，推送 Gitea + GitHub 并双侧复核
- [x] T034 Gitea（权威）与 GitHub（镜像）创建 Release，正文与 changelog 一致
- [ ] T035 台账外：确认集群内首轮 CronJob 签发并推 CDN 成功、线上指纹对齐后，删除台式机 crontab 行（需人工确认，属独立回退路径）
