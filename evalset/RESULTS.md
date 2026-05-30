# 小样本 sanity eval 结果

> 这是一次 **sanity 检查**,不是基准证明。样本仅 8 条(4 issue / 4 clean),
> 目的是验证流水线可量化、并诚实暴露当前表现与问题。

- 模型:`deepseek/deepseek-v4-flash`(经 litellm);样本:`evalset/samples.json`(内联 diff,可复现)。
- 命令:`reviewpilot eval evalset/samples.json [--no-guard]`
- 判定:issue 样本被指认问题(risk/intent_mismatch finding)= TP,否则 FN;clean 样本被指认问题 = FP,否则 TN。

## 结果(2026-05-30)

| 配置 | TP | TN | FP | FN | 误报率(FP/clean) | 漏报率(FN/issue) |
|---|---|---|---|---|---|---|
| 护栏 ON | 3 | 3 | 1 | 1 | **25%** | **25%** |
| 护栏 OFF(对照) | 4 | 3 | 1 | 0 | 25% | 0% |

逐样本(护栏 ON):
- ✅ TP `intent-smuggle-payment` —— **意图对照成功**:抓到"声称只修登录却改了 payment"。
- ❌ FN `wrong-operator` —— 见下分析。
- ✅ TP `missing-none-check`、`off-by-one-loop`
- ✅ TN `clean-correct-fix`、`clean-docs-typo`、`clean-rename-var`
- ❌ FP `clean-add-test` —— 把"新增测试"误判为问题。

## 改进后(强制证据 prompt,2026-05-31)

针对下方第 1 条改进项,在 analyzer prompt 中**强制每条 finding 必带 file+line+原样引用证据**,并加入"新增测试/重命名/拼写/格式化属低风险默认不指认"。重跑(护栏 ON):

| 配置 | 误报率 | 漏报率 |
|---|---|---|
| 改进前 护栏 ON | 25% | 25% |
| **改进后 护栏 ON** | 25% | **0%** ↓ |

- ✅ `wrong-operator` 由 FN 转 TP:模型这次带了行号证据,通过证据门没被误杀(漏报率 25%→0%)。
- ⚠️ `clean-add-test` 仍是 FP:低风险提示未完全压住"把新增测试当问题",误报率仍 25%。这是下一步要继续治的点(更明确的 negative few-shot,或对 test/docs 文件降权)。

## 诚实分析与改进项

1. **证据门误杀真问题(护栏 ON 漏报↑)。** `wrong-operator` 模型其实发现了,但该 finding 没带行号证据,被护栏的"无证据则丢弃"规则删掉 → 变成漏报(护栏 OFF 时它是 TP)。
   → **改进**:在 analyzer prompt 中**强制每条 finding 必须给 `file`+`line`+`evidence`**,让真问题保住证据从而通过护栏;或让证据门按 kind 分级(对高价值 kind 放宽)。
2. **误报来自"把 clean 改动当问题"。** `clean-add-test`(新增测试)被指认为问题。
   → **改进**:prompt 显式告知"新增测试/重命名/文档拼写属低风险,默认不指认"。
3. **延迟由 LLM 主导且波动大(6.5s–79s)。** 护栏是纯函数无开销;两次运行延迟差是 LLM 调用本身(flash 为推理模型,偏慢)+ API 负载波动,不可横向比较。
   → **改进**:文件级事实抽取用更快的非推理模型,仅最终判断用强模型(模型分层)。

## 结论

意图对照在关键样本上成立(抓到夹带改动);护栏的证据门在当前 prompt 下**过严**,需先让模型可靠产出证据再收紧。样本量小,以上为方向性信号,非定论。
