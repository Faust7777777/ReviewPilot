# ReviewPilot Demo 视频脚本

> 目标时长:3–5 分钟。适合竞赛评委演示或录制 walkthrough 视频。
> 格式:**[时长] [画面操作] [旁白要点]**

---

## 第 1 段:开场(~20 秒)

**画面操作:**  
全屏展示 ReviewPilot README 标题行,然后切到终端空白界面。

**旁白要点:**  
> "ReviewPilot 是一个领域专用的 PR 评审 harness。它不是通用 coding agent,也不自动改代码。它只做一件事:帮 reviewer 快速重建 PR 上下文、核对代码有没有做它声称要做的事——并对拿不准的地方诚实说出来。接下来用真实例子展示三分钟。"

**镜头重点:** README 中"领域专用 PR 评审 harness"那一句加粗字样。

---

## 第 2 段:评审一个真实 GitHub PR(~70 秒)

**画面操作:**

1. 终端输入:
   ```bash
   reviewpilot review https://github.com/owner/repo/pull/123
   ```
2. 命令运行后,屏幕开始滚动输出——先出现进度信息(如"浅 clone owner/repo 供取证…""读取 src/auth.py""搜索 'login_handler'")。
3. 最终输出完整 briefing:
   - "变更总结"一栏
   - "意图对照"栏:若有夹带改动则高亮显示
   - "我检查了什么"栏:展示"取证过程:读取 src/auth.py、搜索 'login_handler'"
   - **最重要**:末尾出现"证据过滤:已丢弃 N 条低可信结论(无证据 X 条、文件不在 diff 也不在读过的文件 Y 条)——诚实声明,非静默忽略"

**旁白要点:**  
> "你看到它先去浅 clone 了仓库,然后按需读取相关文件——这是 ReAct 评审循环,不是把全量 diff 一把塞给模型。"  
> "取证完成之后,注意这里——'已丢弃 N 条低可信结论'。这是诚实护栏:没有 diff 证据的 finding、指向模型没读过的文件的 finding,全部主动声明被丢掉了,不是静默忽略。这是 AI review 里最容易被忽视的诚实设计。"  
> "意图对照结果:PR 说只修了登录流程,但 diff 里还有一处支付模块的改动没提——这就是夹带改动,也是最难发现的一类问题。"

**镜头重点:** 滚动到"取证过程"和"证据过滤"两行,暂停两秒,让评委看清楚。

---

## 第 3 段:本地模式(~30 秒)

**画面操作:**

1. 切到另一个终端,当前目录是一个本地仓库(可以是 ReviewPilot 自身)。
2. 输入:
   ```bash
   reviewpilot review --local --range main...HEAD --title "修 auth 模块的边界问题"
   ```
3. 输出 briefing(流程与第 2 段相同,但无浅 clone 步骤)。

**旁白要点:**  
> "不是所有代码都在 GitHub 上。私有内网、还没 push 的分支、提交前自检——都能用本地模式。`--local --range main...HEAD` 直接读本地 git diff,不依赖 GitHub,不需要网络。`--title` 可以手动提供'作者声称'的意图。"

**镜头重点:** 命令行参数 `--local --range main...HEAD`。

---

## 第 4 段:TUI 多轮追问(~50 秒)

**画面操作:**

1. 输入:
   ```bash
   reviewpilot chat https://github.com/owner/repo/pull/123
   ```
2. 全屏 TUI 弹出(展示 tui-screenshot.svg 效果或实录),左侧实时显示分析进度(read/search trace),右侧逐步出现 briefing。
3. briefing 稳定后,在追问框输入:
   - 第一条:"第 2 条风险项是什么意思?"
   - AI 给出解释
   - 第二条:"这是故意的,作者在 PR 描述里提过。"
   - AI 更新置信度声明:"如描述已涵盖此改动,则该项不构成夹带——请以作者确认为准,已标注需人工确认。"

