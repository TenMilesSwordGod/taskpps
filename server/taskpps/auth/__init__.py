"""认证模块：密码哈希、JWT 签发/校验、依赖注入。

设计决策：
- 独立 auth 包而非散落在 api/middleware，便于后续扩展（OAuth、SSO 等）。
- security.py 只做无状态工具函数，不依赖 DB session，方便单测。
- dependencies.py 提供 FastAPI 依赖注入，但本次不挂载到路由（spec 要求预留）。
"""
