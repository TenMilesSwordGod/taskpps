# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

小团队与个人开发者。他们在自己的机器或服务器上自托管 Taskpps，用 CLI（ppsctl）或 Web UI 编排部署、测试、发布等日常任务流水线；没有专职 DevOps，期望几分钟内跑起来、零学习成本。

## Product Purpose

轻量级、可扩展的任务编排系统：替代 Jenkins 等重量级 CI/CD 工具，面向中小团队和项目。一套 Server（Python FastAPI + SQLite）同时管理多个项目（Code/Project 解耦），任务以 YAML 定义，支持 Shell / SSH 远程 / Python invoke 三种任务类型、DAG 依赖编排（拓扑排序、并发、fail/continue 失败策略）、SSE 实时日志与运行历史、WebSocket Agent 远程执行、插件化扩展（触发器/通知器/执行器）、API 密钥认证、中英双语。

## Positioning

像 n8n 一样自托管 + 可视化编排：用户自托管、开箱即用，通过可视化 DAG（React Flow）与 YAML 双通道编排任务流水线，普通开发者无需运维知识即可运行，同时保留"YAML 即配置"的零模板简单性。（已与用户确认：定位为"自托管 + 可视化编排"，n8n-like）

## Operating Context

- 用户自托管 server（单二进制，监听 127.0.0.1:26521），把项目目录注册到 server，通过 project_id 路由。
- 三端协作：ppctl CLI（Go/Cobra）、Web UI（React + Vite，可选）、远程 Agent（Go/WebSocket，断线自动重连）。
- 项目目录结构：pipelines/、agents/、credentials/、tasks/、plugins/（用户插件放项目本地）。
- 典型用法：`ppsctl init --register-current-folder` 注册项目 → `ppsctl run deploy.yaml TAG=latest` 执行流水线。
- 文档体系：wiki/ 与 server/docs/ 双份完整中文文档。

## Capabilities and Constraints

- 任务类型：Shell 命令 / SSH 远程 / Python invoke。
- DAG 编排：拓扑排序、并发执行、失败策略（fail / continue）。
- 可观测：SSE 实时日志、运行历史、状态跟踪。
- 插件化：触发器（Cron）、通知器、执行器均可扩展；插件目录可配置（plugins/）。
- 安全：API 密钥认证（可选中间件）。
- 国际化：内建中文 / English（taskpps.yaml 中 locale 可配置）。
- 技术栈：server = Python FastAPI + SQLModel + aiosqlite（uv 管理依赖）；cli = Go + Cobra；web = React 18 + TypeScript + Vite + Ant Design 5 + Tailwind + React Flow（xyflow）+ CodeMirror + Zustand + TanStack Query；execution_agent = Go + WebSocket。
- 术语：pipeline（流水线）、task（任务）、agent（远程执行节点）、project（server 侧管理的项目，与代码仓库 Code 解耦）。

## Brand Commitments

产品名 Taskpps，MIT 许可证。已确认无其他特殊品牌承诺与约束（命名、logo、宣传口径均无绑定要求）。

## Evidence on Hand

- README.md：特性、架构图、快速开始、项目结构（仓库根）。
- wiki/ 与 server/docs/：完整中文文档（快速开始、架构、流水线配置、任务类型、执行器、Agent、插件系统、触发器、API 参考、部署、开发指南、CLI 概览与命令、CLI 配置）。
- taskpps.yaml：服务端配置样例（locale、server 地址、executor 超时与并发、env、plugins、triggers）。
- web/：React Web UI 源码，含 Playwright e2e 与 Vitest 单元测试、需求文档 req.md / req-settings-center.md。
- 无正式官网、客户名单、案例、基准测试数据 —— 未来设计工作不得虚构这些内容。

## Product Principles

1. 轻量至上：一套二进制、几分钟自托管，任何面向用户的复杂度都必须服务于这一承诺。
2. YAML 即配置：零模板，全局默认值 + 任务级覆盖，不引入额外 DSL。
3. 可视化与代码双通道：用户在浏览器里编排 DAG 与用 YAML/CLI 完成同一件事，体验必须等价。
4. 一套 Server 管多项目：Code/Project 解耦是架构级卖点，新功能不得破坏该模型。
5. 插件优先扩展：触发器、通知器、执行器可插拔，核心保持精简。
