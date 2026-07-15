# Security policy / 安全说明

This repository is archived and does not receive regular security maintenance.
Do not expose the workbench directly to the public internet. Bind it to
`127.0.0.1` or place it behind authentication and a trusted reverse proxy.

The optional LLM compression feature sends the supplied prompt and API key to
the configured provider. Keys are not intentionally persisted by the UI, but
operators remain responsible for provider trust, transport security, logs, and
retention policies.

本仓库已经归档，不再进行常规安全维护。请勿将工作台直接暴露到公网；应绑定
`127.0.0.1`，或置于带身份验证的可信反向代理之后。

可选的 LLM 压缩功能会把 Prompt 和 API Key 发送到所配置的提供商。界面不会
主动持久化 Key，但提供商可信度、传输安全、日志与数据保留仍由部署者负责。
