# 巨量 PR / commit 的评审策略

> 背景:贴一个无 open PR 的 repo → 退化成"分析最新 commit",该 commit 有 259 个文件、
> 还混进 `node_modules/.bin/pbjs` 等 vendored 文件;旧实现"字母序取前 40"既脏又任意。
> 基于 codex + 本会话的设计评审收敛出以下策略。

## 根因
不是"40 太小",而是:① 候选集脏(含 vendored/生成物)② 截断是字母序、不是"最该看的" ③ repo 最新 commit 本就常不是可评审对象。

## 已落地(本轮)
1. **路径级过滤**:除生成类后缀/lockfile/超大文件外,整段排除 vendored/生成目录
   (`node_modules dist build vendor .next out target __pycache__ .venv site-packages …`)。见 `analyzer._should_skip`。
2. **相关性排序取 Top N**:按"源码扩展名 + 改动行数"打分,取最该审的 `max_files`(默认 40),
   而非 split/字母序。见 `analyzer._review_score` / `analyze_chunked`。
3. **诚实提示**:文件过多时明确告知"过滤后仍 N 个,只深审最相关的 M 个,其余未覆盖,
   建议给具体 PR 或缩小范围"。
4. **按预算打包**:多文件打包成几批、每批一次 LLM 调用(此前已做),避免 N 文件 N 次串行。

## 未来扩展(codex 评审,尚未做)
- **④ 无 open PR 的大 commit 默认降级 triage**:识别"初始导入/大合并"(文件数过大 / 多数为 vendored)
  → 默认只做结构性 triage,并要求用户给具体 PR / commit range / 选目录,不声称完整评审。
- **⑤ 两阶段 + map-reduce**:先 PR 级 LLM triage 挑与意图最相关的文件 → 深审 → reduce 汇总去重。
  LLM triage 放最后:确定性过滤+排序已解决大部分污染,LLM 是锦上添花。
- `.gitattributes` 的 `linguist-generated` / `linguist-vendored` 标记作为更权威的生成/vendored 信号。
