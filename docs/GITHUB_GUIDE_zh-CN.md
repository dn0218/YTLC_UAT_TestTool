# GitHub 协作指南 —— YTLC_UAT_TestTool

> **适用对象**:第一次接触 GitHub / Git 的开发者,Windows 电脑。
> **目标**:读完并照做,你能在 30 分钟内完成"拿代码 → 改代码 → 提交 → 合入主分支"的完整循环。
> **仓库地址**:https://github.com/dn0218/YTLC_UAT_TestTool

---

## 0. 新人上手验收清单(照着打勾)

- [ ] 注册 GitHub 账号,并把用户名告诉管理员(拉你进协作者)
- [ ] 安装 Git for Windows
- [ ] 配置自己的姓名和邮箱(一次性)
- [ ] `git clone` 把代码拉到本地
- [ ] 放好自己的 `config_ocs.json`(不会被提交,验证过)
- [ ] 装依赖,工具能跑起来
- [ ] 完成第一次"分支 → 修改 → 提交 → 推送 → Pull Request"

---

## 1. 一次性准备(只做一次)

### 1.1 注册 GitHub 账号

1. 打开 https://github.com/signup
2. 用公司/常用邮箱注册,用户名建议用真名拼音(如 `zhangsan`),方便管理员认人
3. 注册后把 **GitHub 用户名**发给仓库管理员,让他把你加为 **Collaborator(协作者)**。
   **没被加为协作者之前,你只能看,不能推送代码。**

### 1.2 安装 Git for Windows

1. 下载:https://git-scm.com/download/win
2. 双击安装,**一路默认 Next 即可**(默认自带 Git Credential Manager,后面登录会用到)
3. 验证:按 `Win + R`,输入 `cmd` 回车,在黑窗口输入:

```bat
git --version
```

显示 `git version 2.x.x` 即安装成功。

### 1.3 配置姓名和邮箱(必须,提交记录的署名)

```bat
git config --global user.name  "Zhang San"
git config --global user.email "zhangsan@example.com"
```

> - `user.name` 用真名拼音;`user.email` 用你 **注册 GitHub 用的那个邮箱**,这样提交记录才会关联到你的 GitHub 头像。
> - 这两个配置只影响署名,和登录无关,记不住密码这回事。

### 1.4 第一次连接:登录授权(重点,最容易卡住的地方)

**不需要背密码**。第一次 `git clone` / `git push` 时,会自动弹出浏览器打开 GitHub 授权页:

1. 点 **Sign in with your browser**(如果没有弹出,看终端提示,按回车重试)
2. 浏览器里登录你的 GitHub 账号 → 点 **Authorize**
3. 之后 Windows 会替你记住授权,以后推送不再询问

**如果弹浏览器失败/公司网络受限**,改用 Personal Access Token(PAT)方式:

1. 网页登录 GitHub → 右上角头像 → **Settings** → 左栏最底部 **Developer settings**
2. **Personal access tokens → Tokens (classic) → Generate new token (classic)**
3. Note 随便填(如 `work-laptop`),Expiration 选 `No expiration`,勾选 **`repo`** 这一大项
4. 点 **Generate token**,**立刻复制**页面显示的 `ghp_xxxx`(只显示这一次!)
5. 下次 git 弹出输入密码时:**Username 填 GitHub 用户名,Password 填这个 token**(不是网页登录密码)

---

## 2. 第一次拿到代码

### 2.1 克隆仓库(clone = 把整个项目下载到本地)

选一个放代码的目录,比如 `D:\work`,然后:

```bat
D:
cd \work
git clone https://github.com/dn0218/YTLC_UAT_TestTool.git
cd YTLC_UAT_TestTool
```

完成后 `D:\work\YTLC_UAT_TestTool` 就是你的工作目录,里面有全部源码。

> 💡 建议把这个文件夹**固定到快速访问**。以后所有开发都在这个文件夹里做。

### 2.2 放置本地配置文件(必须)

仓库里**没有** `config_ocs.json`(含真实环境信息,禁止上传)。你需要:

1. 找维护者(或 UAT 环境负责人)要一份真实的 `config_ocs.json`
2. 放到项目根目录(和 `main.py` 同级)
3. **验证它被忽略**(不会被不小心提交):

