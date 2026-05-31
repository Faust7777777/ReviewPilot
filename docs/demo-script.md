# ReviewPilot Demo 视频分镜（5 分钟）

## 第 1 幕：指挥官启动（~35 秒）

**画面**：终端全屏，`~/` 提示符。

```
$ reviewpilot chat
```

TUI 弹出，欢迎语下方出现自检提示：
```
⚠️ 未检测到 API key; gh 未登录
  /key 设 API key | /auth 查 gh 登录 | /model 切模型 | /help 全部命令
```

输入 `/setup`，显示三步引导：
```
⚙️  快速配置:
1️⃣  API key — /key deepseek sk-xxx
2️⃣  GitHub 登录 — gh auth login
3️⃣  模型 — analyze:pro  chat:pro  /model flash 或 /model pro 切换
```

扫一眼 `/model` 输出，然后 `/model flash` 切到快速模型。

**旁白**：
> ReviewPilot 一行命令启动。key、gh、模型全在 TUI 里配，不用出去改环境变量。`/setup` 引导式三步走，冷启动不到 30 秒。等下演示时会切到 v4-flash 加速，生产用 v4-pro。

---

## 第 2 幕：硬核 PR——多跳取证（~80 秒）

**画面**：TUI 中输入 `Faust7777777 rp-hard`。ReAct 发现循环：list_repos → 找到 rp-hard → 确认 "是这个吗？输入 y"。输 `y`，列出 PR #1。选择 `1`。

ReAct 评审开始，屏幕上方出现工具调用 trace：
```
浅 clone Faust7777777/rp-hard…
读取 constants.py
搜索 ALLOWED_ROLES
读取 config.py
读取 auth.py
读取 api.py
读取 web.py
```

最终 briefing 出现，重点高亮：

```
[需人工确认] web.py 默认角色仍为 viewer，所有无显式 role 的请求将失败
  位置: web.py:7
  证据: web.py:7 form.get("role", "viewer") 默认 fallback 为 "viewer"
  调用链: web→api→auth→config→constants

[需人工确认] 环境变量 RP_ROLES 可绕过常量收紧，引入安全缺口
  位置: config.py:7

未找到测试文件，viewer 被拒的回归覆盖缺失
```

滚动到"我检查了什么"一栏，高亮取证路径。

**旁白**：
> 这个 PR 只改了 constants.py 一行——把角色白名单从三个减到两个。单看 diff，人类评审员很可能批了。  
> 但 ReviewPilot 的 ReAct loop 在 6 次工具调用中自主追踪了 4 层调用链：读 constants → 搜 ALLOWED_ROLES → 读 config → 读 auth → 读 api → 读 web。最终发现 web.py 里硬编码了 default="viewer"——它不在 diff 里，不看调用方根本不知道会炸。  
> 还发现环境变量 RP_ROLES 可以绕过这个"安全收紧"，形成安全缺口。外加零测试覆盖。六条 finding，全有证据锚点。

---

## 第 3 幕：网页 LLM 对比（~60 秒）

**画面**：切到浏览器，打开 Claude/GPT 网页版。粘贴同一个 PR 的 diff（只显示 constants.py 一行改动）。

网页 LLM 回复（提前录好）：
> "这个 PR 把 viewer 从角色白名单中移除了。改动看起来合理，是一次安全性提升。建议合并。"

镜头切回 ReviewPilot 的 6 条 finding，画面对比并排：
- 左边网页 LLM：「改动合理，建议合并」
- 右边 ReviewPilot：6 条 finding，覆盖代码缺陷 + 安全漏洞 + 测试缺口

**旁白**：
> 网页 LLM 只看到你贴的一段 diff，说"改动合理，建议合并"。它没有工具去读其他文件、没有 agent loop 去迭代探索、没有护栏去过滤它没见过的东西。  
> ReviewPilot 翻了 5 个文件，出了 6 条 finding。这个差距不是模型智商——是工具链和系统设计。这是 harness 和 general-purpose chatbot 的本质区别。

---

## 第 4 幕：GUI 对话式评审（~45 秒）

