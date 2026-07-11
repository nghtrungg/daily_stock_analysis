# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> For user-friendly release highlights, see the [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases) page.

## [Unreleased]

- [improvement] Add Vietnam-first analysis defaults, VN market data routing, Vietnamese report localization, and GitHub Actions configuration guidance.
- [docs] 新增 AnalysisContextPack P0 上下文盘点。
- [feature] 新增 AnalysisContextPack P1 内部契约与脱敏序列化测试。
- [feature] 新增 AnalysisContextPack P2 builder。
- [feature] 普通分析与 Agent 运行时 Prompt 接入 AnalysisContextPack 低敏摘要。
- [feature] AnalysisContextPack P4 低敏 overview 接入历史详情。
- [feature] AnalysisContextPack P5 增加数据质量评分。
- [docs] 明确 AnalysisContextPack P6 文档、迁移与回滚边界。
- [docs] #1386 P7 盘前/盘中/盘后分析的入口、迁移、回滚和用户可见说明。
- [feature] #1386 P5 为个股分析报告新增 `dashboard.phase_decision`。
- [improvement] 优化 Web 报告详情页信息层级。
- [feature] P6 自选股、持仓与账户联动规则。
- [docs] 补齐告警中心 P8 文档与配置收口说明，明确 GitHub Actions 与 Desktop 边界。
- [fix] GitHub Actions 每日分析工作流读取 SearXNG 自建实例地址时支持 Variables 优先、Secrets 回退，修复仅配置 Variables 时 URL 不生效的问题。
- [改进] GitHub Actions 每日分析工作流补齐 TickFlow 数据源环境变量映射，并收敛 README 数据源稳定性说明到完整指南。
- [修复] WebUI 启动时显式 `--host` / `--port` 不再被 `.env` 中的 `WEBUI_HOST` / `WEBUI_PORT` 覆盖，未传 CLI 参数时统一使用解析后的运行时配置。
- [改进] GitHub Actions: 每日分析工作流（`00-daily-analysis.yml`）新增钉钉通知环境变量映射，支持在云端定时任务中直接使用钉钉机器人。
- [修复] Web 持仓页首屏快照改用 `include_realtime=false` 快速估值，跳过逐票实时行情预取后先展示持仓列表，避免外部实时行情源变慢时长时间空白等待。
- [修复] 修复任务状态接口重建报告动作字段时把合法情绪分 `0` 当成空值的问题，确保低分报告能按评分口径纠正为卖出建议。
- [修复] 修复 Agent 流式回复在未收到完成事件就断开时被显示为“（无内容）”的问题，改为提示流式响应中断并保留用户消息，避免误判为空回答。
- [修复] 修复桌面端 `WEBUI_HOST=*` / `WEBUI_HOST=[::]` 会被原样传给端口探测和后端启动导致无法监听的问题，启动前分别规范化为 `0.0.0.0` / `::`。
- [改进] `STOCK_LIST` 自选股解析支持中文逗号、顿号、分号、空格和换行等常见粘贴分隔符，运行时、定时热刷新、CLI `--stocks`、Web 设置保存和自选 API 统一识别，并在写回时规范为英文逗号。
- [改进] 新增 `NEWS_INTEL_AUTO_FETCH_ENABLED` 单开关，开启后个股分析、Agent 分析和大盘复盘会 fail-open 自动初始化并刷新 RSS/Atom/NewsNow 本地资讯池。
- [改进] Web AI 建议页新增主股票上下文，复用最近分析和股票索引候选，并改进表现统计零样本说明。
- [改进] 补充本次设置页布局收敛：移动端分类导航改为横向滚动列表并保证设置内容首屏可见，桌面端保留分类说明并收紧字段布局层级与间距，提升首屏效率与可配置信息密度。
- [文档] 在 README 快速开始中补充行情数据源配置说明（TUSHARE_TOKEN / Longbridge），明确未配置时仍可走 AkShare、Baostock、YFinance 等免费兜底源，日志中相关提示不影响运行。同步更新docs下的中英双份 README
- [改进] 新增 #1743 Phase 6a 内部 DSA Tool Surface 契约，统一工具 schema、stock scope fail-closed guard、结构化错误、审计摘要和脱敏诊断边界，并明确外部 AgentBackend 工具能力仍需 wire-level probe 证明。

<!-- 新条目格式：- [类型] 描述（类型取值：新功能/改进/修复/文档/测试/chore）-->
<!-- 每条独立一行追加到本段末尾，无需分类标题，合并时冲突最小 -->
- [新功能] 飞书推送新增文件上传能力：`FeishuSender.send_feishu_file(file_path)` 通过 App Bot SDK (`im.v1.file.create`) 上传文件并发送文件消息；Webhook 模式回退为发送文件内容文本；新增 `FEISHU_SEND_AS_FILE=true` 配置开关，开启后飞书以文件形式发送报告而非文字消息。
- [新功能] 多 Agent 编排 Pipeline 新增子 Agent 独立超时钳位：支持 6 个环境变量为 TechnicalAgent、IntelAgent、RiskAgent、DecisionAgent、PortfolioAgent、SkillAgent 各自配置独立硬上限，互不挤占配额；默认 0 表示关闭钳位。

## [3.25.0] - 2026-07-03

### 发布亮点