**旁白要点:**  
> "看完 briefing 不够——reviewer 往往要追问。这里直接在 TUI 里追问:先问'第 2 条是什么意思',再反驳'这是故意的'。模型会降级置信度,不会固执己见。"  
> "会话历史完整保留,可以一直追问下去。"

**镜头重点:** 追问框输入"这是故意的"后 AI 的回复,重点展示"已标注需人工确认"字样。

---

## 第 5 段:仓库模糊发现(~40 秒)

**画面操作:**

1. 在 TUI 追问框(或新的 `reviewpilot chat`)输入:
   ```
   wuwai 的那个 CTF 题目仓库的最新 PR
   ```
2. 界面显示 ReAct 发现过程:"正在探索 GitHub…列出 wuwai 的仓库…找到 dlut-ctf…获取最新 PR…"
3. 确认提示框弹出:"找到仓库 wuwai/dlut-ctf,最新 PR #12 '修 web 题附件路径'——开始评审?"
4. 用户按 Enter 确认,自动进入评审流程。

**旁白要点:**  
> "不记得 PR 链接怎么办?直接告诉它用户名加大概意图——另一个 ReAct loop 会用 list_repos 和 search_repos 两个工具探索 GitHub,找到正确仓库,然后让你确认,再自动开评审。不需要记链接,不需要打开浏览器。"

**镜头重点:** 从"正在探索"到确认提示框出现的完整过程,体现 agent 自主发现能力。

---

## 第 6 段:eval 对照(~30 秒)

**画面操作:**

1. 切到终端,输入:
   ```bash
   reviewpilot eval evalset/samples.json
   reviewpilot eval evalset/samples.json --no-guard
   ```
2. 两次输出结果并排展示(或先后展示):
   - 护栏开:FP=… / FN=… / 误报率=…(以实际输出为准,别背数字)
   - 护栏关:FP=… / FN=… / 误报率=…(对照护栏开:量化护栏把误报降了多少、代价漏几条)

**旁白要点:**  
> "我们有一个小样本 eval 集,含 issue 样本和 clean 样本(专门测误报)。`--no-guard` 关掉诚实护栏作对照——你可以量化护栏到底把误报降了多少、代价是漏了几条。"  
> "evalset 里还有跨文件样本——diff 本身看不出问题,必须读仓库其他文件才能发现,这些样本会走生产主路径的 ReAct Review Loop。loop vs 传统 chunked 的对照数字需要配置 LLM key 跑出,结论方向性,不是基准声明。"

**镜头重点:** 两次 eval 输出的 FP/FN 对比数字。

**注意(演示前确认):** 需要配置 `DEEPSEEK_API_KEY`(或其它 provider key)才能真跑 eval。loop vs chunked 对照需要 key,若无 key 只演示命令和输出格式即可。

---

## 第 7 段:收尾(~20 秒)

**画面操作:**  
回到 README,展示"进化路线图"部分。

**旁白要点:**  
> "ReviewPilot 的定位是领域专用 harness:流程固定成可观测、可对照的阶段,组件可替换,用 eval 数据说明设计取舍。它不追求'挑出最多 bug',而是追求'说出来的每一条都能站得住脚'。"  
> "下一步是 run trace 持久化——把每次评审的模型选择、token 消耗、护栏丢弃全部落盘,形成跨 PR 的审计记录;以及跨 PR 记忆——把团队历史误报和已驳回结论作为可检索证据注入后续评审。"

**镜头重点:** 路线图表格的"run trace 持久化"和"跨 PR 记忆"两行。

---

## 演示前检查清单

- [ ] 配置 `DEEPSEEK_API_KEY`(或其它 provider)
- [ ] `gh auth login` 已完成
- [ ] Python 3.12 venv 已激活,`pip install -e ".[dev]"` 已完成
- [ ] 准备好一个真实 PR 链接(最好是有意图对照价值的 PR——改了比 PR 描述多的东西)
- [ ] 确认 TUI(`reviewpilot chat`)在演示终端可以正常启动
- [ ] evalset/samples.json 确认存在且格式正确
- [ ] loop vs chunked 实测:若无 key 则跳过数字对比,只演示命令
