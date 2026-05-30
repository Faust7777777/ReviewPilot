# ReviewPilot 设计文档(spec · 2026-05-30)

状态:已通过技术验证([tech-validation](../research/2026-05-30-tech-validation.md)),待评审。

## 1. 定位

> ReviewPilot 不假装全知。它做一件资深 reviewer 最先做、机器却普遍做不好的事:
> **核对这个 PR 是否真的做了它声称要做的事,并对拿不准的地方诚实。**

- **主特色:意图对照** —— 拿 PR 描述 / 关联 issue 当"作者声称要做的事",核对代码做了没、有没有夹带未声明的改动。
- **底色:诚实评审** —— 每条结论绑定 diff 证据 + 置信分级;越过能力边界(业务正确性)就标"需人工确认",绝不硬给权威结论。
- **次要(有余力):爆炸半径** —— 改动影响到哪些调用方。

## 2. 形态与交互

**harness 为主、单 PR 工具为示例入口。** 对外是工具(给 PR 出评审),底层是可度量的 harness。

- **会话模型:session = 一个仓库。** 启动时把目标仓库准备成本地工作区(基础上下文,对抗"片面 diff")。
- **交互:多轮对话,不是一锤子。** reviewer 会被追问、被反驳后解释和修正。
- **记忆:** 单 session 内由对话上下文 + 仓库上下文承载,**不做持久化评审账本**;跨 PR / 跨仓库记忆列为未来扩展。
- **两张脸,共用一个 CLI 引擎:**
  - 终端对话(基于 Aider 的交互式 chat,改为只读 review)——多轮、可追问。
  - 薄 GUI 网页(填 PR 链接 → 渲染 briefing,带置信徽章/证据折叠)——demo 上镜。

**输入口径(GUI):**
- PR 链接 → 完整特色(意图对照 + 上下文检索)。
- diff / patch → 显式降级:页面横幅提示"无仓库上下文/无意图,仅表层检查",自动关闭意图对照与爆炸半径。
- 裸代码 → 劝退,提示提供 PR 链接或 diff。

## 3. 架构(三层 + 引擎/借鉴/原创分工)

```
控制面(编排/上下文/护栏)
  ├─ PR 获取器        ← 借鉴 PR-Agent 的 GitProvider / FilePatchInfo
  ├─ diff 规范化       ← 借鉴 PR-Agent 的 __new/old hunk__ 带行号格式 + 大 PR 分块
  ├─ 意图提取器        ← 原创:从 PR 描述/issue 抽"声称要做的事"
  ├─ 上下文检索器      ← Aider RepoMap + read_only_fnames(按需取调用方/相关文件)
  └─ 诚实护栏          ← 原创:证据门(无 diff 证据则删)+ 置信分级 + 输出配额
求解面
  └─ 分析器           ← Aider AskCoder(只读)+ 原创 prompt:总结/意图对照/风险/建议
                         经 litellm 接 DeepSeek / Anthropic / OpenAI
评估面
  └─ eval runner      ← 原创:PR 集 → 跑同一流程 → 误报率/漏报率/延迟
```

**红线:控制面只做到够支撑两个入口 + 一次评测,不做通用框架。** 力气花在求解面的输出质量(意图对照准不准、护栏降不降误报)。

## 4. 核心数据模型:typed finding(原创)

用真实 Pydantic 模型承接结论(而非 prompt 里的伪 schema):

```
Finding:
  kind: summary | intent_mismatch | risk | suggestion
  title: str
  file: str | None
  line_start / line_end: int | None     # 证据位置
  evidence: str                         # 绑定的 diff hunk / 代码片段
  confidence: high | check_manually
  rationale: str
  needs_human: bool                     # 越界(业务正确性)时为 True
```

护栏规则:`evidence` 为空的 finding 直接丢弃;每类 finding 上限 3 条;`needs_human=True` 的渲染为"需人工确认"而非结论。

## 5. 数据流(工具入口)

```
PR URL
 → 取 diff + PR 描述 + 关联 issue(意图信号)+ 准备仓库工作区
 → 规范化 diff(带行号 hunk;大 PR 分块)
 → 分析器(只读 AskCoder):① 变更总结 ② 意图对照 ③ 风险 ④ 建议 → 产出 Finding[]
 → 诚实护栏:丢无证据项、置信分级、配额、标 needs_human
 → 渲染:一页 reviewer briefing(终端 + Markdown;GUI 渲染同一数据)
 → 进入多轮:用户可追问/反驳,分析器带上下文重答
```

评估入口:`reviewpilot eval <PR集.yaml>` → 每条 PR 跑上述流程 → 与人工标注比对 → 误报/漏报/延迟表。

## 6. 能力边界(诚实写进 README)

- **不执行代码**:沙箱/构建/安全成本过高,明确划界。
- **不判业务正确性**:判据在代码之外(PRD/需求);越界标 `needs_human`。
- 大 PR 超阈值 → 分块 + 提示"部分分析"。

## 7. 评测方法

- 自建 10–20 条小样本评测集,**含若干"干净无问题"的 PR(negative)** 专测误报。
- 指标:误报率、漏报率、平均延迟。表述为 **小样本 sanity eval**,不宣称"证明"。
- 至少一组对照:**开/关诚实护栏** → 用数据展示护栏对误报的影响。

## 8. 技术栈(已验证)

- **Python 3.12**(硬约束);CLI 引擎 + 薄 GUI(轻量 web:FastAPI/Flask 包 CLI)。
- 依赖:`aider-chat 0.86.2`(引擎,Apache-2.0)、`litellm 1.81.10`(provider)、`pydantic`(finding)、GitHub 取数(`gh`/PyGithub)。
- 模型:默认 `deepseek/deepseek-v4-flash`(已验证可调);经 litellm 可切 Anthropic/OpenAI。

## 9. 题面五考点对照

| 考点 | 落点 |
|---|---|
| 分析准确性 | 意图对照 + 证据绑定 |
| 上下文理解 | session=repo + RepoMap 按需检索 + 意图信号 |
| 误报漏报控制 | 诚实护栏(证据门/配额)+ 评估面对照 |
| 响应速度 | 模型分层 + 大 PR 分块 + 延迟指标 |
| 使用体验 | 一页 briefing + 多轮追问 + 置信分级 + GUI |

## 10. 三天倒排

- **5/29(已完成)**:调研、定位、MVP 范围、Day1 PR。
- **5/30(进行中)**:技术验证 PR(已合并)+ 本 spec。下午起搭主链路骨架(PR 获取 → 只读分析 → Finding → briefing)。
- **5/31**:意图对照 + 护栏打磨、薄 GUI、小评测集、README、demo 视频、收尾。

## 11. 合规(对应提交规则)

- 第三方框架在 README 列明:`aider-chat`(Apache-2.0,依赖引入,不拷源码)、借鉴 `PR-Agent`(Apache-2.0,设计借鉴)。
- 原创边界:意图对照、诚实护栏、typed finding、briefing、GUI、eval。
- 若复用 PR-Agent 具体代码,对应 PR 描述注明来源与许可证。
- 全程持续 commit/PR,时间戳落在 5/29–5/31 窗口内。

## 12. 未来扩展(题面要求)

- 跨 PR / 跨仓库的持久化评审记忆与依赖图。
- 自动行级评论回写 GitHub、CI 集成。
- 团队规范/历史决策的长期记忆。
- 检索增强(超大仓库的向量/符号检索),替代当前"全仓 + 按需读"。