- feat: 新增 `claude_code_cli`、`opencode_cli` generation-only 本地 CLI backend，并补齐生成后端状态诊断、预览、冒烟测试 API 和 Web 状态面板。
- feat: 台股报告完整接入三大法人资料，覆盖报告渲染、LLM prompt、TWD 币别标示、收盘集合竞价识别和 fetcher 韧性加固。
- feat: 新增钉钉群机器人通知、韩语报告输出和 AI 建议决策风格重评估预览。
- feat: Agent `/chat/stream` 标准化 progress event，新增阶段开始/完成、pipeline timeout 和预算跳过语义。
- fix: 修复桌面端 WebUI host/port 绑定、macOS Homebrew CLI PATH 诊断、Discord 长报告分片、AlphaSift 超时、yfinance 分红解析、A 股回测代码归一化等稳定性问题。

### 新功能

- 钉钉群机器人通知支持 `DINGTALK_WEBHOOK_URL` 和 `DINGTALK_SECRET`，并对长文本自动切片以适配 20KB 限制。
- 报告输出语言新增韩语（`REPORT_LANGUAGE=ko`），覆盖个股报告、大盘复盘、Prompt 输出语言、决策护栏、通知模板标签与 Web 报告详情页文案。
- 新增 `claude_code_cli` 与 `opencode_cli` generation-only 本地 CLI backend，保留 LiteLLM 默认路径、Agent 工具调用边界、per-preset extractor、最小 env allowlist 与结构化错误。
- 新增生成后端状态、预览和冒烟测试 API，以及 Web 生成后端状态面板，区分轻量检查与 JSON 冒烟测试，并保持本地 CLI “仅生成、不支持问股工具调用”的边界。
- Agent `/chat/stream` progress event 新增 `stage_start`、`stage_done`、`pipeline_timeout`、`pipeline_budget_skipped`，补齐阶段进度、超时和预算跳过语义。
- 台股个股报告的 institution 区块展示 TWSE T86 / TPEx 三大法人原始买卖超净额，并将三大法人净买卖超表格注入 LLM 分析 prompt 作为台股筹码过滤器。
- 新增 AI 建议决策风格重评估预览接口与页面预览。

### 改进

- 台股三大法人 fetcher 增加并发缓存防击穿、TWSE/TPEx 分市场熔断、TPEx 日期保护和剩余 stage 预算复用，降低限流、端点故障和冷抓取超时带来的降级概率。
- AlphaSift 默认依赖 pin 更新到 `9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf`，接入 wrapper 数据源 caller-side timeout、东财直连限速/抖动、策略目录元数据和防守策略。
- 选股任务状态轮询遇到可恢复超时时提示后台任务仍会自动重试，`.env.example` 补充相关超时调优项。
- 收敛个股分析评分与 DecisionSignal action 口径，统一 80/60/40/20 分段，并在风控降级时记录 raw/adjusted score、final action 与原因。
- Web 设置页左侧分类切换时仅在相关分类展示首次启动检查和 AlphaSift 辅助卡片，减少跨分类残留。

### 修复

- 修复 Windows 桌面端启动后端时固定传入 `--host 127.0.0.1` 导致 `.env` 中 `WEBUI_HOST=0.0.0.0` 不生效、局域网无法访问 WebUI 的问题；桌面端仍默认使用 `127.0.0.1`，仅在显式配置 `WEBUI_HOST` 后按配置绑定。
- 修复桌面端启动时 `.env` 中 `WEBUI_PORT` 与 Electron 自动选择端口不一致，导致窗口继续等待旧端口并连接超时的问题。
- 修复 macOS 桌面端从 Finder/Dock 启动时后端 PATH 看不到 Homebrew Codex CLI 的问题，并明确 Codex CLI 主分析与 Agent LiteLLM 工具调用分流诊断。
- 修复 Discord 长报告推送按 2000 字符上限分片逐段发送，遇到 429 限流会按 `retry_after`/`Retry-After` 有限重试，避免中途失败后只收到前半段报告。
- 修复日股、韩股和台股 `market_phase` 收盘集合竞价识别，避免临近收盘阶段仍被标记为普通 `intraday`。
- 修复 A 股个股分析遇到空 `belong_boards` 占位时不会继续补查所属板块、关联板块模块展示不稳定的问题。
- 修复大盘复盘在 LLM 标题漂移或正文缺少板块段时，Web 与推送报告偶发缺少板块主线的问题。
- 修复 Web 大盘复盘结构化数据成交额、指数点位、涨跌幅和高/低值格式化，避免浮点长尾或缺失值 `0.00` 直接展示。
- 修复 Web 首页个股栏在 stock-bar 摘要字段缺失或动作建议无法归类时隐藏情绪分与建议标识的问题。
- 修复 Web 设置页定时任务“立即执行一次”后台线程未传 `stock_codes` 导致任务崩溃的问题。
- 修复 `opencode_cli` 静态指令，避免全局 JSON-only 约束影响 `generate_text()` 与大盘复盘自由文本输出。
- 修复 yfinance 1.2.x 将 `Ticker.dividends` 返回为单列 DataFrame 时分红解析被丢弃的问题，恢复 TTM 每股分红与分红次数计算。
- 修复台股财务金额币别标示，将 TWD 金额标注为“新台币”，避免在 A 股语境下误读为人民币。
- 修复回测日线补全将 `605066.SH`、`SS605066`、`SS.605066` 等 A 股等价代码误向数据源请求 `SS605066`，导致回测数据不足的问题。