```bat
git check-ignore config_ocs.json
```

输出 `config_ocs.json` 就说明受保护,放心。

> 没有真实配置时,可先用模板跑通结构:
> ```bat
> copy config_ocs.json.example config_ocs.json
> ```
> 然后编辑里面的 host / user / password。

### 2.3 安装依赖并跑起来

```bat
pip install -r requirements.txt
python main.py
```

能弹出工具界面即环境 OK。(Oracle 连接需要 UAT 网络,连不上不影响后面学 git。)

---

## 3. 日常开发循环(每天都要用的流程)

> 铁律:**永远不直接在 `main` 分支上改代码**。所有修改都在自己的分支上做,通过 Pull Request(PR)审查后合入 `main`。

完整流程一张图:

```
main(公共稳定版)
 │
 ├─ ① git pull                ← 开工前先同步最新
 ├─ ② git checkout -b feature/xxx   ← 开自己的分支
 ├─ ③ 改代码 → 测试
 ├─ ④ git add + git commit    ← 存档(可以多次)
 ├─ ⑤ git push -u origin feature/xxx ← 推到 GitHub
 ├─ ⑥ GitHub 网页上发 Pull Request
 ├─ ⑦ 找人 review → 通过后 Merge
 └─ ⑧ 删分支,git pull 更新本地 main → 开始下一轮
```

### 3.1 每天开工:先同步最新代码

```bat
git checkout main
git pull
```

### 3.2 开一个自己的分支

命名规范:`feature/功能名` 或 `fix/问题名`,用英文短横线:

```bat
git checkout -b feature/invoice-export
```

> 分支就像"平行草稿",你在草稿上乱写都不影响 `main`,满意后再申请合并。

### 3.3 改代码、随时查看改了什么

```bat
git status          :: 看哪些文件动过
git diff            :: 看具体改动内容(按 q 退出)
```

### 3.4 存档:add + commit

```bat
git add ui/tabs/invoice_tab.py      :: 添加指定文件
git add .                           :: 或添加全部改动文件(前提:确认没有垃圾文件,见 5.2)

git commit -m "feat: add CSV export to invoice tab"
```

