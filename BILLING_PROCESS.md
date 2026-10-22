# 出账（Bill Run）全流程 Pseudo Code

> 依据 `Preprod_TestTool.py`（Core 1: Bill Run）真实源码整理。
> 示例：`acct_id = 123456`，账期 `2026-10-13 ~ 2026-11-13`（对应的 `BILLING_CYCLE_ID` 记为 `BC_123`）。

---

## 一、总览

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 0  Check Account   查账户 + 拉出 ±5 个月内的账期列表     │
│  Phase 1  Pre-billing     RecurrRate 预计费（周期性费用落库）   │
│  Phase 2  Bill Run        Brainless_Invoice.sh 正式出账       │
│  Phase 3  Verify          DB 核验发票 + 账单内容 + 收尾         │
└─────────────────────────────────────────────────────────────┘
```

一句话概括：**先确认账户能用、选对账期 → 给每个号码提前算好周期费用（RecurrRate）→ 跑出账脚本生成发票（Brainless_Invoice.sh）→ 回数据库验证发票生成、内容无 NULL、把发票状态推成"已发送"**。

---

## 二、完整 Pseudo Code

```
PROCEDURE BillRun(acct_input):

    # ============ Phase 0: Check Account（表数据检查） ============
    # 目的：确认账户存在、在用、是后付费；找到它的账期类型；列出可选账期

    acct_id ← SQL: SELECT acct_id FROM acct WHERE acct_id   = acct_input
                        UNION
                        SELECT acct_id FROM acct WHERE acct_nbr = acct_input
    IF acct_id 不存在:
        ERROR "No account found."               # 白话：账户不存在，结束

    row ← SQL: SELECT BILLING_CYCLE_TYPE_ID, STATE, POSTPAID
               FROM acct WHERE acct_id = 123456
    IF row.STATE != 'A':
        ERROR "Account is not in use."          # 白话：账户被停/销户，不能出账
    IF row.POSTPAID != 'Y':
        ERROR "Account is not in Postpaid."     # 白话：不是后付费账户，不走出账流程

    cycle_type_id ← row.BILLING_CYCLE_TYPE_ID   # 账期类型（月结/周结…）

    # 拉取该类型下 ±5 个月窗口内的所有账期，按开始时间倒序
    cycles ← SQL: SELECT BILLING_CYCLE_ID,
                         CYCLE_BEGIN_DATE, CYCLE_END_DATE, STATE,
                         (CYCLE_BEGIN_DATE <= SYSDATE <= CYCLE_END_DATE) AS IS_CURRENT
                  FROM BILLING_CYCLE
                  WHERE BILLING_CYCLE_TYPE_ID = cycle_type_id
                    AND CYCLE_END_DATE BETWEEN ADD_MONTHS(SYSDATE,-5)
                                            AND ADD_MONTHS(SYSDATE,+5)
                  ORDER BY CYCLE_BEGIN_DATE DESC
    IF cycles 为空:
        WARN "No matching billing cycles within +/- 5 months."   # 结束

    # 例：列表里出现 "2026-10-13 - 2026-11-13"，若 SYSDATE 落在区间内
    #     则显示为 "[Current] 2026-10-13 - 2026-11-13" 并默认选中
    用户在 ComboBox 中选择账期  →  BC_123, begin = "2026-10-13"
    IF 选中的不是当前账期(IS_CURRENT=0):
        弹窗确认 "该账期不是当前账期，确定继续？"     # 防呆，可强选历史/未来账期

    # ============ Phase 1: Pre-billing（RecurrRate 预计费） ============
    # 目的：把套餐月费之类的周期性费用，按天分摊提前写进 EVENT_RECURRING 表。
    #       Brainless_Invoice.sh 只负责"汇总开票"，费用行必须先存在！

    SSH 连接出账服务器

    # 1) 找到账户下所有订阅（号码）
    subs_ids ← SQL: SELECT s.subs_id
                    FROM subs s JOIN acct a ON s.acct_id = a.acct_id
                    WHERE s.acct_id = 123456
                    ORDER BY s.subs_id
    IF subs_ids 为空:
        WARN "账户下没有号码，跳过预计费" → 直接进 Phase 2

    # 2) 跳过检查：已有预计费行的号码不重复跑
    #    判据：EVENT_BEGIN_TIME 是整点零分（TRUNC(t) = t）。
    #    （RecurrRate 用 -d 日期参数写入的行是零点整；
    #     开户补收的行带真实时间戳，不会被误判。
    #     ACCT_ITEM_TYPE_ID1 不可靠：同一号码不同账期出现过 12 和 4311。）
    FOR EACH subs_id IN subs_ids:
        cnt ← SQL: SELECT COUNT(*) FROM EVENT_RECURRING_BC_123@link_rb
                   WHERE SUBS_ID = subs_id
                     AND TRUNC(EVENT_BEGIN_TIME) = EVENT_BEGIN_TIME
        IF cnt > 0:  标记 subs_id 为 already（跳过）
        ELSE:        标记 subs_id 为 need_precharge
    IF 全部 already:
        LOG "全部号码已有预计费，跳过 RecurrRate" → 进 Phase 2

    # 3) 解析 RecurrRate 可执行文件的绝对路径
    #    （exec_command 不是登录 shell，PATH 里没有它，必须先 which）
    path ← SSH: bash -lc 'which RecurrRate'
    IF 找不到: 依次试 ~/bin/RecurrRate、~/invoicing/bin/RecurrRate
    IF 还是找不到:
        ERROR "could not locate RecurrRate" → ABORT（不出账）

    # 4) 逐个号码执行 RecurrRate（必须用 bash -lc 登录 shell，
    #    让 ~/.bash_profile 提供 PATH 和 LD_LIBRARY_PATH）
    #    -t 账期类型  -d 账期开始日(yyyymmdd)  -e 1 期数  -s 号码  -l 5 日志级别
    FOR EACH subs_id IN need_precharge:
        SSH: bash -lc 'cd invoicing/ && <path>/RecurrRate
                        -t <cycle_type_id> -T -d 20261013 -e 1 -s <subs_id> -l 5'
        只记录 "Program RecurrRate begin/end" 两行标记（输出太啰嗦）
        IF 退出码 != 0: WARN（继续跑下一个号码，不中断）

    SLEEP 10 秒                                   # 等费用行落库

    # 5) 校验：每个刚跑的号码都必须在 EVENT_RECURRING 里出现整点行
    FOR EACH subs_id IN need_precharge:
        cnt ← SQL: 同第 2) 步的 COUNT 查询
        IF cnt > 0: verified ✓
        ELSE:       failed ✗
    IF failed 非空:
        ERROR "Pre-billing verification failed"   # 白话：预计费没生成，
        ABORT — 不执行 Brainless_Invoice.sh        #       强行出账会缺费用，
                                                  #       宁可不出！
    # —— 只有全部 verified 才允许进入 Phase 2 ——

    # ============ Phase 2: Bill Run（正式出账） ============
    # Brainless_Invoice.sh：汇总费用 → 生成 invoice / e_invoice /
    #                       bill_data_<cycle> 账单内容 → 触发下游 job

    SSH: cd invoicing/ && ./Brainless_Invoice.sh BC_123 123456
    实时读取输出流，只显示关键行:
        "Step 1..." / "Step 2..." / "Step 3..."
        "Start Call..." / "...successWait 10 seconds for job running..."

    SSH 断开
    LOG "Bill Run Done! 开始核验……"

    # ============ Phase 3: Verify（出账后核验） ============
    SLEEP 30 秒                                   # 等出账链路跑完

    DB_CONN ← 连接核心库

    # --- 核验 1: 电子发票已生成（最多重试 5 次，间隔 10 秒）---
    e_invoice_nbr ← NULL
    FOR attempt IN 1..5:
        row ← SQL: SELECT E_INVOICE_NBR FROM e_invoice
                   WHERE acct_id = 123456 AND billing_cycle_id = BC_123
        IF row 有值: e_invoice_nbr ← row; BREAK
        SLEEP 10
    IF e_invoice_nbr 仍为空:
        WARN "5 次都没取到 E_INVOICE_NBR，继续做账单内容校验"

    # --- 收尾 1: 把发票"已发送时间"回拨到昨天，让发送 job 能捞起它 ---
    IF e_invoice_nbr 存在:
        SQL: UPDATE e_invoice SET SEND_DATE = SYSDATE - 1
             WHERE acct_id = 123456 AND billing_cycle_id = BC_123
        COMMIT
        LOG "Invoice <nbr> status updated in DB."

    # --- 核验 2: 账单内容（BLOB 里的 XML）---
    bill_row ← SQL: SELECT ACCT_ID, BILLING_CYCLE_ID, BILL_CONTENT
                    FROM bill_data_BC_123@link_rb          # 按账期分表！
                    WHERE ACCT_ID = 123456
    IF bill_row 不存在:
        WARN "bill_data 表里没有该账户的账单" → 结束

    xml ← 解码 BILL_CONTENT (BLOB → UTF-8 → 美化缩进)

    # --- 核验 3: XML 里不允许出现 "null" 字样（大小写不敏感）---
    IF "null" 出现在 xml 中:
        WARN + 展示美化后的 XML
        IF 用户选择重跑:
            递归调用 BillRun(BC_123)               # 再走一遍全流程
        ELSE:
            LOG "用户忽略 NULL 告警"
    ELSE:
        SUCCESS "发票 <nbr> 生成且内容校验通过！"      # ✅ 出账完成

    恢复按钮可用