### 文档

- 新增 Agent `/chat/stream` progress event 契约文档，说明新增事件字段语义、Web 兼容边界、验证方式和回滚方式。
- 同步本地 CLI backend 隐私/部署边界，明确 local CLI 不是离线模型，Docker/CI/远端需自行安装登录，DSA 不读取 Claude/OpenCode credential 文件。
- 更新 README 三语入口和市场支持边界，说明台股 `.TW` / `.TWO`、三大法人报告区块、TWD 标注与收盘竞价识别能力边界。

### 测试

- 台股三大法人 fetcher 新增 live-smoke 脚本与 `@pytest.mark.network` 漂移检测测试，用于非阻断 network-smoke 定时任务核对 TWSE T86 / TPEx 核心字段与解析结果。

## [3.24.1] - 2026-06-28

### 修复

- 修正 Longbridge SDK 版本约束为按平台选择可安装版本，避免桌面与 Docker 发布在 `pip install -r requirements.txt` 时因不存在的 `0.2.75` 版本失败。

## [3.24.0] - 2026-06-28

### 发布亮点

- feat: 扩展台股、日股、韩股市场支持，覆盖台股 suffix-only 分析、台股三大法人资料层、JP/KR 大盘复盘和跨服务市场枚举。
- feat: 新增 GenerationBackend 抽象、`codex_cli` 本地 CLI backend、reserved Hermes 本地 HTTP 渠道和 prompt cache capability registry。
- feat: Web/API/Desktop 支持多时间定时推送与 runtime scheduler 热重建，Web 设置页补齐首次启动检查与定时任务面板。
- feat: 报告链路补齐信号归因、单股信号时间线、概念板块排行和通知/报告关联板块展示。
- fix: 修复 Docker/启动探针、静态资源 MIME、回测空结果、组合估值、通知 Markdown、AlphaSift 数据源和测试环境隔离等稳定性问题。

### 新功能

- 新增台股 suffix-only 个股分析 MVP：`.TW`/`.TWO` 代码可走 YFinance 日线与近实时行情，并补齐市场识别、交易日历和 Prompt 能力边界。
- 台股 `tw` 纳入 DecisionSignal、Portfolio、Intelligence 服务层、API 枚举和 Web 筛选，避免台股分析信号被市场归一化静默丢弃。
- 新增台股三大法人资料层 fetcher `TwInstitutionalFetcher`，支持 TWSE/TPEx 来源、日期转换、单日缓存和 fail-open 退化。
- 大盘复盘新增 `jp`/`kr` 市场，支持日经225/TOPIX、KOSPI/KOSDAQ 指数复盘，并扩展 `MARKET_REVIEW_REGION`、交易日过滤和 Web 设置枚举。
- 新增 GenerationBackend Phase 1 抽象和显式 opt-in 的 `codex_cli` 本地 CLI generation backend，提供结构化错误、fallback、stream 降级和 usage unavailable contract。
- 新增 reserved Hermes 本地 HTTP generation 渠道，提供 JSON generation、no-proxy 本地调用和 saved secret endpoint 绑定。
- 新增 Provider Cache Capability Registry，按 provider、API surface、gateway 与 verification status 建模 prompt cache 能力。
- 支持 `SCHEDULE_TIMES` 多时间定时推送，长运行 Web/API/Desktop 进程保存调度配置后可热启停或重建 runtime scheduler。
- 新增信号归因分析和 Web AI 建议页单股信号时间线，并为自动生成与历史回填的 DecisionSignal 写入默认 `decision_profile` metadata。
- 大盘复盘、Web 报告页和通知关联板块补齐概念板块排行与概念信号展示。

### 改进

- TickFlow 扩展为可选 A 股日 K、实时行情、股票列表/名称数据源，并增加 count、完整性校验和批量预取缓存保护。
- 硬化 JP/KR/TW suffix 识别、日韩股票种子索引、YFinance 报价/基本面上下文，以及 JP/KR Portfolio 与 Market Light 边界。
- Web 设置页新增首次启动配置检查卡与定时任务面板，隐藏内部 `SCHEDULE_TIMES` 键，并改善重复任务提示的关闭与自动消失体验。
- Web 历史报告详情不再内嵌 AI 建议卡片，结构化决策信号集中到 AI 建议页，并保留来源报告 ID/URL 参数精确定位。
- `GENERATION_BACKEND=codex_cli` 下普通分析与大盘复盘不再因缺少 LiteLLM API Key 被误判不可用，并改用 `--output-last-message` 文件读取最终响应。
- 本地 CLI backend 对 stdout/stderr 诊断预览和最终响应实行执行期总量上限，并补齐新增 generation backend 数字配置最大值校验。
- AlphaSift 默认依赖 pin 更新到 `0a7b9cd59e81718f851890535241bc105d4ddc64`，并默认走 DSA EastMoney 兜底 provider、暴露 source health 诊断。
- Docker Compose 默认内存建议提升到 1G；每日分析 workflow 兼容误将 `STOCK_LIST` 配到同名 Environment variables 的场景。
- Agent 路径同步 signal attribution prompt，通知报告摘要不再展开 AI 决策信号明细，完整信号保留在个股详情与单股报告。

### 修复

