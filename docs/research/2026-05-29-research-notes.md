# ReviewPilot 调研笔记(Day 1 · 2026-05-29)

> 目的:在动手前用实证 + 跨模型交叉复核,确定产品定位、MVP 范围与技术取舍。
> 方法:第一轮由 Claude 做联网实证调研;第二轮用独立模型(OpenAI gpt-5.5 via codex)做交叉复核,刻意要求"不要附和"。

---

## 1. 开发者在 Code Review 中的真实需求(实证)

- **"收集/切换项目上下文"是 2024 State of Developer Productivity 报告中并列第一的效率漏洞(占 26%)。** 这直接对应题面要求的"上下文理解"。
- Review 拖延 → 开发者转去开新任务 → 回头处理评审反馈时产生**昂贵的上下文切换**。精英团队 PR pickup time < 75 分钟,多数团队远高于此。
- 经验研究(arXiv:2505.16339 等)指出传统 review 的核心痛点:**频繁上下文切换、上下文信息不足**。

**机会点:** ReviewPilot 的核心价值不是"比谁挑出的 bug 多",而是**帮 reviewer 在 ~60 秒内重建 PR 上下文**——但必须是"审查导航"(该先看哪里、为什么危险、缺什么测试、是否动了接口),而非通用 PR 摘要,否则会被 GitHub/Copilot/CodeRabbit 已有的 summary 淹没。

## 2. 竞品格局

| 工具 | 打法 | 2025 bug 捕获率\* | 软肋(用户感知,非硬结论) |
|---|---|---|---|
| Greptile | 全仓库依赖图 + 并行 agent | ~82% | 重、贵、偏 GitHub |
| CodeRabbit | 工作流最全、装机量最大(200万+仓库,1300万+ PR) | ~44% | 噪声/误报被吐槽 |
| Graphite | 绑定 stacked PR 工作流 | ~6% | 不用 stacked PR 价值骤降 |

\* 数据来自 Greptile 自家 benchmark,**有立场,引用需注明来源并谨慎**。

**差异化缝隙(收窄后):** 面向**小团队 / 开源维护者 / 高频小 PR**场景,提供**低打扰的 reviewer briefing**,而不是"完整 AI reviewer"。"轻量 + 低误报 + 摘要优先"是方向,但不能当作竞品的硬短板——竞品也在迭代降噪与上下文理解。

## 3. 误报/漏报如何量化

- **CodeReviewer**(微软,CodeT5 配套)是主流数据集,但只到 **diff hunk 粒度**,缺 PR 级上下文,且已知含 25–32% 低质样本。
- 更新的 **SWE-PRBench / Code Review Agent Benchmark(2026)** 走 PR 级、带仓库上下文,更贴题面但更重。
- **3 天窗口的现实做法:自建一个 10–20 条的小评测集**(挑公开 repo 中"已知引入 bug 又被 review 抓到"的真实 PR)。
  - 定位为 **小样本 sanity eval**,不宣称"证明"低误报/低漏报。
  - **必须包含若干"干净无问题"的 PR(negative 样本)**,专门测系统会不会乱提建议(测误报)。

---

## 4. 收敛结论:MVP 范围(两个独立模型一致)

**一个闭环:输入 GitHub PR 链接 / diff → 输出一页 reviewer briefing。**

1. **PR 变更总结** — 3–5 条 bullet,按文件/模块分组,不长篇复述。
2. **风险识别** — 只输出 3 类:逻辑/边界风险、测试缺口、接口/兼容性风险。
   - 每条风险**必须绑定具体文件或 diff hunk**。
   - 没有证据就输出"未发现高置信风险",**绝不硬凑**。
3. **Review 建议生成** — 最多 3 条;分 `High confidence` / `Check manually` 两档;demo 阶段只生成"reviewer 草稿",**不自动评论到 PR**。

**3 天内明确不做:** 自动行级评论 bot、多仓库长期记忆、IDE 插件、复杂权限系统、"比竞品多抓 bug"的 benchmark。

## 5. 技术取舍

| 问题 | 决定 |
|---|---|
| 全量 diff vs 检索 | MVP 用**全量 diff**,限制 PR 大小;检索系统增加复杂度,小 PR 场景非必需。 |
| 大 PR | 按文件分块:先文件级摘要 → 合并成 PR briefing;超阈值提示"部分分析"。 |
| 一次调用 vs 分段 | 小 PR 一次调用;中等 PR 两阶段(先抽事实 → 再总结风险)。不一开始做复杂 agent flow。 |
| 模型选择 | 强推理模型做最终 briefing,便宜档做文件级摘要。重点不是模型炫技,而是**输出约束:少量、高置信、有证据**。 |

## 6. 最容易翻车的点(规避项)

1. **"低误报"承诺过强** — demo 里冒出一条看似合理实则无关的建议,用户立刻归类为"又一个噪声 bot"。宁可少说,不要硬评论。
2. **摘要太泛无法指导行动** — "改了用户模块并加了测试"等于没说;必须回答"最该先看哪里、为什么、缺什么测试、是否影响接口/数据"。

---

## 7. 待办:人工调研分工(由作者完成,补充本笔记)

- [ ] 亲手跑 CodeRabbit + Greptile/Qodo Merge 各一遍,记录哪条评论有用/哪条是误报(截图存档,进 README 与 demo)。
- [ ] 访谈 2–3 名开发者:review 花多久、最烦哪步、最怕漏哪类问题(留原话)。
- [ ] 在熟悉的公开 repo 中挑 3–5 个"引入 bug 被 review 抓到"的真实 PR,作为评测集种子。
- [ ] 翻几个目标团队的 `PULL_REQUEST_TEMPLATE.md` 与 review 规范。

## 来源

- State of Developer Productivity 2024 / 开发者生产力痛点综述(context gathering 26%)
- arXiv:2505.16339 *Rethinking Code Review Workflows with LLM Assistance*
- Greptile AI Code Review Benchmarks 2025(竞品捕获率,有立场)
- devtoolsacademy *State of AI Code Review Tools in 2025*
- CodeReviewer(微软)数据集;arXiv SWE-PRBench / Code Review Agent Benchmark(2026)
- 第二轮交叉复核:OpenAI gpt-5.5(via codex exec),独立判断
