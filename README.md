# Preprod Telecom Operations Toolkit (Refactored)

Original single-file `Preprod_TestTool.py` (946 lines) refactored into a
layered, object-oriented project. Functionality is 100% identical to the
original tool.

## Project layout

```
preprod tools/
├── main.py                     # entry point
├── config_ocs.json             # runtime config (db / ssh / api)
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

Note: `config_ocs.json` is bundled as a default. At runtime the app prefers a
`config_ocs.json` placed next to the exe, so field engineers can edit
credentials without rebuilding. If it is missing next to the exe, a default
one is created automatically on first launch.

## Config format (config_ocs.json)

```json
{
    "db":   { "host": "...", "port": 11521, "service_name": "cc",
              "user": "cc", "password": "..." },
    "ssh":  { "host": "...", "username": "ocs", "password": "..." },
    "api":  { "base_url": "http://host:7000" }
}
```
