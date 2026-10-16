local get_tags(status, severity) =
  // https://docs.ntfy.sh/emojis
  if status == "resolved" then
    ["tada"]
  else
    std.get({
      critical: ["rotating_light"],
      warning: ["warning"],
      info: ["newspaper"],
    }, severity, ["question"]);

local get_priority(status, severity) =
  // https://docs.ntfy.sh/publish/#message-priority
  if status == "resolved" then
    2
  else
    std.get({
      critical: 5,
      warning: 3,
      info: 1,
    }, severity, 3);

local get_actions(status, annotations) =
  // https://docs.ntfy.sh/publish/#action-buttons
  if status == "resolved" || !("runbook_url" in annotations) then
    []
  else
    [
      {
        action: "view",
        label: "Open runbook",
        url: annotations.runbook_url,
      },
    ];

local severity_rank = { critical: 3, warning: 2, info: 1 };
local rank_to_severity = { "3": "critical", "2": "warning", "1": "info" };

local alert_severity(alert) = std.get(alert.labels, "severity", "");

// Alertmanager 按 group_by: [namespace] 合并告警，一次 webhook 可能带 N 条；
// priority/tags 取组内最高严重度，不知道的 severity 按 0 处理并退回第一条的值。
local group_severity(alerts) =
  local ranks = [std.get(severity_rank, alert_severity(a), 0) for a in alerts];
  local top = std.foldl(function(acc, r) if r > acc then r else acc, ranks, 0);
  if top > 0 then rank_to_severity[std.toString(top)] else alert_severity(alerts[0]);

local alerts = body.alerts;
local alert_count = std.length(alerts);
local severity = group_severity(alerts);
// 多条告警时 title 只报条数（alertname 各不相同），单条保持原样
local title =
  if alert_count == 1 then alerts[0].labels.alertname else std.toString(alert_count) + " alerts";
// runbook 按钮取组内第一条带 runbook_url 的告警
local action_annotations =
  local with_url = [a.annotations for a in alerts if "runbook_url" in a.annotations];
  if std.length(with_url) > 0 then with_url[0] else {};

{
  topic: env.NTFY_TOPIC,
  title: "[" + std.asciiUpper(body.status) + "] " + title,
  message: std.join("\n\n", [a.annotations.description for a in alerts]),
  tags: get_tags(body.status, severity),
  priority: get_priority(body.status, severity),
  actions: get_actions(body.status, action_annotations),
}
