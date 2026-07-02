class WebhookPlugin:
    """## Webhook 通知器

向外部 URL 发送 HTTP 请求，支持 Slack/飞书/钉钉/自定义。

### YAML 用法

**通用 Webhook：**

```yaml
tasks:
  - name: notify
    plugin: webhook
    params:
      url: "https://your-webhook-url.com/notify"
      payload: '{"status":"success","run":"${TASKPPS_RUN_ID}"}'
      headers: "Authorization=Bearer token,X-Custom=value"
      timeout: "10"
      retry: "3"
```

**Slack：**

```yaml
tasks:
  - name: slack-alert
    plugin: webhook
    params:
      url: "https://hooks.slack.com/services/T.../B.../xxx"
      preset: slack
      message: "Deploy completed!"
```

**飞书：**

```yaml
tasks:
  - name: feishu-notify
    plugin: webhook
    params:
      url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
      preset: feishu
      message: "Pipeline failed!"
```

**钉钉：**

```yaml
tasks:
  - name: dingtalk-alert
    plugin: webhook
    params:
      url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
      preset: dingtalk
      message: "Build finished"
```

### 参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | 是 | — | Webhook URL |
| `method` | 否 | `POST` | HTTP 方法：`POST` / `PUT` / `PATCH` |
| `payload` | 否 | — | 自定义 JSON 请求体 |
| `headers` | 否 | — | 自定义 Headers（`key=value,key=value`） |
| `timeout` | 否 | `10` | 超时秒数 |
| `retry` | 否 | `3` | 重试次数 |
| `preset` | 否 | — | 内置模板：`slack` / `feishu` / `dingtalk` |
| `message` | 否 | — | preset 模式下的消息内容 |
"""
    type = "executor"
    version = "1.0.0"
    params_schema = {
        "url": {"type": "string", "required": True, "label": "Webhook URL"},
        "method": {"type": "string", "required": False, "label": "HTTP 方法", "enum": ["POST", "PUT", "PATCH"], "default": "POST"},
        "payload": {"type": "string", "required": False, "label": "请求体 (JSON 字符串)"},
        "headers": {"type": "string", "required": False, "label": "自定义 Headers (key=value,key=value)"},
        "timeout": {"type": "string", "required": False, "label": "超时秒数", "default": "10"},
        "retry": {"type": "string", "required": False, "label": "重试次数", "default": "3"},
        "preset": {"type": "string", "required": False, "label": "内置模板", "enum": ["slack", "feishu", "dingtalk"]},
        "message": {"type": "string", "required": False, "label": "消息内容 (preset 模式)"},
    }

    def __init__(self, url, method=None, payload=None, headers=None, timeout=None, retry=None, preset=None, message=None):
        self.url = url
        self.method = (method or "POST").upper()
        self.payload = payload
        self.headers = headers
        self.timeout = int(timeout) if timeout else 10
        self.retry = int(retry) if retry else 3
        self.preset = preset
        self.message = message or ""

    def _build_preset_payload(self) -> str:
        """根据 preset 生成标准 payload"""
        import json
        if self.preset == "slack":
            return json.dumps({"text": self.message})
        elif self.preset == "feishu":
            return json.dumps({
                "msg_type": "text",
                "content": {"text": self.message},
            })
        elif self.preset == "dingtalk":
            return json.dumps({
                "msgtype": "text",
                "text": {"content": self.message},
            })
        return self.payload or ""

    def _build_preset_headers(self) -> dict[str, str]:
        """根据 preset 生成默认 headers"""
        headers = {"Content-Type": "application/json"}
        if self.headers:
            for item in self.headers.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    headers[k.strip()] = v.strip()
        return headers

    def build_command(self) -> str:
        import shlex

        payload = self._build_preset_payload() if self.preset else (self.payload or "")
        headers = self._build_preset_headers() if self.preset else self._parse_headers()

        parts = ["curl", "-s", "-S"]
        parts.extend(["-X", self.method])
        parts.extend(["--max-time", str(self.timeout)])
        parts.extend(["--retry", str(self.retry)])
        parts.extend(["--retry-delay", "2"])
        parts.extend(["--retry-max-time", str(self.timeout * self.retry)])

        for k, v in headers.items():
            parts.extend(["-H", f"{k}: {v}"])

        if payload:
            parts.extend(["-d", payload])

        parts.append(shlex.quote(self.url))

        cmd = " ".join(parts)
        # 包裹在 sh -c 中确保 shell 正确处理引号
        return f"sh -c {shlex.quote(cmd)}"

    def _parse_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.headers:
            for item in self.headers.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    headers[k.strip()] = v.strip()
        return headers
