# CLI 配置

CLI 通过以下方式(优先级从高到低)获取配置:

1. 命令行参数
2. 环境变量
3. 配置文件

## 服务地址

```bash
# 命令行
ppsctl --server http://10.0.0.1:26521 run deploy.yaml

# 环境变量
export PPSCTL_SERVER=http://10.0.0.1:26521
ppsctl run deploy.yaml

# 配置文件
# ~/.taskpps/config.yaml
server: http://10.0.0.1:26521
```

## API 密钥

如后端启用了 API 密钥认证:

```bash
# 命令行
ppsctl --api-key your-secret-key run deploy.yaml

# 环境变量
export PPSCTL_API_KEY=your-secret-key

# 配置文件
api_key: your-secret-key
```

## 配置文件路径

CLI 按以下顺序查找配置文件,使用第一个找到的:

1. `./.taskpps/config.yaml` — 项目级
2. `~/.taskpps/config.yaml` — 用户级
3. `/etc/taskpps/config.yaml` — 系统级

配置文件示例:

```yaml
# .taskpps/config.yaml
server: http://127.0.0.1:26521
api_key: ""
```

## 环境变量参考

| 环境变量 | 对应标志 | 说明 |
|:--|:--|:--|
| `PPSCTL_SERVER` | `--server` | 后端服务地址 |
| `PPSCTL_API_KEY` | `--api-key` | API 密钥 |