END PROCEDURE
```

---

## 三、白话走一遍（acct_id=123456，账期 2026-10-13 ~ 2026-11-13）

### 第 0 步：检查账户（点 Check Account）

白话：你输入 123456，工具先去 `acct` 表问"这个账户存在吗？状态是 A（在用）吗？是后付费（POSTPAID='Y'）吗？"三个条件缺一不可——账户都不在了当然没法出账，预付费用户也不走这套出账。

过了之后，工具拿着这个账户的**账期类型**（比如"月结"），去 `BILLING_CYCLE` 表把这个类型下、结束日期在前后 5 个月内的所有账期都拉出来，倒序排好，让下拉框里选。假设今天在 10-13 到 11-13 之间，那这条会标着 **[Current]** 并被默认选中。如果你故意选了一个不是当前的账期，工具会再问你一次"确定？"，防止误操作。

选中后记下两个关键值：`BILLING_CYCLE_ID`（假设是 BC_123，后面到处都用它）和账期开始日 `2026-10-13`。

### 第 1 步：预计费（RecurrRate）—— 出账前的"备菜"

白话：出账脚本 `Brainless_Invoice.sh` 只是个"汇总开票员"，它自己不算钱。像包月套餐费这种**周期性费用**必须先由 `RecurrRate` 算好，一行行写进 `EVENT_RECURRING_BC_123` 表（注意：这个表是**按账期分表**的，通过 `@link_rb` db link 访问另一个库）。

工具先查出 123456 名下所有号码（`subs` 表 join `acct`）。然后做个聪明的跳过检查：**已经是"零点整"的费用行就不再跑**。为什么看零点？因为 RecurrRate 写入的时间来自 `-d 20261013` 这种日期参数，落库就是 00:00:00 整；而开户补收那种杂费带真实时分秒。之前想用费用类型（type=12）来判断，结果发现同一号码不同账期类型会变（见过 12 也见过 4311），不靠谱，所以只用"整点"这一个铁判据。

需要跑的号码，工具会逐个在 SSH 服务器上执行：

```
RecurrRate -t <账期类型> -T -d 20261013 -e 1 -s <号码> -l 5
```

两个细节：一是必须用 `bash -lc`（登录 shell）跑，否则 PATH 和 LD_LIBRARY_PATH 不全，程序起不来；二是可执行文件路径先用 `which` 解析成绝对路径再拼命令。跑完睡 10 秒等落库，然后**逐个号码复查**：每个号码在 EVENT_RECURRING 表里必须有整点行。**只要有任何一个号码没生成，立即中止，绝不碰 Brainless_Invoice.sh**——宁可不出账，也不出一张缺费用的账单。

### 第 2 步：正式出账（Brainless_Invoice.sh）

白话：所有号码的费用行都验证齐了，工具才在 SSH 上执行：

```
cd invoicing/ && ./Brainless_Invoice.sh BC_123 123456
```

这个脚本干的就是出账本体：把费用汇总、算税、生成 invoice 和电子发票记录、把账单 XML 写进 `bill_data_BC_123` 表（也是按账期分表），最后触发下游 job。工具实时盯着输出流，只把 "Step 1/2/3"、"Start Call" 这类关键节点打到界面上。

### 第 3 步：核验（等 30 秒再查库）

白话：脚本跑完不等于成功，要回数据库验证三件事：

1. **电子发票生成了没？** 查 `e_invoice` 表拿 `E_INVOICE_NBR`，查不到就等 10 秒再查，最多 5 次。
2. **把发票推进发送队列。** 拿到发票号后，顺手 `UPDATE e_invoice SET SEND_DATE = SYSDATE-1`——把发送时间回拨到昨天，这样发送 job 下次扫描时就会把它当成"该发未发"捞出去，模拟整条链路。
3. **账单内容干净吗？** 去 `bill_data_BC_123@link_rb` 把 `BILL_CONTENT`（BLOB）读出来，解码成 XML 美化展示，然后全文搜 "null"（不分大小写）。有 null 说明账单里有字段没填上（比如地址、税号缺失），工具会弹窗问你要不要**重跑整条流程**；没有 null 就报成功——到这里出账就全部完成了。

### 涉及的表速查

| 表 | 作用 |
|---|---|
| `acct` | 账户存在性、状态、后付费标志、账期类型 |
| `BILLING_CYCLE` | 账期定义（起止日期、是否当前账期） |
| `subs` | 账户下的号码（订阅） |
| `EVENT_RECURRING_<cycle>@link_rb` | RecurrRate 写的周期费用行（按账期分表） |
| `e_invoice` | 电子发票记录（取号、回拨 SEND_DATE） |
| `bill_data_<cycle>@link_rb` | 账单 XML 内容（按账期分表，校验 NULL） |
