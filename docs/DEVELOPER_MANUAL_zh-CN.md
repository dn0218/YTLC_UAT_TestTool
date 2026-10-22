# Preprod Telecom Operations Toolkit — 开发人员手册（v2）

> 版本基线：模块化重构版（`main.py` 入口 + `core / connections / services / ui` 分层结构，6 个功能页签，配置加密，Redis 缓存失效）。
> 旧版单文件实现保留于 `Preprod_TestTool.py`（同样含加密与漫游功能），仅作历史参考；**新功能一律在分层结构中开发**。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈与运行环境](#2-技术栈与运行环境)
3. [目录结构](#3-目录结构)
4. [架构设计](#4-架构设计)
5. [配置体系与值加密](#5-配置体系与值加密)
6. [连接层详解](#6-连接层详解)
7. [服务层详解](#7-服务层详解)
8. [关键业务流程](#8-关键业务流程)
9. [线程模型与 UI 线程桥](#9-线程模型与-ui-线程桥)
10. [构建与打包](#10-构建与打包)
11. [开发指南：如何扩展](#11-开发指南如何扩展)
12. [已知问题与注意事项](#12-已知问题与注意事项)

---

## 1. 项目概述

本工具是面向电信**预生产环境（Preprod）**的桌面运维工具箱，对 OCS（在线计费系统）与 CRM 数据执行日常操作：

| # | 功能页签 | 功能 | 依赖的后端 |
|---|---------|------|-----------|
| 1 | Invoice Generation | 账户出账：RecurrRate 预计费 + 远程账单脚本 + DB 核验 | SSH + Oracle(cc) + DBLink(link_rb) |
| 2 | Contract End Date | 合同到期日查询 / 修改 / 停用（三表同步）+ Redis 缓存失效 | Oracle(cc) + Redis Cluster |
| 3 | MSISDN Clean '0' | 去除号码末尾 `0`（subs / crm.acc_nbr / cc.acc_nbr 三表改名） | Oracle(cc, 跨 schema) |
| 4 | Sales Invoice | 触发预付费/后付费销售发票作业 + SEND_DATE 重置 | REST API（job server）+ Oracle(cc) |
| 5 | SIM Card Attribute | 按 ICCID 查询 SIM 卡，编辑 `EXP_SIM_PRODUCT_TYPE` 属性 | Oracle(crm 连接) |
| 6 | Roaming Subscription Pass | 通过 OCS mdbtt SQL 控制台插入漫游开通 asyn_call 行 | Oracle(cc) + SSH 交互式 shell |

横切能力：

- **配置值加密**：`config_ocs.json` 中口令以 `enc:v1:` 密文存放，加载时透明解密（见第 5 节）；
- **缓存失效**：写操作后清理 OCS Redis 的 `DUMP_SUBS_CACHE` 键，best-effort、失败不影响 DB 结果（见 7.2）。

所有数据库写操作均直接作用于预生产库，**务必确认配置指向的环境正确**后再执行。

---

## 2. 技术栈与运行环境

| 组件 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3（建议 ≥ 3.9） | dataclass、f-string 等 |
| GUI | tkinter / ttk（内置） | 主题基于 `clam`，见 `ui/theme.py` |
| Oracle 驱动 | `oracledb >= 1.4` | **thin 模式**，无需 Oracle Client |
| SSH | `paramiko >= 2.11` | 密码认证、`AutoAddPolicy`、PTY 交互 |
| HTTP | `requests >= 2.28` | jobservermgr 触发接口 |
| Redis | `redis >= 4.1` | **Cluster 模式**（`RedisCluster`） |
| 加密 | 仅标准库（hashlib/hmac/base64） | 无第三方依赖 |
| 打包 | `pyinstaller >= 5.13` | 单文件 windowed exe |

开发运行：

```bash
pip install -r requirements.txt   # pyinstaller 仅打包时需要
python main.py
```

---

## 3. 目录结构

```
preprod tools/
├── main.py                    # 应用入口（异常兜底；input() 有 stdin 保护）
├── config_ocs.json            # 运行时配置（口令为 enc:v1: 密文）
├── encrypt_config.py          # 管理员工具：加密/解密/查看配置中的口令
├── requirements.txt
├── build.bat / build.spec     # PyInstaller 打包
│
├── core/                      # 基础层：配置 / 加密 / 模型 / 异常
│   ├── config.py              # AppConfig：加载 + 透明解密 + 默认模板
│   ├── crypto.py              # enc:v1: 混淆级加密（keystream XOR + HMAC tag）
│   ├── models.py              # frozen dataclass 数据模型
│   └── errors.py              # 自定义异常体系
│
├── connections/               # 连接层：远程资源薄封装（懒连接、可复用）
│   ├── base.py                # BaseConnection 契约
│   ├── db_client.py           # OracleClient / CrmOracleClient（CURRENT_SCHEMA 处理）
│   ├── ssh_client.py          # 流式 exec + 交互式 shell（send_line/read_until）
│   ├── redis_client.py        # RedisCluster 封装，UNLINK 缓存失效
│   └── api_client.py          # triggerJob REST（params 已 URL 编码）
│
├── services/                  # 业务层：纯逻辑，不依赖 UI
│   ├── account_service.py     # 账户校验 / 账期 / SUBS 解析 / EVENT_RECURRING 计数
│   ├── invoice_service.py     # 出账三阶段（预计费判定含 TRUNC + 日期语义）
│   ├── contract_service.py    # 合同三表更新 + Redis 缓存失效
│   ├── msisdn_service.py      # MSISDN 去零改名
│   ├── sales_invoice_service.py # job 触发 + 销售 SEND_DATE 重置
│   ├── sim_card_service.py    # SIM 查询 + ROWID 精确更新
│   └── roaming_service.py     # mdbtt 交互式 asyn_call 插入（IRAN/KENYA）
│
├── ui/                        # 界面层
│   ├── main_window.py         # 装配 notebook 与 6 个页签；关闭时释放连接
│   ├── base_tab.py            # AppContext（5 连接 + 7 服务）+ BaseTab
│   ├── threading_bridge.py    # 工作线程 → UI 线程调度
│   ├── theme.py / widgets.py  # 主题 / ConsoleWidget
│   └── tabs/                  # 6 个功能页签
│
├── Preprod_TestTool.py        # 【遗留】重构前单文件版本（不再维护）
├── backup/                    # 【遗留】历史 .bak
└── docs/                      # 手册（本文档 + 用户手册/简易版）
```

**依赖方向（严格单向）：**

```
core  ←  connections  ←  services  ←  ui
```

---

## 4. 架构设计

### 4.1 分层职责

| 层 | 职责 | 禁止事项 |
|----|------|---------|
| `core` | 配置加载、加密原语、数据模型、异常 | 不 import 项目内其他层 |
| `connections` | 建连/复用/自愈、执行原始 SQL/命令、异常翻译 | 不含业务判断 |
| `services` | 业务规则、SQL 文本、流程编排 | 不 import tkinter |
| `ui` | 视图、事件、线程调度、结果展示 | 不直接写 SQL / 操作连接 |

### 4.2 启动装配流程

```
main.main()
 └─ MainWindow.__init__()
     ├─ AppConfig()               # 读配置 + 透明解密；缺失则写默认模板并退出
     ├─ apply_theme(root)
     ├─ AppContext(root, config)  # 5 连接 + 7 服务（全部懒初始化，启动不建连）
     └─ _build_notebook()         # 6 个页签
关窗 → _on_close() → close() db / crm_db / ssh / redis → destroy
```

### 4.3 数据模型与异常

与 v1 相同，全部 frozen dataclass（`BillingCycle / AccountInfo / MsisdnInfo / AgreementInfo / BillRunResult / CycleQueryResult`），异常体系见 `core/errors.py`（`AppConfigError`、`ConnectionError_` 族、`BusinessRuleError`）。UI 统一经 `BaseTab.handle_error()` 弹窗。

---

## 5. 配置体系与值加密

### 5.1 配置文件（config_ocs.json）

```jsonc
{
  "db":      { "host", "port", "service_name", "user", "password",
               "schema"(可选，默认 CC) },   // OCS 库，当前登录用户 bss_ms_ai
  "ssh":     { "host", "username", "password" },
  "api":     { "base_url" },
  "redis":   { "nodes": [[host, port], ...], "password"(可空) },  // Cluster 节点表
  "crm_db":  { ...同 db... }                 // Tab 5 使用；缺省回退内置默认
}
```

- `crm_db`、`redis` 节缺失时回退 `DEFAULT_CONFIG`（向后兼容）；
- `redis` 校验宽松：`nodes` 必须是 list，`password` 可为 null；
- **运行时查找顺序（frozen 环境）**：exe 同目录 → `_MEIPASS` 内置副本 → 源码目录。意味着升级配置**无需重新打包**，把新 `config_ocs.json` 放到 exe 旁边即可。

### 5.2 值加密（core/crypto.py）

**格式**：`enc:v1:<base64(nonce[8] + ciphertext + tag[8])>`

**算法**：密钥 = `sha256(K1 + 0x50 + K2)`（K1/K2 硬编码且拆分存放，防 `strings` 单块扫描）；keystream = `HMAC-SHA256(key, nonce + counter)` 计数器模式；加密 = XOR；完整性 = 8 字节 HMAC tag，解密时 `compare_digest` 校验，被篡改/密钥不符抛 `ValueError`。

**定位（务必向团队说明）**：这是**混淆级**加密——防的是配置文件被随手打开、截图、转发时明文口令外泄；**密钥随程序分发，防不了逆向**。不要把它当作真正的密钥管理。

**关键性质**：

- 向后兼容：没有 `enc:v1:` 前缀的值原样返回（明文配置仍可用）；
- 加密 nonce 默认由明文派生 → **同一明文密文恒定**（可作等值比对，无随机性）；
- `is_encrypted()` 可判断值形态。

### 5.3 透明解密（core/config.py）

- `AppConfig.SENSITIVE_KEYS = ("password",)`：`_section()` 对 db / ssh / crm_db 的 `password` 自动解密，失败抛 `AppConfigError("db.password: ...")` 指明具体键；
- `redis.password` 在 `load()` 中单独解密（该节走宽松校验路径）。

### 5.4 管理员工具（encrypt_config.py）

```bash
python encrypt_config.py            # 就地加密所有明文 password（幂等：跳过已是 enc:v1: 的）
python encrypt_config.py --decrypt  # 就地解密回明文
python encrypt_config.py --show     # 解密并打印（排障用，不落盘）
```

- 只递归处理键名为 `password` 的值，其他字节原样保留（indent=4, ensure_ascii=False）；
- `load_crypto()` 优先从 `core.crypto` 导入；失败则尝试加载 `Preprod_TestTool.py`（单文件版，密钥与格式完全一致），再失败则文本截取其加密代码段 exec —— 保证两套程序共享同一配置文件。

### 5.5 CURRENT_SCHEMA 处理（重要）

`db_client.py` 两个 Client 建连后都执行：

```sql
ALTER SESSION SET CURRENT_SCHEMA=<db.schema 或 'CC'>
```

原因：应用 SQL 全部使用**未限定表名**（`subs`、`acct`…，属 CC schema）。当前登录用户是 **bss_ms_ai（非 schema owner）**，裸表名会报 `ORA-00942`。设了 CURRENT_SCHEMA 后任何被授权用户都能解析。配置里 `db.schema` 键可选，缺省 `CC`。

---

## 6. 连接层详解

### 6.1 db_client.py

- **懒连接 + ping 自愈**：`get_connection()` 先 ping 复用，失败关闭重建；
- `query_one / query_all / execute`（DML 成功 commit、异常 rollback）/ `cursor()`（逃生舱，调用方自管事务）；
- ⚠️ 已知瑕疵：`CrmOracleClient.get_connection()` 末尾有**重复的 `except Exception` 死代码**（第二个永不执行），见第 12 节。

### 6.2 ssh_client.py（v2 大幅扩展）

**A. 流式执行（原有）**：`exec_command_stream(command, on_line, is_meaningful)`
- `get_pty=True`，逐行回调"有意义的行"（默认出账 Step 标记；调用方可传 `is_meaningful=lambda l: True` 全量捕获）；
- v2 新增**连续重复行去重**：PTY 把 stderr 合并进 stdout，同一日志行可能双写，取 `last` 行比对跳过；
- 异常时主动 close 连接（下次自动重连），返回远端退出码。

**B. 交互式 shell（新增，为 mdbtt 服务）**：

| 方法 | 说明 |
|------|------|
| `open_interactive_shell(term, width, height)` | `invoke_shell` 持久 PTY 通道（vt100, 500×50, chan 超时 5s） |
| `send_line(line)` | 写一行（`\r\n` 结尾），记录 `_last_sent_line` 供回显剥离 |
| `read_until(patterns, timeout, on_line, echo_strip)` | 轮询读取（0.2s）直到 buffer 尾部 512 字节或最近 5 行命中任一 pattern；返回 `(matched_or_None, 已完成行拼接)` |
| `close_interactive_shell()` | 关闭通道（调用方**必须**负责关闭） |

细节：
- `strip_ansi()`：正则剔除 ANSI 转义序列（光标移动/清屏），mdbtt 输出含此类控制符；
- **回显剥离**：PTY 会把发出的命令回显回来，`read_until` 将与 `_last_sent_line` 相同（或尾随 `;`）的行丢弃；
- 超时未命中 pattern 返回 `(None, buffer)`，由调用方决定如何处置（roaming 服务据此打印尾部 12 行排障）。

### 6.3 redis_client.py

- `RedisCluster(startup_nodes, password, decode_responses=True, socket_timeout=5)`，懒初始化；
- `invalidate(key)`：**best-effort UNLINK**，返回 `(True, 提息)` / `(False, 错误文本)`，**从不抛异常**——缓存失败绝不连累 DB 更新结果；失败时置空连接强制下次重建；
- 返回消息里带 UNLINK 整数回复：`1` = 真删了缓存键，`0` = 键本就不存在（都是成功）。

### 6.4 api_client.py

v2 修复：`params` 经 `quote(params, safe="")` **完整 URL 编码**后再拼 URL。params 含 `|` 等保留字符，job server 的 servlet 会解码，不编码会被截断/误解析。30s 超时，非 2xx 抛 `ApiConnectionError`。

---

## 7. 服务层详解

### 7.1 AccountService（查询基础）

除 v1 的方法外，v2 关键变化：

- **`get_bal_share_subs_ids(acct_id)`**（新增）：查 `bal_share(PAYMENT_FORCE='Y') ⋈ bal_share_detail(EXP_DATE IS NULL)`，返回余额共享池中的 SUBS_ID。这些订阅与本账户共享余额，**必须一并预计费**，否则账单缺少共享部分的周期性费用。出账时与 `get_subs_ids` 结果去重合并（`dict.fromkeys` 保序）。
- **`count_event_recurring(...)` 判定语义重写**（新增参数 `truncated_time` / `on_date`）：
  - 旧逻辑按 `ACCT_ITEM_TYPE_ID1=12` 识别预计费行 —— **已证不可靠**（不同周期观察到 12 和 4311 两种取值）；
  - 新逻辑：RecurrRate 写入的行其 `EVENT_BEGIN_TIME` 为**整天（TRUNC 后等于自身，即午夜 00:00）**，由 `-d` 参数决定日期；开户补充收费带真实（非午夜）时间戳；
  - `on_date` 进一步限定日期：RecurrRate 把预计费写在**下一周期起始日（= 本周期结束日）**，其他日期的整天行不属于本周期预计费。

### 7.2 ContractService（合同）

- `update_expiry_date` / `deactivate` 现在更新**三张表**：`prod.AGREEMENT_EXP_DATE`、`subs_agreement_inst.EFF_DATE`、**`cc.subs_agreement_inst.EXP_DATE`（新增）** —— CC 侧视图必须同步，否则数据不一致；TO_DATE 失败仍回退 TO_TIMESTAMP；
- **`invalidate_subs_cache(agreement)`**（新增）：DB 更新成功后 UNLINK `DUMP_SUBS_CACHE/ADAPTER_QRY_SUBS_INFO/{subs_id}`（subs_id 即 prod_id）。失败仅打 WARNING，不改变操作成功结论；UI 弹窗会附注"缓存失效失败请检查 Redis"。

### 7.3 InvoiceService（出账，判定核心）

v2 三处语义变化（都不再"硬中止"）：

1. **`-d` 参数日期**：必须传**下一周期起始日 = 本周期 `end_date`**（例：cycle 2969 / type 316，END 2026-10-16 → `-d 20261016`）；
2. **跳过/核验判定**：`count_event_recurring(truncated_time=True, on_date=next_begin_date)`，不再看 item type；
3. **预计费失败不再中止**：`run_prebilling` 返回 False 仅表示"部分订阅无预计费行"，由 **GUI 弹窗询问用户**是否继续跑 `Brainless_Invoice.sh`（用户确认则带风险继续，拒绝则中止且不执行出账脚本）——v1 是无条件中止；
4. `mark_invoice_sent` 变更：`UPDATE e_invoice SET SEND_DATE=sysdate-1 WHERE acct_id=:1`（**去掉了 billing_cycle_id 条件，覆盖该账户全部发票行**），让该账户所有待处理发票都能被发送作业重新拾取。

### 7.4 SalesInvoiceService

触发成功（HTTP 200）后新增 `update_send_date(acct_id)`：对 `BILLING_CYCLE_ID IS NULL`（销售型发票的识别特征；账单型发票必有周期 ID）的行执行 `SEND_DATE=sysdate-1`，允许重新处理。best-effort：失败打日志返回 -1，不影响触发成功结论。

### 7.5 MsisdnService / SimCardService

与 v1 一致（三表改名 / ROWID 单行更新+回读校验）。注意 msisdn 三条 UPDATE 仍是各自独立提交（见第 12 节）。

### 7.6 RoamingService（新增，Tab 6）

业务：为指定 MSISDN 的**每一个 SUBS_ID**（一个号码可能绑多个订阅，如改号后遗留）向 OCS `asyn_call` 表插入漫游通行证 AVP 配置行（`EVENT_ID=2, STATE='A', PRIORITY=500`，主键 `asyn_call_id_seq.nextval`）。

**关键约束：`asyn_call` 的写入必须走 OCS 侧的 mdbtt 控制台（SSH 主机），不能直连 cc 库插**——与出账同一主机/路径，保证经过 OCS 平台逻辑。

国家 AVP 仅三字段不同：

| Country | 1463 | 1464 | 1465 |
|---------|------|------|------|
| KENYA | 03 | 639 | 10502 |
| IRAN | 35 | 432 | 10240 |

`run_mdbtt_inserts(subs_ids, country, on_log, confirm)` 的时序（详见 8.2）返回 `(ok, done_subs, failed_subs)`；`confirm` 回调允许调用方在首条语句前请求人工确认（当前 GUI 已在 UI 层确认过，传恒 True）。

---

## 8. 关键业务流程

### 8.1 出账流程（Tab 1）

```
Check Account → resolve_acct_id → validate_active_postpaid → get_billing_cycles
                                                     （账期下拉框 v2 起为 readonly 可选）
Run Bill & Generate Invoice（非当前账期先二次确认）
 ├─ 阶段① run_prebilling
 │   a. subs_ids = get_subs_ids ∪ get_bal_share_subs_ids（去重）   ← v2：含余额共享订阅
 │   b. 逐个 count_event_recurring(truncated_time=True, on_date=end_date)
 │      已有预计费行 → 跳过                                        ← v2：新判定
 │   c. 定位 RecurrRate：bash -lc 'which RecurrRate' → ~/bin/ → ~/invoicing/bin/（均失败返回 False）
 │   d. 逐个执行：bash -lc 'cd invoicing/ && <path>/RecurrRate -t <type> -T -d <本周期end_date> -e 1 -s <subs> -l 5'
 │      ← v2：-d 是下一周期起始日（= 本周期结束日）
 │   e. sleep 10s 后复查 b；仍有缺失 → 返回 False
 │      → GUI 弹窗询问：继续出账 / 中止                             ← v2：不再硬中止
 ├─ 阶段② run_bill_script：cd invoicing/ && ./Brainless_Invoice.sh <cycle_id> <acct_id>
 └─ 阶段③ verify_bill：sleep 30s → 轮询 e_invoice(5×10s) 取号
      → 取到则 UPDATE e_invoice SET SEND_DATE=sysdate-1 WHERE acct_id=:1（全账户）← v2
      → 读 bill_data_<cycle>@link_rb.BILL_CONTENT（BLOB→UTF-8）
      → 含 "null" → 弹窗问是否重跑（递归 _do_run_bill）；否则成功弹窗
```

### 8.2 漫游开通 mdbtt 时序（Tab 6）

```
open_interactive_shell()                          # PTY 通道
  read_until(["> ", "$ ", "# "], 15s)              # 等 shell 提示符
  send_line("cd invoicing/") → read_until(prompt)
  send_line("mdbtt")     → read_until(["SQL>>"], 60s, 逐行打日志)
      未命中 → 打印尾部 12 行，整体失败退出
  for 每个 subs_id:
      send_line(INSERT_SQL + ";")                  # 分号必须！否则控制台等待续行永不返回
      read_until(["SQL>>", "ERROR", "error", "ORA-"], 60s)
      命中 SQL>> → done；否则记 failed
  send_line("commit;") → read_until(["SQL>>"])
  sleep 10s                                        # 等 OCS 平台消化异步 asyn_call 行
  send_line("quit;") → sleep 3s
close_interactive_shell()（finally 保证）
返回 (not failed, done, failed)
```

### 8.3 RecurrRate 路径解析（为什么绕）

paramiko `exec_command` 是**非登录 shell**，不加载 `~/.bash_profile`，缺 OCS 的 `PATH`/`LD_LIBRARY_PATH`。解决链：`bash -lc 'which RecurrRate'`（登录 shell 解析绝对路径 + 抓 LD_LIBRARY_PATH 供日志）→ `~/bin/` → `~/invoicing/bin/` 探测 → 失败报错退出。执行也包 `bash -lc`，与人工交互完全等价。

---

## 9. 线程模型与 UI 线程桥

与 v1 相同：**Tk 控件只能在主线程操作**。`BaseTab.run_worker()` 起 daemon 线程；`UIThreadBridge` 提供 `run_on_ui / log / ask_yes_no（Event 阻塞等待，600s 超时）/ show_*`。页签固定套路：

- `on_xxx()`（主线程）：校验输入 → `_set_busy(True)` → `run_worker(self._do_xxx, ...)`
- `_do_xxx()`（工作线程）：try 业务调用 + `self._log(...)`；except `handle_error`；finally `bridge.run_on_ui(self._set_busy, False)`。

---

## 10. 构建与打包

```bat
build.bat → pip install -r requirements.txt → pyinstaller --noconfirm build.spec
输出 dist\PreprodTestTool\PreprodTestTool.exe
```

`build.spec` v2 要点：

- `hiddenimports` 显式列出各层模块 + `ui.tabs.roaming_tab`、`services.roaming_service`、`connections.redis_client`、`core.crypto`；
- **`cryptography.hazmat.primitives.kdf`**：paramiko 的 Ed25519/RSA 后端是懒导入，PyInstaller 抓不到，冻结 exe 运行时报 `No module named cryptography.hazmat.primitives.kdf` —— 必须显式声明，且追加 `collect_submodules('cryptography')`；
- `collect_submodules('oracledb')` 维持不变；
- `console=False`；调试可临时改 True 看 traceback；
- `datas=[('config_ocs.json', '.')]`：内置默认配置；运行时优先 exe 同目录副本（见 5.1）。

---

## 11. 开发指南：如何扩展

### 11.1 新增功能页签（标准六步）

1. `services/xxx_service.py`：构造函数收所需 client；SQL 绑定变量；异常抛 `BusinessRuleError` 或透传连接层异常；
2. 需要跨层传数据 → `core/models.py` 加 frozen dataclass；
3. `services/__init__.py` 导出；
4. `ui/tabs/xxx_tab.py`：继承 `BaseTab`，按第 9 节套路写事件；
5. `ui/base_tab.py` `AppContext` 实例化服务；`ui/tabs/__init__.py` + `ui/main_window.py` `TAB_CLASSES` 注册；
6. `build.spec` 补 `hiddenimports`。

### 11.2 约定清单（Code Review 检查项）

- [ ] services 层零 UI 依赖；过程输出一律 `on_log` 回调；
- [ ] SQL 绑定变量（`:1`）；动态表名仅允许拼接内部数字 ID（如 `EVENT_RECURRING_{id}`）；
- [ ] 远程交互必须处理超时/未命中 prompt 的路径（参照 roaming 的失败打印尾部输出做法）；
- [ ] 写库后若涉及 OCS 缓存的订阅数据，评估是否需要 `invalidate_subs_cache` 类似的清理；
- [ ] best-effort 的附属操作（缓存/SEND_DATE 等）不得让主操作结果失真；
- [ ] 危险操作前 `bridge.ask_yes_no` 二次确认；
- [ ] 新配置键同步 `DEFAULT_CONFIG` + `_section` 校验；
- [ ] 打包验证 hiddenimports（尤其懒导入的加密/cryptography 相关）。

---

## 12. 已知问题与注意事项

| # | 事项 | 说明 / 建议 |
|---|------|------------|
| 1 | **`CrmOracleClient.get_connection()` 末尾重复 `except Exception`** | 132–137 行两个同型 except，第二个是死代码（Python 只走第一个）。无害但应删除 |
| 2 | **加密是混淆级** | 密钥随程序分发，防截图/明文泄露，不防逆向。向团队沟通预期；如需真安全改 keyring/环境变量 |
| 3 | MSISDN 三表改名无整体事务 | 三条 `execute` 各自提交，中途失败不回滚已提交项。需原子性应共享 cursor 手动 commit |
| 4 | `contains_null` 是朴素子串判断 | XML 中合法字面 "null" 会误报（已知行为） |
| 5 | 出账硬编码等待（10s/30s/5×10s）与漫游（10s/3s） | 沿用实测节奏；调整前与环境入库速度核对 |
| 6 | `mark_invoice_sent` 覆盖全账户 e_invoice | 有意为之（让所有待处理发票可重拾取），但影响面比单周期大，运维上要知晓 |
| 7 | SSH `AutoAddPolicy` 不校验主机指纹 | 内网取舍，勿用于生产 |
| 8 | `encrypt_config.py --show` 会打印明文口令 | 仅排障用；注意终端历史/截图 |
| 9 | 加密 nonce 由明文派生 | 同一明文密文恒定（等值可比对），安全性进一步降低——混淆定位下可接受 |
| 10 | 旧版 `Preprod_TestTool.py` 与 `backup/` | 不再维护；新功能勿加进去 |
| 11 | `_do_run_bill` NULL 重跑采用递归 | 深度受弹窗次数限制，风险低；可改循环 |
| 12 | 根目录 `console.log('FAIL'` 空文件 | 误产物（shell 引号错误生成），建议删除 |
| 13 | `DEFAULT_CONFIG` 仍是明文口令模板 | 首次生成模板给用户改，属预期；但模板本身含真实口令值，分发时注意 |
| 14 | 工具无 About/版本号显示 | 用户反馈时只能报 exe 修改日期；建议后续加版本常量 + About 弹窗（也可在反馈流程中约定文件名带日期） |

---

## 附：一键索引

- 入口与装配：`main.py` → `ui/main_window.py` → `ui/base_tab.py`
- 最简页签模板：`ui/tabs/contract_tab.py`
- 复杂流程样例：`services/invoice_service.py`（三阶段 + 判定语义）`services/roaming_service.py`（交互式 shell 驱动）
- 加密体系：`core/crypto.py` + `encrypt_config.py`
- 缓存失效：`connections/redis_client.py` + `services/contract_service.py`
- 线程安全输出：`ui/threading_bridge.py` + `ui/widgets.py`
