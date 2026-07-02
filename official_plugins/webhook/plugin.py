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
        "method": {
            "type": "string",
            "required": False,
            "label": "HTTP 方法",
            "enum": ["POST", "PUT", "PATCH"],
            "default": "POST",
        },
        "payload": {"type": "string", "required": False, "label": "请求体 (JSON 字符串)"},
        "headers": {"type": "string", "required": False, "label": "自定义 Headers (key=value,key=value)"},
        "timeout": {"type": "string", "required": False, "label": "超时秒数", "default": "10"},
        "retry": {"type": "string", "required": False, "label": "重试次数", "default": "3"},
        "preset": {"type": "string", "required": False, "label": "内置模板", "enum": ["slack", "feishu", "dingtalk"]},
        "message": {"type": "string", "required": False, "label": "消息内容 (preset 模式)"},
    }

    def __init__(
        self, url, method=None, payload=None, headers=None, timeout=None, retry=None, preset=None, message=None
    ):
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
            return json.dumps(
                {
                    "msg_type": "text",
                    "content": {"text": self.message},
                }
            )
        elif self.preset == "dingtalk":
            return json.dumps(
                {
                    "msgtype": "text",
                    "text": {"content": self.message},
                }
            )
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
        """生成 Python urllib 脚本，替代 curl 以兼容无 curl 的平台"""
        import json as _json

        payload = self._build_preset_payload() if self.preset else (self.payload or "")
        headers = self._build_preset_headers() if self.preset else self._parse_headers()

        script = (
            "import json, sys, time, urllib.request, urllib.error\n"
            "url = " + _json.dumps(self.url) + "\n"
            "method = " + _json.dumps(self.method) + "\n"
            "payload = " + _json.dumps(payload) + "\n"
            "headers = " + _json.dumps(headers) + "\n"
            "timeout = " + str(self.timeout) + "\n"
            "max_retry = " + str(self.retry) + "\n"
            "for attempt in range(1, max_retry + 1):\n"
            "    try:\n"
            "        req = urllib.request.Request(url, method=method)\n"
            "        for k, v in headers.items():\n"
            "            req.add_header(k, v)\n"
            "        if payload:\n"
            "            req.data = payload.encode('utf-8')\n"
            "        with urllib.request.urlopen(req, timeout=timeout) as resp:\n"
            "            body = resp.read().decode('utf-8', errors='replace')\n"
            "            print(f'[webhook] {resp.status} {resp.reason}')\n"
            "            if body:\n"
            "                print(f'[webhook] body: {body[:500]}')\n"
            "            sys.exit(0)\n"
            "    except urllib.error.HTTPError as e:\n"
            "        body = e.read().decode('utf-8', errors='replace') if e.fp else ''\n"
            "        print(f'[webhook] HTTP {e.code}: {body[:500]}')\n"
            "        if attempt < max_retry:\n"
            "            time.sleep(2)\n"
            "        else:\n"
            "            sys.exit(1)\n"
            "    except Exception as e:\n"
            "        print(f'[webhook] error: {e}')\n"
            "        if attempt < max_retry:\n"
            "            time.sleep(2)\n"
            "        else:\n"
            "            sys.exit(1)\n"
        )
        # 写临时文件避免 shell 引号嵌套问题
        return (
            "_wf=$(mktemp /tmp/webhook_XXXXXX.py) && "
            f"cat > \"$_wf\" <<'_WEOF_'\n{script}_WEOF_\n"
            'python3 "$_wf"; rc=$?; rm -f "$_wf"; exit $rc'
        )

    def _parse_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.headers:
            for item in self.headers.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    headers[k.strip()] = v.strip()
        return headers
