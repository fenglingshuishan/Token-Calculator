# Archive notice / 归档说明

## English

Token Calculator was created to reduce LLM input-token cost by cleaning or
compressing prompts. The project demonstrated that counting tokens is easy,
while proving economic benefit is not: managed agents assemble hidden system
instructions, tool schemas, history, retrieved context, and intermediate tool
results that an end user cannot fully inspect or control. Prompt caching can
also make a longer stable prefix cheaper than a shorter prefix that changes
frequently.

The repository is therefore frozen as a reference implementation for a future
self-managed Agent/API gateway, where the operator can observe the complete
request, provider usage fields, cache reads and writes, output tokens, retries,
latency, and task-quality evaluations.

The archived release remains useful for:

- comparing tokenizer outputs;
- demonstrating explicit exact-versus-estimated counts;
- conservative local text cleanup;
- experimenting with compression-cost amortization;
- embedding the FastAPI application in a controlled internal service.

It is not evidence that a shorter prompt preserves semantics or reduces the
total cost of a managed agent. Pricing data is a dated snapshot and must be
verified before financial use. No roadmap or support commitment is implied.

## 中文

Token Calculator 最初希望通过清理或压缩 Prompt 来降低 LLM 输入 Token 费用。
项目最终证明：计算 Token 很容易，证明经济收益却很难。托管 Agent 会组装用户
无法完整查看或控制的系统指令、工具 Schema、历史记录、检索上下文和中间工具
结果；Prompt caching 也可能使一个较长但稳定的前缀，比一个较短却频繁变化的
前缀更便宜。

因此，本仓库冻结为未来自建 Agent/API 网关的参考实现。只有在运营者能够观察
完整请求、提供商 usage、缓存读写、输出 Token、重试、延迟与任务质量评测时，
才可能严谨地判断一项优化是否真正省钱。

归档版本仍可用于：

- 对比不同 tokenizer 的结果；
- 演示“精确计数”和“估算计数”的明确区分；
- 进行保守的本地文本清理；
- 实验压缩成本的摊销与回本次数；
- 将 FastAPI 应用嵌入受控的内部服务。

本项目不能证明更短的 Prompt 保持语义，也不能证明它会降低托管 Agent 的总
费用。价格数据只是带日期的快照，财务使用前必须重新核对。本仓库不承诺后续
路线图或持续支持。