- API 异步批量分析共享概念板块排行缓存，避免同批多股重复拉取全市场概念排行。
- 修复通知 Markdown 表格转换在空单元格后将后续内容错配到错误表头的问题。
- 修复 Market Light 区域归一化拒绝 `jp`/`kr`、日韩历史列表市场阶段摘要误传 `analysis_phase` 和默认通知报告缺少 `dashboard.phase_decision` 的问题。
- 固定 Docker 可安装的 Longbridge SDK 版本为 0.2.75，并修复 Docker 镜像中 efinance 缓存目录属主导致 A 股数据源降级的问题。
- 持仓快照今日估值改为受限并发预取实时价，减少持仓较多时 Web 组合页面刷新超时。
- Web 首页重新分析完成后自动切换到同一股票最新报告，并修复 Windows 环境下 Web/Desktop 静态 JS 资源可能以 `text/plain` 返回导致黑屏的问题。
- 修复 `--serve --schedule` 与 Web/API runtime scheduler 状态脱节、立即执行忙碌状态误提示、重建定时任务重复监听和启动参数语义丢失。
- 修复 `main.py --serve-only` 在低配主机上因惰性 import 应用超出 uvicorn 启动自检窗口而反复重启的问题。
- 修复 Web 回测未传分析日期范围、股票代码未归一化导致成功响应但结果为空的问题，并为空候选、行情不足和非法后缀提供诊断信息。
- 修复 unsupported `GENERATION_BACKEND` 被当成空响应/模板 fallback、`codex_cli` stdout 重复计入输出上限和主分析 JSON schema fallback 语义回退的问题。
- Docker 部署中 Web 设置页保存自定义 Webhook 模板时会转义 `$content_json` 等占位符，并在运行时还原，避免 Compose 重新部署展开为空。

### 文档

- 补齐概念板块排行字段契约、通知报告行业/概念类型列展示和数据源稳定性与故障处理图示。
- 补充 JP/KR/TW suffix-only MVP、`MARKET_REVIEW_REGION` 保存/校验/回退矩阵、Market Light 边界和 PR 提交流程约束。
- 补充本地 CLI backend 隐私边界、非离线模型说明、Docker/CI 登录态限制和 `codex_cli` experimental/limited 状态。
- 补充回测请求链路说明，并同步更新 `docs/full-guide.md` 与 `docs/full-guide_EN.md` 示例。

### 测试

- 新增/更新台股、JP/KR 大盘复盘、GenerationBackend、`codex_cli`、Hermes、本地 CLI、runtime scheduler、回测和概念板块排行相关回归测试。
- 加强 `tests/test_analysis_api_contract.py`、`tests/test_analysis_history.py` 与 `tests/test_backtest_service.py` 的临时 `.env` 隔离，避免本地真实 `.env` 污染系统配置测试。

## [3.23.0] - 2026-06-20

### 发布亮点

- feat: DecisionSignal 贯通报告提取、Web 展示、反馈/后验、告警通知和组合风险，AI 建议信号进入可追踪闭环。
- feat: 新增合规 RSS/Atom 与 NewsNow 资讯源情报池，分析、Agent 和大盘复盘可 fail-open 复用本地资讯 evidence。
- feat: 新增日本/韩国 suffix-only 个股分析 MVP，支持 `.T`、`.KS`、`.KQ` 标的通过 YFinance 获取行情与技术上下文。
- feat: 新增 Token 用量监控看板、legacy LLM usage telemetry 和 message stability audit，增强 LLM 调用可观测性。
- fix: 修复运行流 live 状态、AlphaSift 缓存/字段兼容、发布说明诊断和日韩股票输入/历史展示等稳定性问题。

### 新功能

- 个股分析历史成功保存后会从最终报告 best-effort 提取 `DecisionSignal` 决策信号，复用现有信号去重、计划质量计算和脱敏契约。
- 新增 Web AI 建议页、持仓页 latest active 信号摘要、历史报告信号展示和更完整的信号详情卡片，展示评分、置信度、价格计划、催化、风险与失效条件。
- 新增 DecisionSignal 用户反馈、信号级日线后验评估、统计 API 与 Web 展示，使用 outcome/feedback sidecar 表并保留主信号表契约。
- 将 DecisionSignal 复用到告警、通知和组合风险：告警触发关联 latest active 信号或创建最小 alert 信号，通知追加低敏信号摘要，持仓风险聚合 active sell/reduce/alert 信号并保持 fail-open。
- 新增合规 RSS/Atom 资讯源配置、拉取、去重、入库、查询、retention 与基础安全校验 API，作为个股/市场资讯情报池基线。
- 资讯源新增 `newsnow` 类型、`NEWSNOW_BASE_URL` 配置和 `/api/v1/intelligence/sources/defaults` 默认源初始化接口，内置财联社热门、雪球热门股票、华尔街见闻快讯、金十数据和格隆汇事件等财经热点源。
- 个股分析、Agent 分析和大盘复盘会 fail-open 读取本地资讯/情报池，并把来源链接作为新闻上下文和 evidence 输入。
- 新增日本/韩国 suffix-only 个股分析 MVP：手输 `.T` / `.KS` / `.KQ` 代码可走 YFinance 日线与近实时行情，补充市场识别、交易日历、Prompt 语义、Web/API 类型和能力边界文档。
- 新增 Token 用量监控看板与 `/api/v1/usage/dashboard` 接口，展示 LLM 调用总量、Prompt/Completion 拆分、模型用量、调用类型分布和最近调用明细。

### 改进

