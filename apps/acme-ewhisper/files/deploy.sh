#!/bin/sh
# 把状态目录里的 ewhisper.cn 证书推到腾讯云 CDN（@ 与 www）和七牛 CDN（pic-cdn）。
# 由 renew.sh 调用；证书指纹没变就直接退出，所以重复执行（含失败重跑）是安全的。
set -eu

DOMAIN=ewhisper.cn
QINIU_DOMAINS="pic-cdn.ewhisper.cn"
STATE_DIR="${LE_CONFIG_HOME:-/acme.sh}"
CERT="$STATE_DIR/$DOMAIN/fullchain.cer"
KEY="$STATE_DIR/$DOMAIN/$DOMAIN.key"
FP_FILE="$STATE_DIR/.deployed-$DOMAIN.sha256"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

[ -s "$CERT" ] && [ -s "$KEY" ] || die "证书文件缺失：$CERT / $KEY"
[ -n "${Tencent_SecretId:-}" ] && [ -n "${Tencent_SecretKey:-}" ] || die "缺少 Tencent_SecretId / Tencent_SecretKey"
[ -n "${QINIU_ACCESS_KEY:-}" ] && [ -n "${QINIU_SECRET_KEY:-}" ] || die "缺少 QINIU_ACCESS_KEY / QINIU_SECRET_KEY"

FP=$(sha256sum "$CERT" | awk '{print $1}')
if [ "$FP" = "$(cat "$FP_FILE" 2>/dev/null || true)" ]; then
  log "证书与上次部署一致，无需推送"
  exit 0
fi

# ---- 腾讯云 SSL / CDN ----
# 腾讯云 API v3 只接受 TC3-HMAC-SHA256 签名；这里只有一个 host、参数全在 JSON body 里，
# 所以签名串是固定的几行，用 openssl + jq 就够，不必在镜像里塞 tccli。
_tc_hex() { openssl dgst -sha256 -hex | sed 's/^.*= //'; }

tc_api() { # $1=action $2=json body；成功时输出整个响应 JSON
  _action=$1
  _payload=$2
  _host=ssl.tencentcloudapi.com
  _now=$(date -u '+%Y-%m-%d %s')
  _date=${_now% *}
  _ts=${_now#* }
  _ctype='application/json; charset=utf-8'
  _canonical=$(printf 'POST\n/\n\ncontent-type:%s\nhost:%s\n\ncontent-type;host\n%s' \
    "$_ctype" "$_host" "$(printf '%s' "$_payload" | _tc_hex)")
  _sts=$(printf 'TC3-HMAC-SHA256\n%s\n%s/ssl/tc3_request\n%s' \
    "$_ts" "$_date" "$(printf '%s' "$_canonical" | _tc_hex)")
  _key=$(printf '%s' "$_date" | openssl dgst -sha256 -hmac "TC3$Tencent_SecretKey" | sed 's/^.*= //')
  _key=$(printf '%s' ssl | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$_key" | sed 's/^.*= //')
  _key=$(printf '%s' tc3_request | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$_key" | sed 's/^.*= //')
  _sig=$(printf '%s' "$_sts" | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$_key" | sed 's/^.*= //')
  _resp=$(curl -sS --fail-with-body -X POST "https://$_host/" \
    -H "Authorization: TC3-HMAC-SHA256 Credential=$Tencent_SecretId/$_date/ssl/tc3_request, SignedHeaders=content-type;host, Signature=$_sig" \
    -H "Content-Type: $_ctype" -H "X-TC-Action: $_action" \
    -H "X-TC-Version: 2019-12-05" -H "X-TC-Timestamp: $_ts" \
    --data-binary "$_payload") || die "腾讯云 $_action 请求失败：$_resp"
  _err=$(printf '%s' "$_resp" | jq -r '.Response.Error.Message // empty')
  [ -z "$_err" ] || die "腾讯云 $_action 失败：$_err"
  printf '%s' "$_resp"
}

_upload=$(jq -cn --rawfile cert "$CERT" --rawfile key "$KEY" \
  '{CertificatePublicKey:$cert, CertificatePrivateKey:$key, Alias:"ewhisper.cn-acme", Repeatable:true}')
_resp=$(tc_api UploadCertificate "$_upload")
_cert_id=$(printf '%s' "$_resp" | jq -r '.Response.CertificateId // empty')
[ -n "$_cert_id" ] || die "腾讯云上传证书后没有拿到 CertificateId"
log "腾讯云证书已上传：$_cert_id"

# 实例格式是「域名|计费开关」，off = CDN -> 域名管理 -> HTTPS服务关；应设置为 on，即HTTPS服务开。
_deploy=$(jq -cn --arg id "$_cert_id" \
  '{CertificateId:$id, ResourceType:"cdn", InstanceIdList:["ewhisper.cn|on","www.ewhisper.cn|on"]}')
_resp=$(tc_api DeployCertificateInstance "$_deploy")
_record=$(printf '%s' "$_resp" | jq -r '.Response.DeployRecordId // empty')
[ -n "$_record" ] || die "腾讯云 CDN 部署后没有拿到 DeployRecordId"
log "腾讯云 CDN 已部署：DeployRecordId=$_record"

# ---- 七牛 CDN ----
# 七牛有两套鉴权：证书接口用 QBox（只签 path），域名配置用 Qiniu（签 method/path/头/body）。
_qi_b64() { openssl dgst -sha1 -hmac "$QINIU_SECRET_KEY" -binary | openssl base64 -A | tr '+/' '-_'; }

_body=$(jq -cn --rawfile pri "$KEY" --rawfile ca "$CERT" \
  '{name:"ewhisper.cn-acme", pri:$pri, ca:$ca}')
_resp=$(curl -sS --fail-with-body -X POST "https://api.qiniu.com/sslcert" \
  -H "Authorization: QBox $QINIU_ACCESS_KEY:$(printf '%s\n' /sslcert | _qi_b64)" \
  -H 'Content-Type: application/json' --data-binary "$_body") || die "七牛上传证书失败：$_resp"
_qi_cert=$(printf '%s' "$_resp" | jq -r '.certID // empty')
[ -n "$_qi_cert" ] || die "七牛上传证书后没有拿到 certID：$_resp"
log "七牛证书已上传：$_qi_cert"

for _domain in $QINIU_DOMAINS; do
  _path="/domain/$_domain/httpsconf"
  _body=$(jq -cn --arg id "$_qi_cert" '{certId:$id, forceHttps:true, http2Enable:true}')
  _qd=$(date -u +%Y%m%dT%H%M%SZ)
  _sig=$({ printf 'PUT %s\nHost: %s\nContent-Type: application/json\nX-Qiniu-Date: %s\n\n' \
    "$_path" api.qiniu.com "$_qd"; printf '%s' "$_body"; } | _qi_b64)
  _resp=$(curl -sS --fail-with-body -X PUT "https://api.qiniu.com$_path" \
    -H "Authorization: Qiniu $QINIU_ACCESS_KEY:$_sig" -H 'Content-Type: application/json' \
    -H "X-Qiniu-Date: $_qd" --data-binary "$_body") || die "七牛 $_domain 绑定证书失败：$_resp"
  log "七牛 $_domain 已绑定证书 $_qi_cert"
done

printf '%s\n' "$FP" >"$FP_FILE"
log "CDN 部署完成：fullchain sha256=$FP"
# 证书指纹（与 openssl s_client 看到的可比对）留在日志里当部署留痕
log "证书指纹：$(openssl x509 -in "$CERT" -noout -fingerprint -sha256)"
