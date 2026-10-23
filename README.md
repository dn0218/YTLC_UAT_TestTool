# Preprod Telecom Operations Toolkit (Refactored)

Original single-file `Preprod_TestTool.py` (946 lines) refactored into a
layered, object-oriented project. Functionality is 100% identical to the
original tool.

## Contributing (开发者必读)

第一次用 GitHub 的开发者,请先阅读手把手协作指南:
**[docs/GITHUB_GUIDE_zh-CN.md](docs/GITHUB_GUIDE_zh-CN.md)**
—— 涵盖环境安装、clone、分支、commit 规范、Pull Request、冲突急救、打包发布全流程。

## Project layout

```
preprod tools/
├── main.py                     # entry point
├── config_ocs.json.example     # config template (copy to config_ocs.json;
│                               #   real config_ocs.json is NOT committed)
├── requirements.txt
├── build.bat                   # one-click exe build
├── build.spec                  # PyInstaller spec
├── core/                       # ── shared foundation ──
│   ├── config.py               #   AppConfig: loads/creates config_ocs.json
│   ├── errors.py               #   typed exceptions
│   └── models.py               #   dataclasses (AccountInfo, BillingCycle, ...)
├── connections/                # ── connection layer ──
│   ├── base.py                 #   BaseConnection
│   ├── db_client.py            #   OracleClient  (oracledb, auto-reconnect)
│   ├── ssh_client.py           #   SSHClient     (paramiko, streaming exec)
│   └── api_client.py           #   JobApiClient  (requests)
├── services/                   # ── business layer (no UI code) ──
│   ├── account_service.py      #   account validation + billing cycles
│   ├── invoice_service.py      #   Core 1: bill run + verification
│   ├── contract_service.py     #   Core 2: contract end date
│   ├── msisdn_service.py       #   Core 3: MSISDN trailing-'0' removal
│   └── sales_invoice_service.py#   Core 4: sales invoice job trigger
└── ui/                         # ── presentation layer ──
    ├── theme.py                #   colors & ttk styles
    ├── widgets.py              #   ConsoleWidget
    ├── threading_bridge.py     #   thread-safe UI calls (logs/dialogs)
    ├── base_tab.py             #   AppContext + BaseTab
    ├── main_window.py          #   MainWindow (notebook, lifecycle)
    └── tabs/                   #   one class per feature tab
        ├── invoice_tab.py
        ├── contract_tab.py
        ├── msisdn_tab.py
        └── sales_invoice_tab.py
```

## Architecture

Three cleanly separated layers:

1. **connections** – opens/closes DB, SSH and HTTP sessions only.
2. **services** – all business logic and SQL; no tkinter imports, unit-testable.
3. **ui** – tkinter rendering, theming and event handling only.

Tabs talk to services through `AppContext`; background threads communicate
with the UI exclusively via `UIThreadBridge` (thread-safe logging and
dialogues), so no widget is touched from a worker thread.

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Build the .exe

```bash
build.bat
```

or manually:

```bash
pyinstaller --noconfirm build.spec
```

Result: `dist\PreprodTestTool\PreprodTestTool.exe` (one-folder build; ship the
whole folder, or switch to `--onefile` by adding a COLLECT-less spec).

Note: `config_ocs.json` is not stored in git (it contains real endpoints and
credentials). When building, PyInstaller bundles the local working copy if
present. At runtime the app prefers a `config_ocs.json` placed next to the
exe, so field engineers can edit credentials without rebuilding. From a
fresh clone, copy `config_ocs.json.example` to `config_ocs.json` and fill in
the real values (ask the maintainer for them).

## Config format (config_ocs.json)

```json
{
    "db":   { "host": "...", "port": 1521, "service_name": "...",
              "user": "...", "password": "..." },
    "ssh":  { "host": "...", "username": "...", "password": "..." },
    "api":  { "base_url": "http://host:7000" }
}
```