- 为 `DecisionSignal` 补齐默认生命周期、同源窄 relaxed 去重、相反 active 信号自动 invalidated、terminal 状态不可 PATCH 复活和低敏 market phase hints 提取。
- 补充 Web decision-signals typed API wrapper 与契约隔离测试，并将历史报告 AI 建议查询收口到精确报告懒提取。
- DSA 数据源链路新增 Tencent 日 K 直连 fetcher、daily source health 短期熔断，并升级 AlphaSift 默认 pin/runtime bridge。
- 默认启用 `DAILY_SOURCE=auto`、Sina snapshot 优先级、候选级 quote context 与 LLM ranking timeout/max tokens 边界。
- 新增 legacy LLM usage provider/cache telemetry、message HMAC 诊断字段和普通个股分析 legacy message stability audit，不改变公开 Usage API、prompt 或 provider 参数。
- 问股页移动端策略选择改为默认收起的按钮入口，展开后仍可多选策略并在发送后自动收起，减少对对话内容的遮挡。

### 修复

- 修复运行流 live SSE 脱敏、后期 LLM/通知卡片重复、数据源聚合卡片过早成功、Web 首页窄侧栏挤压股票信息，以及个股分析自动生成大盘上下文时运行诊断互相串扰的问题。
- 修复 AlphaSift 热点题材 EastMoney 瞬断且无缓存时的空态、桌面更新热点缓存保留，以及 `leader_stocks` / `stocks` 双字段兼容问题。…37705 tokens truncated…修复信号 emoji 与建议不一致的问题（复合建议如"卖出/观望"未正确映射）
- 🐛 修复 `*ST` 股票名在微信/Dashboard 中 markdown 转义问题
- 🐛 修复 `idx.amount` 为 None 时大盘复盘 TypeError
- 🐛 修复分析 API 返回 `report=None` 及 ReportStrategy 类型不一致问题
- 🐛 修复 Tushare 返回类型错误（dict → UnifiedRealtimeQuote）及 API 端点指向

### 新增
- 📊 大盘复盘报告注入结构化数据（涨跌统计、指数表格、板块排名）
- 🔍 搜索结果 TTL 缓存（500 条上限，FIFO 淘汰）
- 🔧 Tushare Token 存在时自动注入实时行情优先级
- 📰 新闻摘要截断长度 50→200 字

### 优化
- ⚡ 补充行情字段请求限制为最多 1 次，减少无效请求

## [3.0.4] - 2026-02-07

