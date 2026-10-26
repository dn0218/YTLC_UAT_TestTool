# Oracle 连接套件(oracle_conn_kit)复用指南

> 目的:在其他程序 / agent 里,**原样复用** YTLC_UAT_TestTool 的 Oracle
> 连接方式。整个套件只有一个文件夹 `oracle_conn_kit/`,零项目内部依赖,
> 拷走即用。

---

## 1. 连接方式是什么(一句话版)

**python-oracledb thin 模式**,DSN 写成 `host:port/service_name`,
**不需要安装 Oracle Client**;连接懒建立、每次取用时 `ping()` 检查,
断了自动重连;连上后执行 `ALTER SESSION SET CURRENT_SCHEMA=<schema>`,
让不带前缀的表名(subs、prod、e_invoice…)对任何被授权的账号都可见
(否则 ORA-00942)。

## 2. 主项目里的连接链路(对应源码)

```
config_ocs.json ──> core/config.py (AppConfig)      读取 + 解密 enc:v1: 密码
                        │
                        ▼
              connections/db_client.py (OracleClient)   连接 + 自动重连 + CRUD
                        │
        ┌───────────────┼──────────────────┐
        ▼               ▼                  ▼
  query_one()      query_all()         execute()      (services 层只调这三个)
```

- **`core/config.py`** — `AppConfig`:加载 JSON 配置;`db_dsn` 属性拼出
  `host:port/service_name`;`enc:v1:` 前缀的密码经 `core/crypto.py` 解密。
- **`connections/base.py`** — `BaseConnection`:懒持有连接 + `close()`。
- **`connections/db_client.py`** — `OracleClient`:真正干活;
  `CrmOracleClient` 是同一个类绑定 `crm_db` 配置段的变体(CRM 侧库)。

关键代码(主项目 `OracleClient.get_connection`):

```python
self._conn = oracledb.connect(
    user=self._config.db['user'],
    password=self._config.db['password'],   # 已在 AppConfig 里解密
    dsn=self._config.db_dsn                 # "host:port/service_name"
)
cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA={schema}")  # 默认 CC
```

## 3. 套件文件清单

| 文件 | 作用 |
|------|------|
| `oracle_conn_kit/__init__.py` | 包入口,导出 `OracleClient` |
| `oracle_conn_kit/oracle_conn.py` | 全部逻辑:连接/重连/增删查改 + 内置 `enc:v1:` 解密 |
| `oracle_conn_kit/example.py` | 冒烟测试 + 用法示例(`python -m oracle_conn_kit.example`) |
| `oracle_conn_kit/REUSE_GUIDE.md` | 本文档 |

## 4. 给另一个 agent 用:三种姿势

### 姿势 A:直接拷文件夹(最简单)

把 `oracle_conn_kit/` 整个文件夹拷进你的项目,与你的代码同级:

```
your_agent/
├── your_agent.py
└── oracle_conn_kit/
    ├── __init__.py
    ├── oracle_conn.py
    └── example.py
```

```python
from oracle_conn_kit import OracleClient

db = OracleClient.from_config({
    "host": "YOUR_UAT_DB_HOST",
    "port": 1521,
    "service_name": "YOUR_SERVICE",
    "user": "YOUR_USER",
    "password": "YOUR_PASSWORD",   # 明文或 enc:v1: 密文都行
    "schema": "CC",
})

row = db.query_one("SELECT USER FROM DUAL")
rows = db.query_all("SELECT * FROM e_invoice WHERE ROWNUM <= 10")
n = db.execute("UPDATE t SET x = :1 WHERE id = :2", [val, tid])  # 自动 commit
db.close()
```

### 姿势 B:读主工具的配置文件

已有 `config_ocs.json` 的环境,直接复用同一份配置(agent 与工具
共享一套凭据,轮换密码只改一处):

```python
import json
from oracle_conn_kit import OracleClient

with open("config_ocs.json", encoding="utf-8") as f:
    cfg = json.load(f)

db     = OracleClient.from_config(cfg["db"])      # CC 主库
# crm  = OracleClient.from_config(cfg["crm_db"])  # CRM 侧库(如需要)
```

### 姿势 C:环境变量(适合调度器 / 容器 / CI)

