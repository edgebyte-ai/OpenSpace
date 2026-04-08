# OpenSpace 全面替换为 Agent CLI 的架构设计

## 1. 目标与范围

本文描述如何将 OpenSpace 从「内置 GroundingAgent 主导」迁移为「外部 Agent CLI 主导」，同时保留：

- Skill 注册/检索/演化
- 任务评估与质量反馈
- MCP 工具生态

并实现跨 CLI 适配（Codex/Copilot/Cursor/Claude Code）的统一控制协议。

---

## 2. 当前实现基线

当前系统已具备：

1. **CLI Adapter 层**：命令解析、提示词构建、执行结果解析、会话 JSONL 解析。  
2. **显式状态机工具**：
   - `cli_begin_execution`
   - `cli_report_step`
   - `cli_finalize_execution`
3. **external_cli 执行模式**：`execute_task` 在 `OPENSPACE_PRIMARY_AGENT_MODE=external_cli` 下可走外部 CLI 路径。

但仍需进一步强化：强一致状态控制、持久化状态、技能与 adapter 兼容约束。

---

## 3. 总体架构

```text
User Agent / Orchestrator
        │
        │ MCP
        ▼
OpenSpace MCP Server
  ├─ CLI Control Plane (state machine tools)
  ├─ Adapter Layer (codex/copilot/cursor/claude_code)
  ├─ Skill Store / Registry / Search
  ├─ Analyzer / Evolver
  └─ Recording + Quality Feedback
        │
        ▼
External Agent CLI Runtime
```

关键原则：

- **控制在 MCP Server**：phase 转换、失败判定、回退策略、清理策略由服务端控制。
- **执行在 Agent CLI**：CLI 负责执行动作并按协议上报。
- **兼容性在 Skill 层建模**：技能必须显式声明或推导适配器适用性。

---

## 4. 控制协议（建议收敛为强制 ACK 模式）

### 4.1 开始执行
`cli_begin_execution`

返回：
- `execution_id`
- 当前 `phase`（skill/fallback）
- `selected_skills`
- 策略（fallback_on_first_error 等）

### 4.2 步骤上报
`cli_report_step`

请求：
- action/status/detail/artifacts

响应：
- `next_action`（continue / switch_to_fallback / stop）
- 若需要 fallback，返回 `cleanup_required` 与清理结果

### 4.3 结束执行
`cli_finalize_execution`

请求：
- final response/status

响应：
- 标准化任务结果（含分析/进化产物）

> 建议升级：未按顺序调用工具则拒绝 finalize（强约束）。

---

## 5. Skill 数据模型变更（重点）

你提出的点是正确的：**Skill 必须有 adapter 维度**，否则“可用性”不可控。

## 5.1 新字段建议

在 Skill 元数据（文件 frontmatter + DB）增加：

- `adapter`: `"codex" | "copilot" | "cursor" | "claude_code" | "generic"`
- `compatible_adapters`: string[]
- `required_tools`: string[]
- `tool_profile`: object（可选，记录该 adapter 下工具约束）
- `created_by_adapter`: string（进化产物来源）
- `validated_on_adapter`: string[]（测试通过的 adapter）

### 5.2 检索优先级

Skill 检索排序建议：

1. `adapter == 当前 adapter`
2. `compatible_adapters` 包含当前 adapter
3. `adapter == generic`
4. 其余降权或过滤

### 5.3 进化标注

进化产物必须写入：

- `created_by_adapter = 当前执行 adapter`
- `compatible_adapters` 初始至少包含 `created_by_adapter`
- 若跨 adapter 回归通过，再扩展 `validated_on_adapter`

---

## 6. Analyzer/Evolver 的 CLI 化

目标：当 external_cli 模式开启时，分析与进化也走 Agent CLI。

建议实现：

1. Analyzer CLI Prompt（结构化 JSON 输出）
2. Evolver CLI Prompt（结构化 `evolved_skills` 输出）
3. 将分析/进化结果写回 Skill Store 与录制元数据
4. 若 CLI 分析失败，可配置“硬失败”或“降级到内部分析”

---

## 7. 迁移计划

### 阶段 A（已完成基础）
- adapter 层 + external_cli 路径 + 状态机工具

### 阶段 B（本次文档重点）
- Skill DB 增加 adapter 字段与索引
- 检索排序引入 adapter 优先级
- 进化写回 adapter 来源字段

### 阶段 C（收敛）
- 强一致状态机（强制 ACK）
- 状态持久化（内存 -> DB/Redis）
- 渐进下线 GroundingAgent 主执行路径

---

## 8. 验收标准

- external_cli 模式下，执行/评估/进化全链路无需内部 LLM 主执行
- Skill 检索命中率在 adapter 维度可解释
- 进化技能有明确 adapter 归属并可追踪
- 状态机调用顺序可审计、可重放

---

## 9. 风险与缓解

- 风险：不同 CLI 会话日志格式不稳定  
  缓解：adapter 独立解析器 + 版本探测 + structured report 兜底。

- 风险：跨 adapter skill 误用  
  缓解：adapter 字段 + required_tools 过滤 + 回归验证。

- 风险：状态机中断导致脏状态  
  缓解：持久化执行状态 + TTL + 可恢复 finalize。