**Commit message 规范**(英文/中文均可,前缀必须有):

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat:` | 新功能 | `feat: add roaming tab search` |
| `fix:` | 修 bug | `fix: null pointer on empty msisdn` |
| `docs:` | 只改文档 | `docs: update user manual` |
| `refactor:` | 重构不改行为 | `refactor: extract db helper` |
| `chore:` | 构建/配置等杂项 | `chore: bump pyinstaller version` |

一个 commit 只做一件事。写清楚"做了什么",半年后你感谢现在的自己。

### 3.5 第一次推送分支

```bat
git push -u origin feature/invoice-export
```

`-u` 只需第一次带,之后这个分支直接 `git push` 即可。

### 3.6 发 Pull Request(PR = 申请把你的分支合入 main)

1. 推送后,打开仓库网页 https://github.com/dn0218/YTLC_UAT_TestTool
   页面顶部通常会出现黄条 `Compare & pull request`,点它;
   没有就点 **Pull requests → New pull request**,base 选 `main`,compare 选你的分支
2. 标题默认取你最后一个 commit;正文写:**做了什么 / 为什么 / 怎么测的**
3. **Reviewers** 里点选管理员(或指定同事)→ **Create pull request**

### 3.7 Review 与合并

- 审查人在 PR 页面的 **Files changed** 里看代码,可留行内评论
- 有修改意见:回本地继续改 → `git add` → `git commit` → `git push`,**PR 会自动更新**,不用重新建
- 审查通过:审查人点 **Merge pull request → Confirm merge**(推荐 Squash and merge,把零碎 commit 压成一个干净的)
- 合并后点 **Delete branch**(删的是 GitHub 上的分支,安全)

### 3.8 合并后收尾

```bat
git checkout main
git pull
git branch -d feature/invoice-export   :: 删掉本地已合并的分支
```

回到 3.1,开始下一个任务。

---

## 4. 急救手册(出事先来这里)

### 4.1 改乱了,想丢弃所有未提交的修改

```bat
git restore .                        :: 丢弃工作区改动(不可恢复!)
git restore --staged 文件名          :: 只是把误 add 的文件撤出暂存,文件内容保留
```

### 4.2 commit 了但还没 push,想撤销重来

```bat
git reset --soft HEAD~1   :: 撤销 commit,改动保留(回到 add 之后的状态)
```

### 4.3 push 被拒:`! [rejected] ... fetch first`

说明别人在你之前合了新代码,你的分支旧了。同步一下再推:

```bat
git pull --rebase origin main
:: 若提示冲突 → 见 4.4
git push
```

### 4.4 解决冲突(step by step)

冲突 = 你和别人改了同一文件的同一处,git 不知道听谁的。

1. 执行 `git pull --rebase origin main` 后提示 `CONFLICT (content): Merge conflict in xxx.py`
2. 用编辑器(VS Code 最佳)打开该文件,找长这样的段落:

   ```
   <<<<<<< HEAD
   对方(main 上)的代码
   =======
   你的代码
   >>>>>>> feature/invoice-export
   ```

3. **手动编辑成最终想要的样子**(可能保留一方、可能两者融合),把 `<<<<<<<`、`=======`、`>>>>>>>` 三行标记全部删掉
4. 标记完成:

   ```bat
   git add xxx.py
   git rebase --continue
   ```

5. 再 `git push`。实在搞砸了想放弃本次合并:`git rebase --abort`,回到操作前状态。

### 4.5 误删了本地分支 / 找回丢失的 commit

```bat
git reflog                       :: 列出你最近所有操作,每条前面有短 hash
git checkout -b feature/invoice-export abc1234   :: 用 hash 重建分支
```

`reflog` 是 git 的"黑匣子",只要 commit 过,几乎都能找回。

### 4.6 不小心 add 了不该提交的文件(config_ocs.json / zip / backup)

```bat
git restore --staged config_ocs.json     :: 从暂存区撤下(文件还在硬盘上)
git commit -m "..."                      :: 再正常提交其余文件
```

**如果已经 commit 甚至 push 了:立刻停下来,通知管理员处理,不要自己 force push。**

---

## 5. 仓库纪律(违反会被打回 PR)

### 5.1 永远不提交的内容(`.gitignore` 已挡一部分,但你的眼睛是最后一道防线)

| 禁止提交 | 原因 |
|----------|------|
| `config_ocs.json` / `*.plaintext` | 内网地址 + 凭据,泄密事故 |
| `*.zip` / `dist/` / `build/` | 二进制大文件,git 仓库不是网盘 |
| `backup/`、`*_bak*`、临时脚本 | 历史用 git 分支管理,不需要手工备份 |
| `build_log.txt`、日志 | 噪音文件 |
| `.cptr/`、IDE 配置目录 | 个人环境文件 |

### 5.2 提交前 10 秒自检

```bat
git status
```

盯着输出问自己:**列出的每一个文件,都应该进仓库吗?**有疑问就 `git restore --staged` 撤下来。

### 5.3 其他约定

- `main` 分支只接受 PR 合入,不直接 push
- 改了 `.gitignore` / `build.spec` / `requirements.txt` 这类影响所有人的文件,PR 里要 @ 管理员
- 文档(`docs/`)和代码一起改:改了功能必须同步更新 `USER_MANUAL_en.md` / `DEVELOPER_MANUAL_zh-CN.md` 对应章节

---

## 6. 打包与发布(发版负责人操作)

1. 确认要发布的 commit 已合入 `main`,本地已是最新:

   ```bat
   git checkout main
   git pull
   ```

2. 打包:

   ```bat
   build.bat
   :: 产物在 dist\PreprodTestTool\PreprodTestTool.exe
   ```

3. 在 UAT 冒烟测试通过后,打 tag 并推送:

   ```bat
   git tag -a v1.1 -m "Release v1.1: invoice CSV export"
   git push origin v1.1
   ```

4. (可选)GitHub 网页 → **Releases → Draft a new release** → 选择刚打的 tag → 上传 `PreprodTestTool.exe` 压缩包 → Publish。这样现场人员能直接从 Releases 页下载。

> `config_ocs.json` 不进仓库,但**要**随 exe 一起交付给现场(打包已内置一份默认配置,现场也可用 exe 旁的副本覆盖更新)。

---

## 7. 不想敲命令行?GitHub Desktop 速成(可选)

命令行过敏者可用图形界面:https://desktop.github.com

| 命令行 | GitHub Desktop 等价操作 |
|--------|------------------------|
| `git clone` | `File → Clone Repository → URL` |
| `git checkout -b` | 顶部 `Current branch → New branch` |
| `git add` + `commit` | 左侧勾选文件 → 填 summary → `Commit to xxx` |
| `git push` | 顶部 `Push origin` 按钮 |
| `git pull` | 顶部 `Fetch origin` → `Pull origin` |
| 发 PR | 菜单 `Branch → Create pull request` |

GUI 和命令行可以混用,操作的是同一个仓库。**但冲突解决、reset、reflog 等急救场景仍建议回命令行**(第 4 节照样适用)。

---

## 8. FAQ / 常见报错对照表

| 报错 / 现象 | 原因 | 解法 |
|-------------|------|------|
| `Authentication failed` | 密码方式已被 GitHub 停用 | 用浏览器授权(1.4)或 PAT 当密码(1.4 第 5 步) |
| `remote: Permission to dn0218/... denied` | 你还不是协作者 | 把 GitHub 用户名发给管理员加权限 |
| `! [rejected] ... fetch first` | 远端有新提交,本地落后 | `git pull --rebase origin main` 后再 push(4.3) |
| `error: Your local changes ... would be overwritten` | 有未提交的改动挡路了 | 先 `git stash`,pull 完再 `git stash pop` |
| `fatal: not a git repository` | 当前目录不对 | `cd` 到 `YTLC_UAT_TestTool` 文件夹里 |
| 提交记录作者是乱码/错误名字 | 1.3 没配好 | `git config --global user.name/email` 重配 |
| `git log` 卡住不动 | 进入了翻页模式 | 按 `q` 退出 |
| 中文文件名显示成 `\344\270\252` 转义 | Windows 默认 | `git config --global core.quotepath false` |
| 想看某次发布改了什么 | — | 网页 **Commits** 页,或 `git log --oneline` |

---

## 9. 术语速查

| 术语 | 人话解释 |
|------|----------|
| repository (repo) | 仓库,整个项目 + 全部历史 |
| clone | 把仓库完整下载到本地 |
| branch / 分支 | 平行草稿线,`main` 是正式线 |
| commit | 一次存档快照,带说明文字 |
| push / pull | 上传本地存档 / 下载别人存档 |
| origin | 远端仓库(GitHub 上那份)的默认代号 |
| HEAD | 你当前所处的位置 |
| PR (Pull Request) | "我改好了,请审查并合入 main" 的申请单 |
| merge / conflict | 合并分支 / 两边改同一处产生的冲突 |
| .gitignore | 声明哪些文件永远不进仓库的名单 |

---

## 10. 管理员维护手册(仅 dn0218 / 后续负责人)

1. **加协作者**:仓库页 → **Settings → Collaborators → Add people** → 输入对方用户名 → 发邀请;对方在邮箱/网页 Accept 后即有推送权限。
2. **保护 main**:Settings → **Branches → Add branch protection rule** → Branch name pattern 填 `main` → 勾选 **Require a pull request before merging**、**Require 1 approval** → Save。此后没人能直接 push main。
3. **可见性**:当前为 Public(已脱敏)。若要转 Private:Settings → General → 拉到最底部 **Danger Zone → Change visibility**。转 Private 后协作者权限不变,但外部无法再访问。
4. **新人入职流程**:发本文档链接 → 收用户名 → 加 collaborator → 对方完成第 0 节清单 → 在其第一个 PR 上做 review,即完成 git 传帮带。
5. **凭据轮换提醒**:UAT 密码如轮换,只需让各开发者更新本地 `config_ocs.json`(可用 `encrypt_config.py` 加密后互相传递,该文件同样不入库)。

---

*文档版本:v1.0 | 仓库:https://github.com/dn0218/YTLC_UAT_TestTool | 有疑问先查第 8 节 FAQ,再在群里 @ 管理员。*