**画面**：浏览器打开 `http://localhost:8000`，显示 ReviewPilot 的 FastAPI GUI。

操作流程：
1. 输入框粘贴同一个 PR 链接，点"评审"
2. 左边栏出现 briefing（Markdown 渲染）
3. 下方对话框输入："web.py 的默认值写成空字符串行不行？"
4. AI 回复，建议改为 `form.get("role")` 迫使客户端必传
5. 再问："config.py 的环境变量覆盖问题怎么修？"
6. AI 给出方案：常量优先，环境变量仅用于新增角色

**旁白**：
> TUI 之外还有 Web GUI。评审结果和对话追问在同一个界面里。追问会保留完整会话上下文，不丢失之前的 briefing。你可以在团队里部署内部服务，让所有 PR 先过一遍审查再说。

**镜头重点**：左边 briefing + 右边对话的左右分屏布局。

---

## 第 5 幕：eval 数据自证（~50 秒）

**画面**：切回终端。

```bash
$ reviewpilot eval evalset/samples.json
```

输出双栏对照：
```
样本 12  (同一批 LLM 输出,护栏开 vs 关)
        护栏开         护栏关
TP/TN/FP/FN   5/4/2/1      6/5/1/0
误报率        33%          17%
漏报率        17%           0%
```

切到 `evalset/samples.json` 展示跨文件样本：
```json
{
  "name": "signature-change-breaks-caller-cross-file",
  "label": "issue",
  "expect_substring": "tasks.py",
  "repo_files": {"tasks.py": "send(\"done\")"}
}
```

再展示 `reviewpilot runs` 查看 trace：
```
最近 3 条 run trace:
  r_xxx  rp-hard#1  mode=loop  findings=6  latency=43s
```

**旁白**：
> 我们不说"效果很好"——我们用 eval 数据说话。12 个标注样本，含 issue 和 clean 样本。护栏开/关的对比不是跑两次 LLM——同一批输出分别过和不过护栏，确定性可复现。跨文件样本走 ReAct loop，它必须读到 diff 以外的文件才能判对。loop vs chunked 的实测对照需要 LLM key 跑出，欢迎评审老师自行验证。每次评审的 run trace 落 JSONL，可审计、可回放。

---

## 第 6 幕：收尾（~30 秒）

**画面**：回到 README，展示模块地图和进化路线图。

**旁白**：
> ReviewPilot 的定位是领域专用评审 harness。我们不追求"挑出最多的 bug"——我们追求"说出来的每一条都站得住脚"。证据绑定、诚实护栏、可观测 trace、eval 回归门，这四个基石让"AI 帮你 review 代码"这件事从玄学变成工程。  
> 感谢观看。仓库、文档、安装指引都在 README 里。欢迎试用、反馈、提 PR。

---

## 录制前检查清单

- [ ] `DEEPSEEK_API_KEY` 已设（仅走环境变量，别贴进文件）
- [ ] `gh auth login` 已完成
- [ ] `reviewpilot chat` 能在终端正常启动
- [ ] 网页 LLM 对比画面已预先录制（打开 Claude/GPT 网页并粘贴 rp-hard diff）
- [ ] 确认 PR `Faust7777777/rp-hard#1` 仍 open、仓库未删除
- [ ] GUI（`reviewpilot web`）启动正常，`http://localhost:8000` 可访问
- [ ] evalset/samples.json 存在且格式正确
- [ ] 录屏软件（OBS / QuickTime）已配置、麦克风已测试
- [ ] 建议设置终端字体放大（32pt+）方便评委观看

## 分镜时长汇总

| 幕 | 内容 | 时长 |
|---|---|---|
| 1 | 指挥官启动（/setup /key /model） | 35s |
| 2 | 硬核 PR——4 层多跳取证 | 80s |
| 3 | 网页 LLM 对比（同一 PR 不同结果） | 60s |
| 4 | GUI 对话式评审 | 45s |
| 5 | eval 数据自证 + runs trace | 50s |
| 6 | 收尾 | 30s |
| **总计** | | **300s（5 分钟）** |