### 新增
- 📈 **回测引擎** (PR #269)
  - 新增基于历史分析记录的回测系统，支持收益率、胜率、最大回撤等指标评估
  - WebUI 集成回测结果展示

## [3.0.3] - 2026-02-07

### 修复
- 🐛 修复狙击点位数据解析错误问题 (PR #271)

## [3.0.2] - 2026-02-06

### 新增
- ✉️ 可配置邮件发送者名称 (PR #272)
- 🌐 外国股票支持英文关键词搜索

## [3.0.1] - 2026-02-06

### 修复
- 🐛 修复 ETF 实时行情获取、市场数据回退、企业微信消息分块问题
- 🔧 CI 流程简化

## [3.0.0] - 2026-02-06

### 移除
- 🗑️ **移除旧版 WebUI**
  - 删除基于 `http.server.ThreadingHTTPServer` 的旧版 WebUI（`web/` 包）
  - 旧版 WebUI 的功能已完全被 FastAPI（`api/`）+ React 前端替代
  - `--webui` / `--webui-only` 命令行参数标记为弃用，自动重定向到 `--serve` / `--serve-only`
  - `WEBUI_ENABLED` / `WEBUI_HOST` / `WEBUI_PORT` 环境变量保持兼容，自动转发到 FastAPI 服务
  - `webui.py` 保留为兼容入口，启动时直接调用 FastAPI 后端
  - Docker Compose 中移除 `webui` 服务定义，统一使用 `server` 服务

### 变更
- ♻️ **服务层重构**
  - 将 `web/services.py` 中的异步任务服务迁移至 `src/services/task_service.py`
  - Bot 分析命令（`bot/commands/analyze.py`）改为使用 `src.services.task_service`
  - Docker 环境变量 `WEBUI_HOST`/`WEBUI_PORT` 更名为 `API_HOST`/`API_PORT`（旧名仍兼容）

## [2.3.0] - 2026-02-01

### 新增
- 🇺🇸 **增强美股支持** (Issue #153)
  - 实现基于 Akshare 的美股历史数据获取 (`ak.stock_us_daily()`)
  - 实现基于 Yfinance 的美股实时行情获取（优先策略）
  - 增加对不支持数据源（Tushare/Baostock/Pytdx/Efinance）的美股代码过滤和快速降级

### 修复
- 🐛 修复 AMD 等美股代码被误识别为 A 股的问题 (Issue #153)

## [2.2.5] - 2026-02-01

### 新增
- 🤖 **AstrBot 消息推送** (PR #217)
  - 新增 AstrBot 通知渠道，支持推送到 QQ 和微信
  - 支持 HMAC SHA256 签名验证，确保通信安全
  - 通过 `ASTRBOT_URL` 和 `ASTRBOT_TOKEN` 配置

## [2.2.4] - 2026-02-01

### 新增
- ⚙️ **可配置数据源优先级** (PR #215)
  - 支持通过环境变量（如 `YFINANCE_PRIORITY=0`）动态调整数据源优先级
  - 无需修改代码即可优先使用特定数据源（如 Yahoo Finance）

## [2.2.3] - 2026-01-31

### 修复
- 📦 更新 requirements.txt，增加 `lxml_html_clean` 依赖以解决兼容性问题

## [2.2.2] - 2026-01-31

### 修复
- 🐛 修复代理配置区分大小写问题 (fixes #211)

## [2.2.1] - 2026-01-31

### 修复
- 🐛 **YFinance 兼容性修复** (PR #210, fixes #209)
  - 修复新版 yfinance 返回 MultiIndex 列名导致的数据解析错误

## [2.2.0] - 2026-01-31

### 新增
- 🔄 **多源回退策略增强**
  - 实现了更健壮的数据获取回退机制 (feat: multi-source fallback strategy)
  - 优化了数据源故障时的自动切换逻辑

### 修复
- 🐛 修复 analyzer 运行后无法通过改 .env 文件的 stock_list 内容调整跟踪的股票

## [2.1.14] - 2026-01-31

### 文档
- 📝 更新 README 和优化 auto-tag 规则

## [2.1.13] - 2026-01-31

### 修复
- 🐛 **Tushare 优先级与实时行情** (Fixed #185)
  - 修复 Tushare 数据源优先级设置问题
  - 修复 Tushare 实时行情获取功能

## [2.1.12] - 2026-01-30

### 修复
- 🌐 修复代理配置在某些情况下的区分大小写问题
- 🌐 修复本地环境禁用代理的逻辑

## [2.1.11] - 2026-01-30

### 优化
- 🚀 **飞书消息流优化** (PR #192)
  - 优化飞书 Stream 模式的消息类型处理
  - 修改 Stream 消息模式默认为关闭，防止配置错误运行时报错

## [2.1.10] - 2026-01-30

### 合并
- 📦 合并 PR #154 贡献

## [2.1.9] - 2026-01-30

### 新增
- 💬 **微信文本消息支持** (PR #137)
  - 新增微信推送的纯文本消息类型支持
  - 添加 `WECHAT_MSG_TYPE` 配置项

## [2.1.8] - 2026-01-30

### 修复
- 🐛 修正日志中 API 提供商显示错误 (PR #197)

## [2.1.7] - 2026-01-30

### 修复
- 🌐 禁用本地环境的代理设置，避免网络连接问题

## [2.1.6] - 2026-01-29

### 新增
- 📡 **Pytdx 数据源 (Priority 2)**
  - 新增通达信数据源，免费无需注册
  - 多服务器自动切换
  - 支持实时行情和历史数据
- 🏷️ **多源股票名称解析**
  - DataFetcherManager 新增 `get_stock_name()` 方法
  - 新增 `batch_get_stock_names()` 批量查询
  - 自动在多数据源间回退
  - Tushare 和 Baostock 新增股票名称/列表方法
- 🔍 **增强搜索回退**
  - 新增 `search_stock_price_fallback()` 用于数据源全部失败时
  - 新增搜索维度：市场分析、行业分析
  - 最大搜索次数从 3 增加到 5
  - 改进搜索结果格式（每维度 4 条结果）

### 改进
- 更新搜索查询模板以提高相关性
- 增强 `format_intel_report()` 输出结构

## [2.1.5] - 2026-01-29

### 新增
- 📡 新增 Pytdx 数据源和多源股票名称解析功能

## [2.1.4] - 2026-01-29

### 文档
- 📝 更新赞助商信息

## [2.1.3] - 2026-01-28

### 文档
- 📝 重构 README 布局
- 🌐 新增繁体中文翻译 (README_CHT.md)

### 修复
- 🐛 修复 WebUI 无法输入美股代码问题
  - 输入框逻辑改成所有字母都转换成大写
  - 支持 `.` 的输入（如 `BRK.B`）

## [2.1.2] - 2026-01-27

### 修复
- 🐛 修复个股分析推送失败和报告路径问题 (fixes #166)
- 🐛 修改 CR 错误，确保微信消息最大字节配置生效

## [2.1.1] - 2026-01-26

### 新增
- 🔧 添加 GitHub Actions auto-tag 工作流
- 📡 添加 yfinance 兜底数据源及数据缺失警告

### 修复
- 🐳 修复 docker-compose 路径和文档命令
- 🐳 Dockerfile 补充 copy src 文件夹 (fixes #145)

## [2.1.0] - 2026-01-25

### 新增
- 🇺🇸 **美股分析支持**
  - 支持美股代码直接输入（如 `AAPL`, `TSLA`）
  - 使用 YFinance 作为美股数据源
- 📈 **MACD 和 RSI 技术指标**
  - MACD：趋势确认、金叉死叉信号（零轴上金叉⭐、金叉✅、死叉❌）
  - RSI：超买超卖判断（超卖⭐、强势✅、超买⚠️）
  - 指标信号纳入综合评分系统
- 🎮 **Discord 推送支持** (PR #124, #125, #144)
  - 支持 Discord Webhook 和 Bot API 两种方式
  - 通过 `DISCORD_WEBHOOK_URL` 或 `DISCORD_BOT_TOKEN` + `DISCORD_MAIN_CHANNEL_ID` 配置
- 🤖 **机器人命令交互**
  - 钉钉机器人支持 `/分析 股票代码` 命令触发分析
  - 支持 Stream 长连接模式
- 🌡️ **AI 温度参数可配置** (PR #142)
  - 支持自定义 AI 模型温度参数
- 🐳 **Zeabur 部署支持**
  - 添加 Zeabur 镜像部署工作流
  - 支持 commit hash 和 latest 双标签

### 重构
- 🏗️ **项目结构优化**
  - 核心代码移至 `src/` 目录，根目录更清爽
  - 文档移至 `docs/` 目录
  - Docker 配置移至 `docker/` 目录
  - 修复所有 import 路径，保持向后兼容
- 🔄 **数据源架构升级**
  - 新增数据源熔断机制，单数据源连续失败自动切换
  - 实时行情缓存优化，批量预取减少 API 调用
  - 网络代理智能分流，国内接口自动直连
- 🤖 Discord 机器人重构为平台适配器架构

### 修复
- 🌐 **网络稳定性增强**
  - 自动检测代理配置，对国内行情接口强制直连
  - 修复 EfinanceFetcher 偶发的 `ProtocolError`
  - 增加对底层网络错误的捕获和重试机制
- 📧 **邮件渲染优化**
  - 修复邮件中表格不渲染问题 (#134)
  - 优化邮件排版，更紧凑美观
- 📢 **企业微信推送修复**
  - 修复大盘复盘推送不完整问题
  - 增强消息分割逻辑，支持更多标题格式
  - 增加分批发送间隔，避免限流丢失
- 👷 **CI/CD 修复**
  - 修复 GitHub Actions 中路径引用的错误

## [2.0.0] - 2026-01-24

### 新增
- 🇺🇸 **美股分析支持**
  - 支持美股代码直接输入（如 `AAPL`, `TSLA`）
  - 使用 YFinance 作为美股数据源
- 🤖 **机器人命令交互** (PR #113)
  - 钉钉机器人支持 `/分析 股票代码` 命令触发分析
  - 支持 Stream 长连接模式
  - 支持选择精简报告或完整报告
- 🎮 **Discord 推送支持** (PR #124)
  - 支持 Discord Webhook 推送
  - 添加 Discord 环境变量到工作流

### 修复
- 🐳 修复 WebUI 在 Docker 中绑定 0.0.0.0 (fixed #118)
- 🔔 修复飞书长连接通知问题
- 🐛 修复 `analysis_delay` 未定义错误
- 🔧 启动时 config.py 检测通知渠道，修复已配置自定义渠道情况下仍然提示未配置问题

### 改进
- 🔧 优化 Tushare 优先级判断逻辑，提升封装性
- 🔧 修复 Tushare 优先级提升后仍排在 Efinance 之后的问题
- ⚙️ 配置 TUSHARE_TOKEN 时自动提升 Tushare 数据源优先级
- ⚙️ 实现 4 个用户反馈 issue (#112, #128, #38, #119)

## [1.6.0] - 2026-01-19

### 新增
- 🖥️ WebUI 管理界面及 API 支持（PR #72）
  - 全新 Web 架构：分层设计（Server/Router/Handler/Service）
  - 核心 API：支持 `/analysis` (触发分析), `/tasks` (查询进度), `/health` (健康检查)
  - 交互界面：支持页面直接输入代码并触发分析，实时展示进度
  - 运行模式：新增 `--webui-only` 模式，仅启动 Web 服务
  - 解决了 [#70](https://github.com/ZhuLinsen/daily_stock_analysis/issues/70) 的核心需求（提供触发分析的接口）
- ⚙️ GitHub Actions 配置灵活性增强（[#79](https://github.com/ZhuLinsen/daily_stock_analysis/issues/79)）
  - 支持从 Repository Variables 读取非敏感配置（如 STOCK_LIST, GEMINI_MODEL）
  - 保持对 Secrets 的向下兼容

### 修复
- 🐛 修复企业微信/飞书报告截断问题（[#73](https://github.com/ZhuLinsen/daily_stock_analysis/issues/73)）
  - 移除 notification.py 中不必要的长度硬截断逻辑
  - 依赖底层自动分片机制处理长消息
- 🐛 修复 GitHub Workflow 环境变量缺失（[#80](https://github.com/ZhuLinsen/daily_stock_analysis/issues/80)）
  - 修复 `CUSTOM_WEBHOOK_BEARER_TOKEN` 未正确传递到 Runner 的问题

## [1.5.0] - 2026-01-17

### 新增
- 📲 单股推送模式（[#55](https://github.com/ZhuLinsen/daily_stock_analysis/issues/55)）
  - 每分析完一只股票立即推送，不用等全部分析完
  - 命令行参数：`--single-notify`
  - 环境变量：`SINGLE_STOCK_NOTIFY=true`
- 🔐 自定义 Webhook Bearer Token 认证（[#51](https://github.com/ZhuLinsen/daily_stock_analysis/issues/51)）
  - 支持需要 Token 认证的 Webhook 端点
  - 环境变量：`CUSTOM_WEBHOOK_BEARER_TOKEN`

## [1.4.0] - 2026-01-17

### 新增
- 📱 Pushover 推送支持（PR #26）
  - 支持 iOS/Android 跨平台推送
  - 通过 `PUSHOVER_USER_KEY` 和 `PUSHOVER_API_TOKEN` 配置
- 🔍 博查搜索 API 集成（PR #27）
  - 中文搜索优化，支持 AI 摘要
  - 通过 `BOCHA_API_KEYS` 配置
- 📊 Efinance 数据源支持（PR #59）
  - 新增 efinance 作为数据源选项
- 🇭🇰 港股支持（PR #17）
  - 支持 5 位代码或 HK 前缀（如 `hk00700`、`hk1810`）

### 修复
- 🔧 飞书 Markdown 渲染优化（PR #34）
  - 使用交互卡片和格式化器修复渲染问题
- ♻️ 股票列表热重载（PR #42 修复）
  - 分析前自动重载 `STOCK_LIST` 配置
- 🐛 钉钉 Webhook 20KB 限制处理
  - 长消息自动分块发送，避免被截断
- 🔄 AkShare API 重试机制增强
  - 添加失败缓存，避免重复请求失败接口

### 改进
- 📝 README 精简优化
  - 高级配置移至 `docs/full-guide.md`


## [1.3.0] - 2026-01-12

### 新增
- 🔗 自定义 Webhook 支持
  - 支持任意 POST JSON 的 Webhook 端点
  - 自动识别钉钉、Discord、Slack、Bark 等常见服务格式
  - 支持配置多个 Webhook（逗号分隔）
  - 通过 `CUSTOM_WEBHOOK_URLS` 环境变量配置

### 修复
- 📝 企业微信长消息分批发送
  - 解决自选股过多时内容超过 4096 字符限制导致推送失败的问题
  - 智能按股票分析块分割，每批添加分页标记（如 1/3, 2/3）
  - 批次间隔 1 秒，避免触发频率限制

## [1.2.0] - 2026-01-11

### 新增
- 📢 多渠道推送支持
  - 企业微信 Webhook
  - 飞书 Webhook（新增）
  - 邮件 SMTP（新增）
  - 自动识别渠道类型，配置更简单

### 改进
- 统一使用 `NOTIFICATION_URL` 配置，兼容旧的 `WECHAT_WEBHOOK_URL`
- 邮件支持 Markdown 转 HTML 渲染

## [1.1.0] - 2026-01-11

### 新增
- 🤖 OpenAI 兼容 API 支持
  - 支持 DeepSeek、通义千问、Moonshot、智谱 GLM 等
  - Gemini 和 OpenAI 格式二选一
  - 自动降级重试机制

## [1.0.0] - 2026-01-10

### 新增
- 🎯 AI 决策仪表盘分析
  - 一句话核心结论
  - 精确买入/止损/目标点位
  - 检查清单（✅⚠️❌）
  - 分持仓建议（空仓者 vs 持仓者）
- 📊 大盘复盘功能
  - 主要指数行情
  - 涨跌统计
  - 板块涨跌榜
  - AI 生成复盘报告
- 🔍 多数据源支持
  - AkShare（主数据源，免费）
  - Tushare Pro
  - Baostock
  - YFinance
- 📰 新闻搜索服务
  - Tavily API
  - SerpAPI
- 💬 企业微信机器人推送
- ⏰ 定时任务调度
- 🐳 Docker 部署支持
- 🚀 GitHub Actions 零成本部署

### 技术特性
- Gemini AI 模型（gemini-3-flash-preview）
- 429 限流自动重试 + 模型切换
- 请求间延时防封禁
- 多 API Key 负载均衡
- SQLite 本地数据存储

---

[Unreleased]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.25.0...HEAD
[3.25.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.24.1...v3.25.0
[3.24.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.24.0...v3.24.1
[3.24.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.23.0...v3.24.0
[3.23.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.22.0...v3.23.0
[3.22.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.21.1...v3.22.0
[3.21.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.21.0...v3.21.1
[3.21.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.20.0...v3.21.0
[3.20.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.19.0...v3.20.0
[3.19.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.18.0...v3.19.0
[3.18.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.17.1...v3.18.0
[3.17.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.17.0...v3.17.1
[3.17.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.16.0...v3.17.0
[3.16.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.15.0...v3.16.0
[3.15.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.14.2...v3.15.0
[3.14.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.14.1...v3.14.2
[3.14.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.14.0...v3.14.1
[3.14.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.13.0...v3.14.0
[3.13.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.12.0...v3.13.0
[3.12.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.11.0...v3.12.0
[3.11.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.10.1...v3.11.0
[3.10.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.10.0...v3.10.1
[3.10.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.9.0...v3.10.0
[3.9.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.8.0...v3.9.0
[3.8.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.7.0...v3.8.0
[3.7.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.6.0...v3.7.0
[3.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.10...v3.5.0
[3.4.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.9...v3.4.10
[3.4.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.8...v3.4.9
[3.4.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.7...v3.4.8
[3.4.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.0...v3.4.7
[3.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.3.22...v3.4.0
[3.3.22]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.3.12...v3.3.22
[3.3.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.2.11...v3.3.12
[3.2.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.2.10...v3.2.11
[2.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.5...v2.3.0
[2.2.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.4...v2.2.5
[2.2.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.14...v2.2.0
[2.1.14]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.13...v2.1.14
[2.1.13]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.12...v2.1.13
[2.1.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.11...v2.1.12
[2.1.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.10...v2.1.11
[2.1.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.9...v2.1.10
[2.1.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.8...v2.1.9
[2.1.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.7...v2.1.8
[2.1.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.6...v2.1.7
[2.1.6]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.5...v2.1.6
[2.1.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.4...v2.1.5
[2.1.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.6.0...v2.0.0
[1.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/releases/tag/v1.0.0