```bat
set ORACLE_HOST=YOUR_UAT_DB_HOST
set ORACLE_PORT=1521
set ORACLE_SERVICE=YOUR_SERVICE
set ORACLE_USER=YOUR_USER
set ORACLE_PASSWORD=YOUR_PASSWORD
set ORACLE_SCHEMA=CC
```

```python
from oracle_conn_kit import OracleClient
db = OracleClient.from_env()          # 前缀默认 ORACLE_
```

## 5. 连上之后的 API 一览

| 方法 | 说明 |
|------|------|
| `query_one(sql, params)` | SELECT,返回第一行(元组)或 `None` |
| `query_all(sql, params)` | SELECT,返回所有行(元组列表) |
| `execute(sql, params)` | DML,成功 commit / 失败 rollback,返回行数 |
| `cursor()` | 原始 cursor 逃生口(自己负责 close) |
| `commit()` / `rollback()` | 手动事务 |
| `close()` | 关闭连接(下次取用会自动重连) |
| `with OracleClient(...) as db:` | 上下文管理器:退出时自动 commit(异常则 rollback)并 close |

绑定变量统一用 Oracle 风格 `:1 / :name`,传 list 或 dict:

```python
db.query_all("SELECT * FROM subs WHERE acc_nbr = :1", ["601234567"])
```

## 6. 自动重连的行为(长跑 agent 必读)

- 每次调用 `query_one / query_all / execute / cursor` 都会先 `ping()`;
  ping 失败 → 关闭旧连接 → 重新 `oracledb.connect` → 重设 CURRENT_SCHEMA。
- 所以 **DB 会话超时、防火墙空闲断连** 都不会弄死你的 agent,
  最多那一拍慢一次(重建连接的开销)。
- 例外:`cursor()` 拿到的原始 cursor 在执行中连接断了,oracledb 会抛
  `DPY-xxxx`;捕获后重试一次该操作即可(会自动重连)。

## 7. 密码加密(enc:v1:)说明

- 配置里 `"password": "enc:v1:...."` 会被**透明解密**;明文密码原样可用
  (向后兼容,与主工具一致)。
- 加密是"混淆级"(防截图/转发泄露,不防逆向),算法内置在
  `oracle_conn.py` 的 fallback 里,与主项目 `core/crypto.py` 完全相同。
- 生成密文:在主项目目录跑 `python encrypt_config.py`,或:

  ```python
  from oracle_conn_kit.oracle_conn import encrypt_value
  print(encrypt_value("明文密码"))
  ```

## 8. 冒烟测试(拿到套件先跑这个)

```bat
pip install oracledb
:: 方式一:用主工具的配置
python -m oracle_conn_kit.example --config path\to\config_ocs.json
:: 方式二:环境变量(见姿势 C)后直接
python -m oracle_conn_kit.example
```

预期输出:

```
[OK] connected: Oracle Database 19c Enterprise Edition ...
[OK] SELECT 1 FROM DUAL -> 1
[OK] logged in as: BSS_MS_AI
[OK] CURRENT_SCHEMA: CC
[OK] closed cleanly
```

退出码 0 = 连接正常,1 = 失败并打印原因。

## 9. 常见问题

| 现象 | 原因 / 解法 |
|------|-------------|
| `DPY-3010: unsupported database version` | 目标库太老(Oracle 11g 及以下);thin 模式仅支持 12.1+,老库需改用 thick 模式(装 Oracle Client 后 `oracledb.init_oracle_client()`) |
| `ORA-12541 no listener` | host/port 不对或网络不通;先用 `tnsping` / `telnet host port` 验证 |
| `ORA-01017 invalid username/password` | 账号或密码错;注意密码是否被 enc:v1: 加密过、大小写是否敏感 |
| `ORA-00942 table or view does not exist` | 账号没被 GRANT 该表,或 schema 不对;检查 `schema=` 参数(默认 CC),参考主项目 `grant_bss_ms_ai.sql` |
| 连接慢(每次都重建) | 连接被中间设备频繁掐断;正常现象,重连已自动化 |

## 10. 打包分发

- **源码包**:`oracle_conn_kit_v1.0.zip`(本仓库根目录,含全部 4 个文件)。
- agent 若要打成 exe:PyInstaller 会自动把 `oracledb` 打进去,
  thin 模式**无需**附带 Oracle Client DLL。
- 依赖只有一个:`oracledb>=1.4`(`pip install oracledb`)。
