#!/bin/sh
# ewhisper.cn 证书：Let's Encrypt DNS-01（DNSPod / 腾讯云）签发与续期，然后交给 deploy.sh 推到 CDN。
# CronJob 每 6 小时调用一次，真签发时间由 acme.sh 按 ACME ARI 窗口决定。
set -eu

DOMAIN=ewhisper.cn
DOMAIN_ARGS="-d ewhisper.cn -d www.ewhisper.cn -d pic-cdn.ewhisper.cn"
# 镜像里 acme.sh 与 dnsapi 的安装位置（只读）与状态目录（PVC）：
ACME_BIN="${LE_WORKING_DIR:-/acmebin}"
STATE_DIR="${LE_CONFIG_HOME:-/acme.sh}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

if [ -f "$STATE_DIR/$DOMAIN/$DOMAIN.conf" ]; then
  log "续期：acme.sh --cron"
  acme.sh --cron --home "$ACME_BIN" --config-home "$STATE_DIR"
else
  log "首签：状态目录里没有证书，执行 acme.sh --issue"
  # shellcheck disable=SC2086 # $DOMAIN_ARGS 必须按空格拆成多个参数
  acme.sh --issue --server letsencrypt --keylength 2048 --dns dns_tencent \
    --home "$ACME_BIN" --config-home "$STATE_DIR" $DOMAIN_ARGS
fi

exec /bin/sh /scripts/deploy.sh
