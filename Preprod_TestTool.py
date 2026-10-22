import os
import sys
import json
import time
import threading
import xml.dom.minidom
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import oracledb
import paramiko
import requests
from redis.cluster import RedisCluster, ClusterNode

# ==================== Config value encryption (obfuscation grade) ====================
import base64 as _b64
import hashlib as _hl
import hmac as _hmac

_ENC_PREFIX = "enc:v1:"
_ENC_K1 = bytes.fromhex("5f2a7c91e4b08d36a1f4c5e29b7d3a88")
_ENC_K2 = bytes.fromhex("6d1e9f4a2c8b7e5d0a3f6c9b1e8d4a72")
_ENC_KEY = _hl.sha256(_ENC_K1 + bytes([0x50]) + _ENC_K2).digest()


def _enc_keystream(nonce, length):
    out = b""
    counter = 0
    while len(out) < length:
        out += _hmac.new(_ENC_KEY, nonce + counter.to_bytes(4, "big"), _hl.sha256).digest()
        counter += 1
    return out[:length]


def _enc_xor(data, ks):
    return bytes(a ^ b for a, b in zip(data, ks))


def encrypt_value(plaintext):
    """Encrypt a password string into 'enc:v1:<base64>' form."""
    nonce = _hl.sha256(plaintext.encode("utf-8")).digest()[:8]
    data = plaintext.encode("utf-8")
    ct = _enc_xor(data, _enc_keystream(nonce, len(data)))
    tag = _hmac.new(_ENC_KEY, nonce + ct, _hl.sha256).digest()[:8]
    return _ENC_PREFIX + _b64.b64encode(nonce + ct + tag).decode("ascii")


def decrypt_value(value):
    """Decrypt 'enc:v1:...' back to plaintext; plain strings pass through."""
    if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value
    try:
        raw = _b64.b64decode(value[len(_ENC_PREFIX):])
        nonce, ct, tag = raw[:8], raw[8:-8], raw[-8:]
        expected = _hmac.new(_ENC_KEY, nonce + ct, _hl.sha256).digest()[:8]
        if not _hmac.compare_digest(tag, expected):
            raise ValueError("integrity check failed")
        return _enc_xor(ct, _enc_keystream(nonce, len(ct))).decode("utf-8")
    except Exception as e:
        raise ValueError(f"cannot decrypt config value: {e}") from e
# ===================================================================


# ==================== SIM Tool Config ====================
# Only rows with this attr_code are shown in Tab 5 (others hidden)
ATTR_FILTER_CODE = "EXP_SIM_PRODUCT_TYPE"


class TelecomOpsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Telecom Operations Toolkit")
        self.geometry("1020x780")
        self.minsize(900, 700)

        # Application state
        self.config = {}
        self.db_conn = None
        self.crm_conn = None
        self._redis_client = None

        # State variables for Core 1
        self.core1_acct_id = None
        self.core1_cycle_type_id = None
        self.core1_run_begin_date = None
        self.core1_billing_cycles = {}  # Label -> dict(id, is_current, begin)
        self.core1_current_cycle_label = None

        # State variables for Core 4
        self.t4_acct_id = None
        self.t4_is_postpaid = False
        self.t4_billing_cycles = {}

        # Initialize Config & Styling
        self.load_config()
        self._apply_theme()

        # Build UI
        self._build_ui()

    # ==========================================
    # THEME & STYLING
    # ==========================================
    def _apply_theme(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")  # Use flat flexible base theme

        # Define Color Palette
        PRIMARY = "#0056b3"
        PRIMARY_HOVER = "#004085"
        SUCCESS = "#28a745"
        BACKGROUND = "#f8f9fa"
        SURFACE = "#ffffff"
        TEXT_MAIN = "#212529"
        TEXT_MUTED = "#6c757d"

        self.configure(bg=BACKGROUND)

        # Style Configurations
        self.style.configure(".", background=BACKGROUND, foreground=TEXT_MAIN, font=("Segoe UI", 10))

        # Notebook / Tabs
        self.style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#e9ecef", foreground=TEXT_MAIN, padding=[16, 8], font=("Segoe UI", 10, "bold"))
        self.style.map("TNotebook.Tab",
                       background=[("selected", SURFACE), ("active", "#dee2e6")],
                       foreground=[("selected", PRIMARY)])

        # LabelFrame
        self.style.configure("TLabelframe", background=SURFACE, relief="solid", borderwidth=1, bordercolor="#dee2e6", padding=12)
        self.style.configure("TLabelframe.Label", background=SURFACE, foreground=PRIMARY, font=("Segoe UI", 10, "bold"))

        # Buttons
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=[12, 6], background=PRIMARY, foreground="white")
        self.style.map("TButton",
                       background=[("disabled", "#e9ecef"), ("active", PRIMARY_HOVER)],
                       foreground=[("disabled", "#adb5bd")])

        self.style.configure("Success.TButton", background=SUCCESS, foreground="white")
        self.style.map("Success.TButton", background=[("active", "#218838")])

        # Entries & Comboboxes
        self.style.configure("TEntry", padding=6)
        self.style.configure("TCombobox", padding=6)

        # Labels
        self.style.configure("TLabel", background=SURFACE, foreground=TEXT_MAIN)
        self.style.configure("Muted.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=("Segoe UI", 9, "italic"))

    # ==========================================
    # CONFIG & DB MANAGEMENT
    # ==========================================
    def get_resource_path(self, relative_path):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

    def load_config(self):
        config_path = self.get_resource_path('config_ocs.json')
        if not os.path.exists(config_path):
            # No real credentials are shipped in the source. Copy
            # config_ocs.json.example -> config_ocs.json and fill it in.
            example_path = os.path.join(os.path.dirname(config_path) or '.',
                                        'config_ocs.json.example')
            if os.path.exists(example_path):
                import shutil
                shutil.copyfile(example_path, config_path)
                messagebox.showinfo(
                    "Config",
                    "config_ocs.json created from config_ocs.json.example.\n"
                    "Edit it with real credentials and restart.")
            else:
                messagebox.showerror(
                    "Config",
                    "config_ocs.json not found and no "
                    "config_ocs.json.example available.\n"
                    "Ask the maintainer for a config file.")
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Transparently decrypt 'enc:v1:...' password values (plain values untouched)
        for section in ("db", "ssh", "crm_db"):
            if isinstance(self.config.get(section), dict) and "password" in self.config[section]:
                self.config[section]["password"] = decrypt_value(self.config[section]["password"])
        if isinstance(self.config.get("redis"), dict) and "password" in self.config["redis"]:
            self.config["redis"]["password"] = decrypt_value(self.config["redis"]["password"])

        # Backward compatibility: older config files lack the 'crm_db' / 'redis' sections
        if "crm_db" not in self.config:
            self.config["crm_db"] = {
                "host": self.config.get("db", {}).get("host", ""),
                "port": self.config.get("db", {}).get("port", 1521),
                "service_name": self.config.get("db", {}).get("service_name", ""),
                "user": "crm",
                "password": self.config.get("db", {}).get("password", "")
            }
        if "redis" not in self.config:
            self.config["redis"] = {
                "nodes": [],
                "password": None
            }

    def get_db_connection(self):
        try:
            if self.db_conn is not None:
                self.db_conn.ping()
                return self.db_conn
        except Exception:
            self.db_conn = None

        try:
            dsn = f"{self.config['db']['host']}:{self.config['db']['port']}/{self.config['db']['service_name']}"
            self.db_conn = oracledb.connect(
                user=self.config['db']['user'],
                password=self.config['db']['password'],
                dsn=dsn
            )
            # Bare table names (subs, acct, ...) live in the CC schema. When the
            # login user is not the schema owner (e.g. bss_ms_ai), name
            # resolution fails with ORA-00942 - point the session at CC.
            schema = (self.config['db'].get('schema') or 'CC').upper()
            cur = self.db_conn.cursor()
            try:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA={schema}")
            finally:
                cur.close()
            return self.db_conn
        except Exception as e:
            messagebox.showerror("DB Error", f"Database connection failed: {e}")
            return None

    def _get_redis_client(self):
        """Lazily create and reuse a single RedisCluster client."""
        if self._redis_client is not None:
            return self._redis_client

        redis_conf = self.config.get("redis", {})
        nodes = [ClusterNode(host, int(port))
                 for host, port in redis_conf.get("nodes", [])]
        self._redis_client = RedisCluster(
            startup_nodes=nodes,
            password=redis_conf.get("password") or None,
            decode_responses=True,
            socket_timeout=5
        )
        return self._redis_client

    def _invalidate_subs_cache(self, subs_id):
        """Best-effort deletion of the subscription cache key.

        Returns (True, key) on success, (False, error_message) on failure.
        Never raises - cache failure must not fail the DB update.
        """
        key = f"DUMP_SUBS_CACHE/ADAPTER_QRY_SUBS_INFO/{subs_id}"
        try:
            client = self._get_redis_client()
            reply = client.unlink(key)
            if reply:
                return True, f"{key} (redis UNLINK replied {reply}: cache entry deleted)"
            return True, (f"{key} (redis UNLINK replied 0: "
                          f"key was already absent, nothing to delete)")
        except Exception as e:
            self._redis_client = None  # force a fresh connection next time
            return False, str(e)

    def _bg(self, job, on_done):
        """Run job() in a daemon thread, marshal the result back to the UI thread.

        Exceptions are wrapped as ("__error__", str(e)); on_done always runs
        on the main Tk thread, so it may touch widgets / messagebox safely.
        """
        def wrapper():
            try:
                result = job()
            except Exception as e:
                result = ("__error__", str(e))
            self.after(0, lambda: on_done(result))
        threading.Thread(target=wrapper, daemon=True).start()

    def _get_crm_connection(self):
        """Lazily create/reuse the CRM connection (base64 config, like sim_tool).

        Raises on failure - callers wrap it in _bg(job, on_done).
        """
        if self.crm_conn is not None:
            try:
                self.crm_conn.ping()
                return self.crm_conn
            except Exception:
                self.crm_conn = None
        crm = self.config["crm_db"]
        dsn = f"{crm['host']}:{crm['port']}/{crm['service_name']}"
        self.crm_conn = oracledb.connect(user=crm['user'], password=crm['password'], dsn=dsn)
        # Same CURRENT_SCHEMA fix as get_db_connection (ORA-00942 for bare
        # names when the login user is not the schema owner).
        schema = (crm.get('schema') or 'CC').upper()
        cur = self.crm_conn.cursor()
        try:
            cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA={schema}")
        finally:
            cur.close()
        return self.crm_conn

    def trigger_curl(self, job_name, params):
        # URL-encode the params value: it contains '|' and other reserved
        # characters. The job server decodes URL-encoded values, and an
        # unencoded '|' can be truncated/mangled by intermediate layers.
        from urllib.parse import quote
        encoded_params = quote(params, safe="")
        url = f"{self.config['api']['base_url']}/jobservermgr/api/triggerJob"
        full_url = f"{url}?jobName={job_name}&jobGroup=InvoiceManagement&params={encoded_params}"
        self._t4_log(f"Triggering API: {full_url}")
        self._t4_log(f"Raw params (unencoded): {params}")
        try:
            response = requests.post(full_url, timeout=30)
            self._t4_log(f"API response status: {response.status_code}, body: {response.text}")
            response.raise_for_status()
            return response
        except Exception as e:
            self._t4_log(f"API call failed: {e}")
            raise

    # ==========================================
    # UI INITIALIZATION
    # ==========================================
    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        tab1 = ttk.Frame(notebook, padding=10)
        notebook.add(tab1, text="Invoice Generation")
        self._setup_tab1(tab1)

        tab2 = ttk.Frame(notebook, padding=10)
        notebook.add(tab2, text="Contract End Date")
        self._setup_tab2(tab2)

        tab3 = ttk.Frame(notebook, padding=10)
        notebook.add(tab3, text="MSISDN Clean '0'")
        self._setup_tab3(tab3)

        tab4 = ttk.Frame(notebook, padding=10)
        notebook.add(tab4, text="Sales Invoice")
        self._setup_tab4(tab4)

        tab5 = ttk.Frame(notebook, padding=10)
        notebook.add(tab5, text="SIM Card Attribute")
        self._setup_tab5(tab5)

        tab6 = ttk.Frame(notebook, padding=10)
        notebook.add(tab6, text="Roaming Subscription Pass")
        self._setup_tab6(tab6)

    def _create_console(self, parent):
        """Helper to create dark-terminal styled scrolled text."""
        console = scrolledtext.ScrolledText(
            parent,
            state="disabled",
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            font=("Consolas", 9),
            relief="flat",
            borderwidth=0
        )
        return console

    # ==========================================
    # CORE 1: INVOICE GENERATION
    # ==========================================
    def _setup_tab1(self, parent):
        frame_top = ttk.LabelFrame(parent, text=" Account & Cycle Selection ")
        frame_top.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame_top, text="Account ID / Number:").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        self.t1_acct_entry = ttk.Entry(frame_top, width=32)
        self.t1_acct_entry.grid(row=0, column=1, padx=8, pady=8, sticky=tk.W)

        self.t1_btn_check = ttk.Button(frame_top, text="Check Account", command=self._t1_check_account)
        self.t1_btn_check.grid(row=0, column=2, padx=8, pady=8, sticky=tk.W)

        ttk.Label(frame_top, text="Pick Billing Cycle:").grid(row=1, column=0, padx=8, pady=8, sticky=tk.W)
        self.t1_cycle_combo = ttk.Combobox(frame_top, width=30, state="disabled")
        self.t1_cycle_combo.grid(row=1, column=1, padx=8, pady=8, sticky=tk.W)

        self.t1_btn_run = ttk.Button(frame_top, text="Run Bill & Generate Invoice", state="disabled", command=self._t1_run_bill_thread, style="Success.TButton")
        self.t1_btn_run.grid(row=1, column=2, padx=8, pady=8, sticky=tk.W)

        self.t1_lbl_current_cycle = ttk.Label(frame_top, text="Current cycle: N/A", style="Muted.TLabel")
        self.t1_lbl_current_cycle.grid(row=1, column=3, padx=12, pady=8, sticky=tk.W)

        frame_log = ttk.LabelFrame(parent, text=" Bill Run Progress & Console ")
        frame_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)

        self.t1_log = self._create_console(frame_log)
        self.t1_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _t1_log(self, text):
        self.t1_log.config(state="normal")
        self.t1_log.insert(tk.END, text + "\n")
        self.t1_log.see(tk.END)
        self.t1_log.config(state="disabled")

    def _t1_check_account(self):
        user_acct = self.t1_acct_entry.get().strip()
        if not user_acct:
            messagebox.showwarning("Input Error", "Please enter an Account ID or Account Number.")
            return

        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor()
        try:
            cursor.execute("SELECT acct_id FROM acct WHERE acct_id = :1", [user_acct])
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT acct_id FROM acct WHERE acct_nbr = :1", [user_acct])
                row = cursor.fetchone()

            if not row:
                messagebox.showerror("Error", "No account found.")
                return

            self.core1_acct_id = str(row[0])

            cursor.execute("SELECT BILLING_CYCLE_TYPE_ID, STATE, POSTPAID FROM acct WHERE acct_id = :1", [self.core1_acct_id])
            val_row = cursor.fetchone()
            if not val_row:
                messagebox.showerror("Error", "Account details not found.")
                return

            cycle_type_id, state, postpaid = val_row[0], val_row[1], val_row[2]
            self.core1_cycle_type_id = cycle_type_id

            if state != 'A':
                messagebox.showerror("Error", "Account is not in use.")
                return
            if postpaid != 'Y':
                messagebox.showerror("Error", "Account is not in Postpaid.")
                return

            query = """
                SELECT BILLING_CYCLE_TYPE_ID, BILLING_CYCLE_ID, 
                       TO_CHAR(CYCLE_BEGIN_DATE, 'YYYY-MM-DD') AS BEGIN_DATE_STR, 
                       TO_CHAR(CYCLE_END_DATE, 'YYYY-MM-DD') AS END_DATE_STR, 
                       STATE,
                       CASE WHEN CYCLE_BEGIN_DATE <= SYSDATE AND SYSDATE <= CYCLE_END_DATE THEN 1 ELSE 0 END AS IS_CURRENT
                FROM BILLING_CYCLE 
                WHERE BILLING_CYCLE_TYPE_ID = :1
                  AND CYCLE_END_DATE >= ADD_MONTHS(SYSDATE, -5)
                  AND CYCLE_END_DATE <= ADD_MONTHS(SYSDATE, 5)
                ORDER BY CYCLE_BEGIN_DATE DESC
            """
            cursor.execute(query, [cycle_type_id])
            cycles = cursor.fetchall()

            if not cycles:
                messagebox.showwarning("Warning", "No matching billing cycles found within +/- 5 months window.")
                return

            self.core1_billing_cycles.clear()
            self.core1_current_cycle_label = None
            combo_values = []
            default_index = 0

            for idx, c in enumerate(cycles):
                b_id, b_start, b_end, is_current = c[1], c[2], c[3], c[5]
                period_str = f"{b_start} - {b_end}"

                if is_current == 1:
                    display_str = f"[Current] {period_str}"
                    self.core1_current_cycle_label = display_str
                    self.t1_lbl_current_cycle.config(text=f"Current cycle: {period_str}")
                    default_index = idx
                else:
                    display_str = period_str

                self.core1_billing_cycles[display_str] = {
                    "id": b_id,
                    "is_current": (is_current == 1),
                    "period": period_str,
                    "begin": b_start
                }
                combo_values.append(display_str)

            if not self.core1_current_cycle_label:
                self.t1_lbl_current_cycle.config(text="Current cycle: None in range")

            self.t1_cycle_combo['values'] = combo_values
            self.t1_cycle_combo.current(default_index)
            self.t1_cycle_combo.config(state="readonly")
            self.t1_btn_run.config(state="normal")

            self._t1_log(f"Account validated successfully. ID: {self.core1_acct_id}. Found {len(combo_values)} billing cycles.")

        except Exception as e:
            messagebox.showerror("Database Query Error", str(e))
        finally:
            cursor.close()

    def _t1_run_bill_thread(self):
        selected_label = self.t1_cycle_combo.get()
        if not selected_label or selected_label not in self.core1_billing_cycles:
            messagebox.showwarning("Selection Error", "Please select a valid billing cycle.")
            return

        cycle_data = self.core1_billing_cycles[selected_label]

        if not cycle_data["is_current"]:
            confirm = messagebox.askyesno(
                "Billing Cycle Warning",
                f"The selected cycle ({cycle_data['period']}) is NOT the current billing cycle.\n\n"
                "Are you sure you want to proceed with this bill run?",
                icon="warning"
            )
            if not confirm:
                return

        billing_cycle_id = cycle_data["id"]
        self.core1_run_begin_date = cycle_data.get("begin")
        self.t1_btn_run.config(state="disabled")
        self.t1_btn_check.config(state="disabled")

        threading.Thread(target=self._t1_execute_bill_run, args=(billing_cycle_id,), daemon=True).start()

    def _t1_run_prebilling(self, ssh, bill_run_cycle_id):
        """Run RecurrRate pre-charges for every subs under this account, then verify.

        Steps (per requirement):
          1. Query subs_id list from subs JOIN acct for the current account.
          2. For each subs_id run: RecurrRate -t <CYCLE_TYPE> -T -d <yyyymmdd> -e 1 -s <SUBS_ID> -l 5
          3. sleep 10 seconds.
          4. Verify rows exist in EVENT_RECURRING_<cycle>@link2rb for each subs_id.
        Returns True when ALL subs verified; False aborts the bill run.
        """
        acct_id = self.core1_acct_id
        cycle_type_id = self.core1_cycle_type_id
        begin_date = self.core1_run_begin_date

        if not acct_id or cycle_type_id is None or not begin_date:
            self._t1_log("WARNING: missing account/cycle info; skipping pre-billing step.")
            return True

        yyyymmdd = begin_date.replace("-", "")
        self._t1_log(f"\n--- Pre-billing: querying subscriptions under account {acct_id} ---")

        # 1) SUBS_ID list (subs JOIN acct)
        subs_ids = []
        conn = self.get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """SELECT s.subs_id
                         FROM subs s JOIN acct a ON s.acct_id = a.acct_id
                        WHERE s.acct_id = :1
                        ORDER BY s.subs_id""",
                    [acct_id]
                )
                subs_ids = [str(r[0]) for r in cursor.fetchall()]
            except Exception as e:
                self._t1_log(f"WARNING: failed to query subs list ({e}); skipping pre-billing step.")
                return True
            finally:
                cursor.close()

        if not subs_ids:
            self._t1_log(f"WARNING: no subscriptions found under account {acct_id}; "
                         "skipping pre-billing step.")
            return True

        # 1b) Skip check: subs that already have RecurrRate pre-charge rows do
        #     not need pre-billing again. RecurrRate writes rows whose
        #     EVENT_BEGIN_TIME is a whole day (TRUNC = midnight, derived from
        #     the -d argument). Account-opening supplementary charges carry a
        #     real (non-midnight) timestamp. NOTE: ACCT_ITEM_TYPE_ID1 of
        #     RecurrRate rows is NOT fixed (observed 12 on one cycle, 4311 on
        #     another), so only the truncated-time test is reliable.
        event_table = f"EVENT_RECURRING_{bill_run_cycle_id}@link2rb"
        already, need_precharge = [], []
        conn = self.get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                for subs_id in subs_ids:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {event_table} "
                        f"WHERE SUBS_ID = :1 "
                        f"AND TRUNC(EVENT_BEGIN_TIME) = EVENT_BEGIN_TIME",
                        [subs_id]
                    )
                    cnt = cursor.fetchone()[0]
                    if cnt and cnt > 0:
                        already.append(subs_id)
                        self._t1_log(f"SUBS_ID {subs_id} already pre-charged "
                                     f"({cnt} RecurrRate row(s) with whole-day "
                                     f"EVENT_BEGIN_TIME), skip RecurrRate.")
                    else:
                        need_precharge.append(subs_id)
            except Exception as e:
                self._t1_log(f"WARNING: pre-charge skip check failed ({e}); "
                             "will run RecurrRate for all subs.")
                need_precharge = list(subs_ids)
            finally:
                cursor.close()

        if not need_precharge:
            self._t1_log(f"All {len(already)} subscription(s) already pre-charged. "
                         "Skipping RecurrRate, proceeding to Brainless_Invoice.sh ...")
            return True

        # 2) RecurrRate per subs_id
        # Resolve the RecurrRate executable path.
        # Interactive SSH works because a LOGIN shell loads ~/.bash_profile
        # (its PATH contains the bin dir). exec_command is NOT a login shell,
        # so resolve the absolute path via `bash -lc which` first, falling
        # back to common bin/ locations.
        recurr_rate_path = None
        ld_library_path = None
        try:
            stdin, stdout, stderr = ssh.exec_command(
                "bash -lc 'which RecurrRate; echo LD_LIBRARY_PATH=$LD_LIBRARY_PATH'",
                get_pty=True)
            stdout.channel.recv_exit_status()
            out = stdout.read().decode('utf-8', errors='ignore')
            for ln in out.splitlines():
                ln = ln.strip()
                if ln.startswith("/") and ln.endswith("RecurrRate"):
                    recurr_rate_path = ln
                elif ln.startswith("LD_LIBRARY_PATH="):
                    ld_library_path = ln.split("=", 1)[1]
        except Exception:
            recurr_rate_path = None

        if not recurr_rate_path:
            for cand in ("~/bin/RecurrRate", "~/invoicing/bin/RecurrRate"):
                try:
                    stdin, stdout, stderr = ssh.exec_command(
                        f"ls -l {cand}", get_pty=True)
                    st = stdout.channel.recv_exit_status()
                    out = stdout.read().decode('utf-8', errors='ignore').strip()
                    if st == 0 and "No such file" not in out:
                        recurr_rate_path = cand
                        break
                except Exception:
                    continue

        if not recurr_rate_path:
            self._t1_log("ERROR: could not locate RecurrRate on the SSH host "
                         "(tried login-shell PATH, ~/bin/, ~/invoicing/bin/). "
                         "Please check where the binary lives.")
            return False
        self._t1_log(f"RecurrRate executable resolved: {recurr_rate_path} "
                     f"(LD_LIBRARY_PATH={ld_library_path or 'not set'})")

        for subs_id in need_precharge:
            # Run inside a LOGIN shell so ~/.bash_profile provides the full OCS
            # environment (PATH + LD_LIBRARY_PATH for liboffline_*.so) - exactly
            # like an interactive SSH session.
            cmd = (f"bash -lc 'cd invoicing/ && {recurr_rate_path} -t {cycle_type_id} "
                   f"-T -d {yyyymmdd} -e 1 -s {subs_id} -l 5'")
            self._t1_log(f"Executing: {cmd}")
            try:
                stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
                exit_status = stdout.channel.recv_exit_status()
                output = stdout.read().decode('utf-8', errors='ignore')

                # RecurrRate is very verbose - keep only the begin/end markers.
                for ln in output.splitlines():
                    ln = ln.strip()
                    if "Program RecurrRate begin" in ln or "Program RecurrRate end" in ln:
                        self._t1_log(ln)

                if exit_status != 0:
                    tail = "\n".join(output.strip().splitlines()[-15:])
                    self._t1_log(f"WARNING: RecurrRate for SUBS_ID {subs_id} exited with "
                                 f"status {exit_status}. Last output lines:\n{tail}")
            except Exception as e:
                self._t1_log(f"WARNING: RecurrRate execution failed for SUBS_ID {subs_id}: {e}")

        # 3) sleep 10 seconds (only needed when RecurrRate actually ran)
        self._t1_log("Waiting 10 seconds for recurring events to persist...")
        time.sleep(10)

        # 4) Verify EVENT_RECURRING_<cycle>@link2rb has pre-charge rows
        #    (whole-day EVENT_BEGIN_TIME) for every subs we just pre-charged.
        verified = []
        failed = []
        conn = self.get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                for subs_id in need_precharge:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {event_table} "
                        f"WHERE SUBS_ID = :1 "
                        f"AND TRUNC(EVENT_BEGIN_TIME) = EVENT_BEGIN_TIME",
                        [subs_id]
                    )
                    cnt = cursor.fetchone()[0]
                    if cnt and cnt > 0:
                        verified.append(subs_id)
                        self._t1_log(f"Pre-billing verified: {cnt} row(s) in {event_table} "
                                     f"for SUBS_ID {subs_id}.")
                    else:
                        failed.append(subs_id)
                        self._t1_log(f"WARNING: no rows in {event_table} for SUBS_ID {subs_id}.")
            except Exception as e:
                self._t1_log(f"WARNING: EVENT_RECURRING verification query failed: {e}.")
                return False
            finally:
                cursor.close()

        if failed:
            self._t1_log(f"Pre-billing verification FAILED for SUBS_ID(s): {', '.join(failed)}")
            return False

        self._t1_log(f"Pre-billing OK for all {len(verified)} subscription(s). "
                     "Proceeding to Brainless_Invoice.sh ...")
        return True

    def _t1_execute_bill_run(self, bill_run_cycle_id):
        self._t1_log(f"\n--- Starting Bill Run for Account {self.core1_acct_id}, Cycle {bill_run_cycle_id} ---")

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=self.config['ssh']['host'],
                username=self.config['ssh']['username'],
                password=self.config['ssh']['password'],
                timeout=10
            )

            cmd = f"cd invoicing/ && ./Brainless_Invoice.sh {bill_run_cycle_id} {self.core1_acct_id}"

            # ---------- Pre-billing: recurring-rate pre-charges (RecurrRate) ----------
            precheck_ok = self._t1_run_prebilling(ssh, bill_run_cycle_id)
            if not precheck_ok:
                ssh.close()
                self._t1_log("Bill Run ABORTED: recurring-event pre-billing verification failed "
                             "(no rows in EVENT_RECURRING table). Brainless_Invoice.sh was NOT executed.")
                messagebox.showerror(
                    "Pre-billing Failed",
                    "Recurring-rate pre-charge verification failed.\n\n"
                    "No rows found in EVENT_RECURRING_<cycle>@link2rb for this account's "
                    "subscription(s) after running RecurrRate.\n\n"
                    "Brainless_Invoice.sh was NOT executed."
                )
                return

            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)

            for line in iter(stdout.readline, ""):
                clean_line = line.strip()
                if any(clean_line.startswith(prefix) for prefix in ["Step 1", "Step 2", "Step 3", "Start Call"]) or \
                        "successWait 10 seconds for job running" in clean_line:
                    self._t1_log(clean_line)

            ssh.close()
            self._t1_log("Bill Run Done! Proceeding to verify invoice records and content...")

            self._t1_log("Waiting 30 seconds before checking database records...")
            time.sleep(30)

            conn = self.get_db_connection()
            e_invoice_nbr = None

            if conn:
                cursor = conn.cursor()

                # Step 1: E-Invoice Generation Check
                query_sql = "SELECT E_INVOICE_NBR FROM e_invoice WHERE acct_id=:1 AND billing_cycle_id=:2"
                max_attempts = 5
                for attempt in range(1, max_attempts + 1):
                    self._t1_log(f"Attempt {attempt}/{max_attempts} to fetch E_INVOICE_NBR...")
                    cursor.execute(query_sql, [self.core1_acct_id, bill_run_cycle_id])
                    row = cursor.fetchone()

                    if row and row[0]:
                        e_invoice_nbr = row[0]
                        break

                    if attempt < max_attempts:
                        # e_invoice generation is async and slow - 15 s between
                        # attempts (was 10 s; rows only showed up after the
                        # tool had given up).
                        time.sleep(15)

                if e_invoice_nbr:
                    cursor.execute(
                        "UPDATE e_invoice SET SEND_DATE=sysdate-1 WHERE acct_id=:1 AND billing_cycle_id=:2",
                        [self.core1_acct_id, bill_run_cycle_id]
                    )
                    conn.commit()
                    self._t1_log(f"Invoice <{e_invoice_nbr}> status updated in DB.")
                else:
                    self._t1_log("WARNING: Failed to retrieve E_INVOICE_NBR after 5 attempts. Proceeding to bill data validation.")

                # Step 2: Bill Content BLOB Validation
                bill_table = f"bill_data_{bill_run_cycle_id}@link2rb"
                bill_query = f"SELECT ACCT_ID, BILLING_CYCLE_ID, BILL_CONTENT FROM {bill_table} WHERE ACCT_ID = :1"

                self._t1_log(f"Checking bill data in table {bill_table}...")
                cursor.execute(bill_query, [self.core1_acct_id])
                bill_row = cursor.fetchone()

                if not bill_row:
                    self._t1_log(f"WARNING: No bill data record found in {bill_table} for ACCT_ID {self.core1_acct_id}.")
                    messagebox.showwarning("Bill Data Missing", f"No record found in {bill_table} for account {self.core1_acct_id}.")
                    return

                # Read BLOB data
                blob_data = bill_row[2]
                raw_xml = blob_data.read() if hasattr(blob_data, 'read') else blob_data

                if isinstance(raw_xml, bytes):
                    raw_xml = raw_xml.decode('utf-8', errors='ignore')

                # Beautify XML content
                try:
                    dom = xml.dom.minidom.parseString(raw_xml)
                    beautified_xml = dom.toprettyxml(indent="  ")
                except Exception:
                    beautified_xml = raw_xml

                # Case-insensitive NULL check
                has_null = "null" in raw_xml.lower()

                if has_null:
                    self._t1_log("\n[!] WARNING: 'NULL' value detected in BILL_CONTENT XML:")
                    self._t1_log("--------------------------------------------------")
                    self._t1_log(beautified_xml)
                    self._t1_log("--------------------------------------------------")

                    rerun = messagebox.askyesno(
                        "Null Value Detected",
                        f"Invoice generated (<{e_invoice_nbr if e_invoice_nbr else 'N/A'}>), but 'NULL' content was found inside the BILL_CONTENT XML.\n\n"
                        "Would you like to rerun the bill generation?"
                    )

                    if rerun:
                        self._t1_log("User initiated bill rerun. Restarting execution...")
                        cursor.close()
                        self._t1_execute_bill_run(bill_run_cycle_id)
                        return
                    else:
                        self._t1_log("User chose to skip rerun despite NULL detection.")
                else:
                    self._t1_log("SUCCESS: BILL_CONTENT verified. No NULL values found.")
                    messagebox.showinfo("Success", f"Invoice <{e_invoice_nbr}> successfully generated and verified!")

                cursor.close()

        except Exception as e:
            self._t1_log(f"Error during execution: {e}")
            messagebox.showerror("Execution Error", str(e))
        finally:
            self.t1_btn_check.config(state="normal")
            self.t1_btn_run.config(state="normal")

    # ==========================================
    # CORE 2: CONTRACT END DATE
    # ==========================================
    def _setup_tab2(self, parent):
        frame = ttk.LabelFrame(parent, text=" Manage Contract / Subscription ")
        frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame, text="MSISDN:").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        self.t2_msisdn_entry = ttk.Entry(frame, width=32)
        self.t2_msisdn_entry.grid(row=0, column=1, padx=8, pady=8, sticky=tk.W)

        self.t2_btn_check_status = ttk.Button(frame, text="Check Agreement Status", command=self._t2_check_agreement_status)
        self.t2_btn_check_status.grid(row=0, column=2, padx=8, pady=8, sticky=tk.W)

        ttk.Label(frame, text="Expiry Date (YYYY-MM-DD):").grid(row=1, column=0, padx=8, pady=8, sticky=tk.W)
        self.t2_date_entry = ttk.Entry(frame, width=32)
        self.t2_date_entry.grid(row=1, column=1, padx=8, pady=8, sticky=tk.W)

        self.t2_btn_update = ttk.Button(frame, text="Update Expiry Date", command=self._t2_update_date)
        self.t2_btn_update.grid(row=1, column=2, padx=8, pady=8, sticky=tk.W)

        self.t2_btn_deactivate = ttk.Button(frame, text="Deactivate Contract", command=self._t2_deactivate)
        self.t2_btn_deactivate.grid(row=1, column=3, padx=8, pady=8, sticky=tk.W)

        frame_log = ttk.LabelFrame(parent, text=" Operations Console ")
        frame_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)

        self.t2_log = self._create_console(frame_log)
        self.t2_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _t2_log(self, text):
        self.t2_log.config(state="normal")
        self.t2_log.insert(tk.END, text + "\n")
        self.t2_log.see(tk.END)
        self.t2_log.config(state="disabled")

    def _t2_validate_and_get_records(self, msisdn):
        conn = self.get_db_connection()
        if not conn:
            return None, None

        cursor = conn.cursor()
        try:
            sql1 = """
                SELECT p.PROD_ID, p.PROD_STATE, 
                       TO_CHAR(p.AGREEMENT_EFF_DATE, 'YYYY-MM-DD HH24:MI:SS') AS EFF_DATE, 
                       TO_CHAR(p.AGREEMENT_EXP_DATE, 'YYYY-MM-DD HH24:MI:SS') AS EXP_DATE, 
                       p.AGREEMENT_ID 
                FROM subs s 
                JOIN prod p ON s.subs_id = p.prod_id 
                WHERE s.ACC_NBR = :1
            """
            cursor.execute(sql1, [msisdn])
            p_row = cursor.fetchone()
            if not p_row:
                messagebox.showerror("Error", f"No record found for MSISDN: {msisdn}")
                return None, None

            prod_id, prod_state, p_eff, p_exp, agreement_id = p_row

            sql2 = """
                SELECT SA.INST_ID, 
                       TO_CHAR(SA.EFF_DATE, 'YYYY-MM-DD HH24:MI:SS') AS SA_EFF, 
                       SA.STATE, 
                       SA.AGREEMENT_NAME 
                FROM subs_agreement_inst SA 
                WHERE SA.INST_ID = :1 AND SA.AGREEMENT_ID = :2
            """
            cursor.execute(sql2, [prod_id, agreement_id])
            sa_row = cursor.fetchone()

            if prod_state != 'A':
                self._t2_log(f"WARNING: MSISDN {msisdn} is not active (State={prod_state}), OK to proceed update.")

            if sa_row:
                sa_state, sa_name = sa_row[2], sa_row[3]
                if sa_state != 'A':
                    self._t2_log(f"WARNING: <{sa_name}> is not active (State={sa_state}), OK to proceed update.")

            return p_row, sa_row
        except Exception as e:
            messagebox.showerror("Query Error", str(e))
            return None, None
        finally:
            cursor.close()

    def _t2_check_agreement_status(self):
        msisdn = self.t2_msisdn_entry.get().strip()
        if not msisdn:
            messagebox.showwarning("Input Error", "Please enter MSISDN.")
            return

        p_row, sa_row = self._t2_validate_and_get_records(msisdn)
        if not p_row:
            return

        p_eff, p_exp = p_row[2], p_row[3]
        sa_name = sa_row[3] if sa_row and sa_row[3] else "N/A"

        self._t2_log(f"\n--- Agreement Status for MSISDN: {msisdn} ---")
        self._t2_log(f"Agreement Name          : {sa_name}")
        self._t2_log(f"Agreement Effective Date: {p_eff if p_eff else 'N/A'}")
        self._t2_log(f"Agreement Expiry Date   : {p_exp if p_exp else 'N/A'}")

    def _t2_update_date(self):
        msisdn = self.t2_msisdn_entry.get().strip()
        user_exp_date = self.t2_date_entry.get().strip()

        if not msisdn or not user_exp_date:
            messagebox.showwarning("Input Error", "Please provide MSISDN and target Expiry Date.")
            return

        p_row, sa_row = self._t2_validate_and_get_records(msisdn)
        if not p_row:
            return

        prod_id, agreement_id = p_row[0], p_row[4]
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            try:
                sql_p = "UPDATE prod SET AGREEMENT_EXP_DATE = TO_DATE(:1, 'YYYY-MM-DD') WHERE prod_id = :2"
                sql_sa = "UPDATE subs_agreement_inst SET EFF_DATE = TO_DATE(:1, 'YYYY-MM-DD') WHERE INST_ID = :2 AND AGREEMENT_ID = :3"
                sql_cc = "UPDATE cc.subs_agreement_inst SET EXP_DATE = TO_DATE(:1, 'YYYY-MM-DD') WHERE INST_ID = :2 AND AGREEMENT_ID = :3"
                cursor.execute(sql_p, [user_exp_date, prod_id])
                cursor.execute(sql_sa, [user_exp_date, prod_id, agreement_id])
                cursor.execute(sql_cc, [user_exp_date, prod_id, agreement_id])
            except Exception:
                sql_p = "UPDATE prod SET AGREEMENT_EXP_DATE = TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI:SS') WHERE prod_id = :2"
                sql_sa = "UPDATE subs_agreement_inst SET EFF_DATE = TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI:SS') WHERE INST_ID = :2 AND AGREEMENT_ID = :3"
                sql_cc = "UPDATE cc.subs_agreement_inst SET EXP_DATE = TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI:SS') WHERE INST_ID = :2 AND AGREEMENT_ID = :3"
                cursor.execute(sql_p, [user_exp_date, prod_id])
                cursor.execute(sql_sa, [user_exp_date, prod_id, agreement_id])
                cursor.execute(sql_cc, [user_exp_date, prod_id, agreement_id])

            conn.commit()

            # Invalidate the Redis cache AFTER a successful DB commit.
            # SUBS_ID == p_row[0] (PROD_ID) in this business model.
            cache_ok, cache_detail = self._invalidate_subs_cache(p_row[0])

            self._t2_log(f"SUCCESS: Contract end date updated to {user_exp_date} for MSISDN: {msisdn}")

            if cache_ok:
                self._t2_log(f"Cache invalidated: {cache_detail}")
                messagebox.showinfo("Success", "Contract end date updated successfully.")
            else:
                self._t2_log(f"WARNING: Failed to invalidate Redis cache for SUBS_ID <{p_row[0]}>: {cache_detail}")
                messagebox.showinfo(
                    "Success",
                    "Contract end date updated successfully.\n"
                    "(Warning: cache invalidation failed, please check Redis.)"
                )
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Update Error", str(e))
        finally:
            cursor.close()

    def _t2_deactivate(self):
        msisdn = self.t2_msisdn_entry.get().strip()
        if not msisdn:
            messagebox.showwarning("Input Error", "Please enter MSISDN.")
            return

        p_row, sa_row = self._t2_validate_and_get_records(msisdn)
        if not p_row:
            return

        prod_id, agreement_id = p_row[0], p_row[4]
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("UPDATE prod SET AGREEMENT_EXP_DATE = sysdate-1 WHERE prod_id = :1", [prod_id])
            cursor.execute("UPDATE subs_agreement_inst SET EFF_DATE = sysdate-1 WHERE INST_ID = :1 AND AGREEMENT_ID = :2", [prod_id, agreement_id])
            cursor.execute("UPDATE cc.subs_agreement_inst SET EXP_DATE = sysdate-1 WHERE INST_ID = :1 AND AGREEMENT_ID = :2", [prod_id, agreement_id])
            conn.commit()

            # Invalidate the Redis cache AFTER a successful DB commit.
            # SUBS_ID == p_row[0] (PROD_ID) in this business model.
            cache_ok, cache_detail = self._invalidate_subs_cache(p_row[0])

            sysdate_minus_1_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            self._t2_log(f"SUCCESS: Deactivated contract ({sysdate_minus_1_str}) for MSISDN: {msisdn}")

            if cache_ok:
                self._t2_log(f"Cache invalidated: {cache_detail}")
                messagebox.showinfo("Success", "Contract deactivated successfully.")
            else:
                self._t2_log(f"WARNING: Failed to invalidate Redis cache for SUBS_ID <{p_row[0]}>: {cache_detail}")
                messagebox.showinfo(
                    "Success",
                    "Contract deactivated successfully.\n"
                    "(Warning: cache invalidation failed, please check Redis.)"
                )
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Deactivation Error", str(e))
        finally:
            cursor.close()

    # ==========================================
    # CORE 3: REMOVE LAST '0' FROM MSISDN
    # ==========================================
    def _setup_tab3(self, parent):
        frame = ttk.LabelFrame(parent, text=" Remove Trailing Zero from MSISDN ")
        frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame, text="MSISDN:").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        self.t3_msisdn_entry = ttk.Entry(frame, width=32)
        self.t3_msisdn_entry.grid(row=0, column=1, padx=8, pady=8, sticky=tk.W)

        self.t3_btn_val = ttk.Button(frame, text="Validate MSISDN", command=self._t3_validate)
        self.t3_btn_val.grid(row=0, column=2, padx=8, pady=8)

        self.t3_btn_remove = ttk.Button(frame, text="Remove Last '0'", state="disabled", command=self._t3_remove_zero, style="Success.TButton")
        self.t3_btn_remove.grid(row=0, column=3, padx=8, pady=8)

        frame_info = ttk.LabelFrame(parent, text=" Account & Customer Details ")
        frame_info.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)

        self.t3_info_text = self._create_console(frame_info)
        self.t3_info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.t3_data = {}

    def _t3_display_info(self, text, clear=False):
        self.t3_info_text.config(state="normal")
        if clear:
            self.t3_info_text.delete('1.0', tk.END)
        self.t3_info_text.insert(tk.END, text + "\n")
        self.t3_info_text.config(state="disabled")

    def _t3_validate(self):
        msisdn = self.t3_msisdn_entry.get().strip()
        if not msisdn:
            messagebox.showwarning("Input Error", "Please enter an MSISDN.")
            return

        if not msisdn.endswith('0'):
            messagebox.showwarning("Validation Warning", f"MSISDN '{msisdn}' does NOT end with '0'.")
            self.t3_btn_remove.config(state="disabled")
            return

        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor()
        try:
            cursor.execute("SELECT ACC_NBR, ACCT_ID, CUST_ID FROM subs WHERE acc_nbr = :1", [msisdn])
            subs_row = cursor.fetchone()
            if not subs_row:
                messagebox.showerror("Error", f"No record found in 'subs' for MSISDN {msisdn}")
                return

            acct_id, cust_id = subs_row[1], subs_row[2]

            cursor.execute("SELECT ACCT_NAME, ACCT_NBR FROM acct WHERE ACCT_ID = :1", [acct_id])
            acct_row = cursor.fetchone()

            cursor.execute("SELECT CUST_NAME, CUST_CODE FROM cust WHERE cust_id = :1", [cust_id])
            cust_row = cursor.fetchone()

            cursor.execute("SELECT ACC_NBR_ID FROM crm.acc_nbr WHERE ACC_NBR = :1", [msisdn])
            crm_row = cursor.fetchone()

            acc_nbr_id = crm_row[0] if crm_row else None

            new_msisdn = msisdn[:-1]
            self.t3_data = {
                "user_msisdn": msisdn,
                "new_msisdn": new_msisdn,
                "acc_nbr_id": acc_nbr_id
            }

            info = f"--- MSISDN Validation Passed ---\n"
            info += f"Original MSISDN  : {msisdn}\n"
            info += f"New Target MSISDN: {new_msisdn}\n\n"
            info += f"Account Name     : {acct_row[0] if acct_row else 'N/A'}\n"
            info += f"Account Number   : {acct_row[1] if acct_row else 'N/A'}\n"
            info += f"Customer Name    : {cust_row[0] if cust_row else 'N/A'}\n"
            info += f"Customer Number  : {cust_row[1] if cust_row else 'N/A'}\n"
            info += f"CRM ACC_NBR_ID   : {acc_nbr_id if acc_nbr_id else 'Not Found'}\n"

            self._t3_display_info(info, clear=True)
            self.t3_btn_remove.config(state="normal")

        except Exception as e:
            messagebox.showerror("Query Error", str(e))
        finally:
            cursor.close()

    def _t3_remove_zero(self):
        if not self.t3_data:
            return

        user_msisdn = self.t3_data["user_msisdn"]
        new_msisdn = self.t3_data["new_msisdn"]
        acc_nbr_id = self.t3_data["acc_nbr_id"]

        confirm = messagebox.askyesno("Confirm", f"Are you sure you want to change MSISDN from {user_msisdn} to {new_msisdn}?")
        if not confirm:
            return

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("UPDATE subs SET acc_nbr = :1 WHERE acc_nbr = :2", [new_msisdn, user_msisdn])

            if acc_nbr_id:
                cursor.execute("UPDATE crm.acc_nbr SET acc_nbr = :1 WHERE acc_nbr = :2 AND ACC_NBR_ID = :3", [new_msisdn, user_msisdn, acc_nbr_id])
            else:
                cursor.execute("UPDATE crm.acc_nbr SET acc_nbr = :1 WHERE acc_nbr = :2", [new_msisdn, user_msisdn])

            if acc_nbr_id:
                cursor.execute("UPDATE cc.acc_nbr SET acc_nbr = :1 WHERE acc_nbr = :2 AND ACC_NBR_ID = :3", [new_msisdn, user_msisdn, acc_nbr_id])
            else:
                cursor.execute("UPDATE cc.acc_nbr SET acc_nbr = :1 WHERE acc_nbr = :2", [new_msisdn, user_msisdn])

            conn.commit()

            self._t3_display_info(f"\nSUCCESS: Updated MSISDN from '{user_msisdn}' to '{new_msisdn}' across all target tables.")
            messagebox.showinfo("Success", f"MSISDN updated successfully to {new_msisdn}")
            self.t3_btn_remove.config(state="disabled")

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Update Error", str(e))
        finally:
            cursor.close()

    # ==========================================
    # CORE 4: SALES INVOICE
    # ==========================================
    def _setup_tab4(self, parent):
        frame_top = ttk.LabelFrame(parent, text=" Account & Invoice Type ")
        frame_top.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame_top, text="Account ID / Number:").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        self.t4_acct_entry = ttk.Entry(frame_top, width=32)
        self.t4_acct_entry.grid(row=0, column=1, padx=8, pady=8, sticky=tk.W)

        self.t4_btn_check = ttk.Button(frame_top, text="Check Account", command=self._t4_check_account)
        self.t4_btn_check.grid(row=0, column=2, padx=8, pady=8, sticky=tk.W)

        self.t4_lbl_type = ttk.Label(frame_top, text="Type: N/A", font=("Segoe UI", 9, "bold"))
        self.t4_lbl_type.grid(row=0, column=3, padx=12, pady=8, sticky=tk.W)

        ttk.Label(frame_top, text="Billing Cycle:").grid(row=1, column=0, padx=8, pady=8, sticky=tk.W)
        self.t4_cycle_combo = ttk.Combobox(frame_top, width=30, state="disabled")
        self.t4_cycle_combo.grid(row=1, column=1, padx=8, pady=8, sticky=tk.W)

        self.t4_btn_trigger = ttk.Button(frame_top, text="Trigger Sales Invoice", state="disabled", command=self._t4_trigger_sales_invoice_thread, style="Success.TButton")
        self.t4_btn_trigger.grid(row=1, column=2, padx=8, pady=8, sticky=tk.W)

        frame_log = ttk.LabelFrame(parent, text=" Sales Invoice Console ")
        frame_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)

        self.t4_log = self._create_console(frame_log)
        self.t4_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _t4_log(self, text):
        self.t4_log.config(state="normal")
        self.t4_log.insert(tk.END, text + "\n")
        self.t4_log.see(tk.END)
        self.t4_log.config(state="disabled")

    def _t4_check_account(self):
        user_acct = self.t4_acct_entry.get().strip()
        if not user_acct:
            messagebox.showwarning("Input Error", "Please enter an Account ID or Account Number.")
            return

        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor()
        try:
            cursor.execute("SELECT acct_id FROM acct WHERE acct_id = :1", [user_acct])
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT acct_id FROM acct WHERE acct_nbr = :1", [user_acct])
                row = cursor.fetchone()

            if not row:
                messagebox.showerror("Error", "No account found.")
                return

            self.t4_acct_id = str(row[0])

            cursor.execute("SELECT BILLING_CYCLE_TYPE_ID, STATE, POSTPAID FROM acct WHERE acct_id = :1", [self.t4_acct_id])
            val_row = cursor.fetchone()
            if not val_row:
                messagebox.showerror("Error", "Account details not found.")
                return

            cycle_type_id, state, postpaid = val_row[0], val_row[1], val_row[2]

            if state != 'A':
                messagebox.showerror("Error", "Account is not active.")
                return

            if postpaid == 'Y':
                self.t4_is_postpaid = True
                self.t4_lbl_type.config(text="Type: POSTPAID", foreground="#0056b3")

                query = """
                    SELECT BILLING_CYCLE_TYPE_ID, BILLING_CYCLE_ID, 
                           TO_CHAR(CYCLE_BEGIN_DATE, 'YYYY-MM-DD') AS BEGIN_DATE_STR, 
                           TO_CHAR(CYCLE_END_DATE, 'YYYY-MM-DD') AS END_DATE_STR, 
                           CASE WHEN CYCLE_BEGIN_DATE <= SYSDATE AND SYSDATE <= CYCLE_END_DATE THEN 1 ELSE 0 END AS IS_CURRENT
                    FROM BILLING_CYCLE 
                    WHERE BILLING_CYCLE_TYPE_ID = :1
                      AND CYCLE_END_DATE >= ADD_MONTHS(SYSDATE, -5)
                      AND CYCLE_END_DATE <= ADD_MONTHS(SYSDATE, 5)
                    ORDER BY CYCLE_BEGIN_DATE DESC
                """
                cursor.execute(query, [cycle_type_id])
                cycles = cursor.fetchall()

                if not cycles:
                    messagebox.showwarning("Warning", "No matching billing cycles found within +/- 5 months window.")
                    return

                self.t4_billing_cycles.clear()
                combo_values = []
                default_index = 0

                for idx, c in enumerate(cycles):
                    b_id, b_start, b_end, is_current = c[1], c[2], c[3], c[4]
                    period_str = f"{b_start} - {b_end}"
                    display_str = f"[Current] {period_str}" if is_current == 1 else period_str

                    if is_current == 1:
                        default_index = idx

                    self.t4_billing_cycles[display_str] = b_id
                    combo_values.append(display_str)

                self.t4_cycle_combo['values'] = combo_values
                self.t4_cycle_combo.current(default_index)
                self.t4_cycle_combo.config(state="readonly")

            else:
                self.t4_is_postpaid = False
                self.t4_lbl_type.config(text="Type: PREPAID", foreground="#28a745")
                self.t4_cycle_combo.set("N/A (Prepaid Account)")
                self.t4_cycle_combo.config(state="disabled")

            self.t4_btn_trigger.config(state="normal")
            account_type = "Postpaid" if self.t4_is_postpaid else "Prepaid"
            self._t4_log(f"Account {self.t4_acct_id} validated as {account_type}.")

        except Exception as e:
            messagebox.showerror("Database Query Error", str(e))
        finally:
            cursor.close()

    def _t4_trigger_sales_invoice_thread(self):
        self.t4_btn_trigger.config(state="disabled")
        self.t4_btn_check.config(state="disabled")

        threading.Thread(target=self._t4_execute_sales_invoice, daemon=True).start()

    def _t4_execute_sales_invoice(self):
        try:
            current_date = datetime.now().strftime("%Y-%m-%d")

            if self.t4_is_postpaid:
                job_name = "PostpaidSalesEInvoiceGenerate"
                params = f"POSTPAID_SALES_E_INVOICE,SRC_SUBS_EVENT_ID=1|SP_ID=101|QRY_DATE={current_date}"
            else:
                job_name = "PrepaidSalesEInvoiceGenerate"
                params = f"PREPAID_SALES_E_INVOICE,SP_ID=101|QRY_DATE={current_date}"

            self._t4_log(f"\n--- Initiating Sales Invoice Trigger ({'Postpaid' if self.t4_is_postpaid else 'Prepaid'}) ---")
            self._t4_log(f"Job Name  : {job_name}")
            self._t4_log(f"Parameters: {params}")

            response = self.trigger_curl(job_name, params)

            if response.status_code == 200:
                self._t4_log("SUCCESS: Sales Invoice API triggered successfully.")
                # Allow the sales invoice to be re-processed: move SEND_DATE
                # back one day on this account's sales-type e_invoice rows
                # (identified by BILLING_CYCLE_ID IS NULL - billing invoices
                # always carry a cycle id, sales ones do not).
                try:
                    conn = self.get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        try:
                            cursor.execute(
                                "UPDATE e_invoice SET SEND_DATE = sysdate-1 "
                                "WHERE ACCT_ID = :1 AND BILLING_CYCLE_ID IS NULL",
                                [self.t4_acct_id]
                            )
                            updated = cursor.rowcount
                            conn.commit()
                            self._t4_log(f"SEND_DATE updated (sysdate-1) on {updated} "
                                         f"sales-type e_invoice row(s) for account "
                                         f"{self.t4_acct_id}.")
                        finally:
                            cursor.close()
                except Exception as e:
                    self._t4_log(f"WARNING: failed to update SEND_DATE for account "
                                 f"{self.t4_acct_id}: {e}")
                messagebox.showinfo("Success", f"Sales Invoice job '{job_name}' triggered successfully!")
            else:
                self._t4_log(f"WARNING: API responded with status {response.status_code}")
                messagebox.showwarning("API Warning", f"Job triggered with non-200 status: {response.status_code}")

        except Exception as e:
            self._t4_log(f"ERROR: Failed to trigger Sales Invoice API: {e}")
            messagebox.showerror("Execution Error", f"Failed to trigger job: {e}")
        finally:
            self.t4_btn_check.config(state="normal")
            self.t4_btn_trigger.config(state="normal")

    # ==========================================
    # TAB 5: SIM CARD ATTRIBUTE
    # ==========================================
    def _setup_tab5(self, parent):
        top = ttk.LabelFrame(parent, text=" ICCID Query ")
        top.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top, text="ICCID:").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        self.t5_iccid_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.t5_iccid_var, width=34, font=("Consolas", 11))
        e.grid(row=0, column=1, padx=8, pady=8, sticky=tk.W)
        e.bind("<Return>", lambda ev: self._t5_query())
        self.t5_btn_query = ttk.Button(top, text="Query", command=self._t5_query, state="disabled")
        self.t5_btn_query.grid(row=0, column=2, padx=8, pady=8)

        self.t5_status_var = tk.StringVar(value="Connecting to database...")
        ttk.Label(top, textvariable=self.t5_status_var, foreground="#1677ff").grid(
            row=0, column=3, padx=12, pady=8, sticky=tk.W)

        info = ttk.LabelFrame(parent, text=" Card Info ")
        info.pack(fill=tk.X, padx=5, pady=5)
        self.t5_info_var = tk.StringVar(value="(Waiting for database connection...)")
        ttk.Label(info, textvariable=self.t5_info_var, justify=tk.LEFT).pack(anchor=tk.W, padx=4, pady=4)

        attrf = ttk.LabelFrame(
            parent,
            text=" Attributes (only %s, double-click a row to edit) " % ATTR_FILTER_CODE)
        attrf.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        cols = ("no", "code", "name", "value")
        self.t5_tree = ttk.Treeview(attrf, columns=cols, show="headings", height=8)
        for cid, text, w, an in (("no", "No.", 50, "center"),
                                 ("code", "ATTR_CODE", 150, "w"),
                                 ("name", "ATTR_NAME", 150, "w"),
                                 ("value", "ATTR_VALUE", 330, "w")):
            self.t5_tree.heading(cid, text=text)
            self.t5_tree.column(cid, width=w, anchor=an)
        self.t5_tree.bind("<Double-1>", lambda ev: self._t5_open_edit())
        vsb = ttk.Scrollbar(attrf, orient="vertical", command=self.t5_tree.yview)
        self.t5_tree.config(yscrollcommand=vsb.set)
        self.t5_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.LEFT, fill=tk.Y)

        btnbar = ttk.Frame(parent)
        btnbar.pack(fill=tk.X, padx=5, pady=(0, 4))
        self.t5_btn_edit = ttk.Button(btnbar, text="Edit Selected", command=self._t5_open_edit, state="disabled")
        self.t5_btn_edit.pack(side=tk.LEFT)
        self.t5_btn_refresh = ttk.Button(btnbar, text="Refresh", command=self._t5_query, state="disabled")
        self.t5_btn_refresh.pack(side=tk.LEFT, padx=6)

        logf = ttk.LabelFrame(parent, text=" Operation Log ")
        logf.pack(fill=tk.BOTH, padx=5, pady=(4, 8))
        self.t5_log = self._create_console(logf)
        self.t5_log.configure(height=6)
        self.t5_log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # State
        self.t5_attrs = []
        self.t5_card = {}

        # Auto-connect in the background (does not block the UI)
        self.after(100, self._t5_connect)

    def _t5_log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        self.t5_log.config(state="normal")
        self.t5_log.insert("1.0", "[%s] %s\n" % (t, msg))
        self.t5_log.config(state="disabled")

    def _t5_connect(self):
        """Connect to the CRM DB (base64 config, background thread)."""
        def job():
            conn = self._get_crm_connection()
            return ("ok", conn)

        def done(r):
            if r[0] == "__error__":
                self.t5_status_var.set("Connection failed")
                self._t5_log("\u2718 CRM connection error: %s" % r[1])
                if messagebox.askretrycancel("Connection Failed",
                                             "%s\n\nClick [Retry] to try again" % r[1]):
                    self._t5_connect()
                else:
                    self.t5_status_var.set("Disconnected")
                return
            self.t5_status_var.set("Connected")
            self._t5_log("Database connected")
            self.t5_info_var.set("(Enter an ICCID and click Query)")
            self.t5_btn_query.config(state="normal")

        self._bg(job, done)

    def _t5_query(self):
        iccid = self.t5_iccid_var.get().strip()
        if not iccid:
            messagebox.showwarning("Notice", "Please enter an ICCID")
            return

        self.t5_btn_query.config(state="disabled")
        self.t5_status_var.set("Querying...")

        def job():
            conn = self._get_crm_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM sim_card WHERE iccid = :1", [iccid])
            cols = [c[0].lower() for c in cur.description]
            rows = cur.fetchall()
            if not rows:
                return ("none", None, None, None)
            sim_id = rows[0][0]
            card = {k: ("" if v is None else str(v)) for k, v in zip(cols, rows[0])}
            cur.execute("""SELECT p.ROWID, p.attr_value, a.attr_name, a.attr_code
                             FROM sim_card_attr_value p, attr a
                            WHERE p.sim_card_id = :1
                              AND p.attr_id = a.attr_id
                              AND a.attr_code = :2
                            ORDER BY a.attr_code""", [sim_id, ATTR_FILTER_CODE])
            attrs = [{"rowid": str(r[0]),
                      "value": "" if r[1] is None else str(r[1]),
                      "name":  "" if r[2] is None else str(r[2]),
                      "code":  "" if r[3] is None else str(r[3])}
                     for r in cur.fetchall()]
            return ("ok", sim_id, card, attrs)

        def done(r):
            self.t5_btn_query.config(state="normal")
            if r[0] == "__error__":
                self.t5_status_var.set("Query failed")
                self._t5_log("\u2718 Query error: %s" % r[1])
                messagebox.showerror("Database Error", r[1])
                return
            if r[0] == "none":
                self.t5_status_var.set("Not found")
                self.t5_tree.delete(*self.t5_tree.get_children())
                self._t5_log("No SIM card found for ICCID=%s" % iccid)
                messagebox.showinfo("Not Found", "No SIM card found for ICCID=%s" % iccid)
                return
            _, sim_id, card, attrs = r
            self.t5_sim_id, self.t5_card, self.t5_attrs = sim_id, card, attrs
            self._t5_render_info()
            self._t5_render_attrs()
            self.t5_status_var.set("SIM_CARD_ID=%s, %s rows" % (sim_id, len(attrs)))
            self._t5_log("Query %s OK: SIM_CARD_ID=%s, %s=%d row(s)"
                         % (iccid, sim_id, ATTR_FILTER_CODE, len(attrs)))
            self.t5_btn_edit.config(state="normal")
            self.t5_btn_refresh.config(state="normal")

        self._bg(job, done)

    def _t5_render_info(self):
        parts = ["%s: %s" % (k, v) for k, v in self.t5_card.items() if v][:8]
        self.t5_info_var.set("\n".join(parts) if parts else "(none)")

    def _t5_render_attrs(self):
        self.t5_tree.delete(*self.t5_tree.get_children())
        for i, a in enumerate(self.t5_attrs):
            self.t5_tree.insert("", "end", iid=str(i),
                                values=(i + 1, a["code"], a["name"], a["value"]))

    def _t5_open_edit(self):
        sel = self.t5_tree.selection()
        if not sel:
            messagebox.showwarning("Notice", "Please select a row first")
            return
        a = self.t5_attrs[int(sel[0])]

        win = tk.Toplevel(self)
        win.title("Edit Attribute")
        win.geometry("430x240")
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="Attribute:  %s / %s" % (a["code"], a["name"]),
                 font=("Segoe UI", 10, "bold"), fg="#1677ff").pack(anchor=tk.W, padx=16, pady=(14, 4))
        tk.Label(win, text="Current Value:  %s" % a["value"]).pack(anchor=tk.W, padx=16, pady=4)
        tk.Label(win, text="New Value(JAVA/NATIVE):").pack(anchor=tk.W, padx=16, pady=(10, 2))
        var = tk.StringVar()
        ent = tk.Entry(win, textvariable=var, font=("Consolas", 11))
        ent.pack(fill=tk.X, padx=16)
        ent.focus_set()

        btns = tk.Frame(win)
        btns.pack(pady=14)

        def _confirm():
            new_value = var.get().strip()
            if not new_value:
                messagebox.showwarning("Notice", "Please enter a new value", parent=win)
                return
            if new_value == a["value"]:
                messagebox.showwarning("Notice", "New value is the same as current value", parent=win)
                return
            if not messagebox.askyesno("Confirm",
                    "Change [%s]\nfrom '%s' to '%s' ?" % (a["code"], a["value"], new_value),
                    parent=win):
                return
            btn_ok.config(state="disabled")

            def job():
                conn = self._get_crm_connection()
                cur = conn.cursor()
                cur.execute("UPDATE crm.SIM_CARD_ATTR_VALUE SET attr_value = :1 WHERE ROWID = :2",
                            [new_value, a["rowid"]])
                if cur.rowcount != 1:
                    conn.rollback()
                    return ("fail", "Updated %d rows (expected 1), rolled back" % cur.rowcount)
                conn.commit()
                cur.execute("SELECT attr_value FROM crm.SIM_CARD_ATTR_VALUE WHERE ROWID = :1",
                            [a["rowid"]])
                return ("ok", cur.fetchone()[0])

            def done(r):
                if r[0] == "__error__":
                    self._t5_log("\u2718 Update error: %s" % r[1])
                    messagebox.showerror("Error", r[1], parent=win)
                    btn_ok.config(state="normal")
                    return
                if r[0] == "ok":
                    self._t5_log("UPDATE crm.SIM_CARD_ATTR_VALUE SET attr_value='%s' WHERE rowid='%s';"
                                 % (new_value, a["rowid"]))
                    self._t5_log("\u2714 Update committed, verified new value: %s" % r[1])
                    win.destroy()
                    self._t5_query()  # auto refresh
                else:
                    self._t5_log("\u2718 Update failed: %s" % r[1])
                    messagebox.showerror("Update Failed", r[1], parent=win)
                    btn_ok.config(state="normal")

            self._bg(job, done)

        win.bind("<Return>", lambda ev: _confirm())
        btn_ok = tk.Button(btns, text="Confirm", width=12, command=_confirm,
                           bg="#1677ff", fg="white")
        btn_ok.pack(side=tk.LEFT, padx=6)
        tk.Button(btns, text="Cancel", width=10, command=win.destroy).pack(side=tk.LEFT, padx=6)

    # ==========================================
    # CORE 6: ROAMING SUBSCRIPTION PASS (mdbtt)
    # ==========================================
    ROAMING_AVP = {
        "KENYA": ("965=6291456,11535056|987=110115702|982=12345|1462=+0800"
                  "|1463=03|1464=639|1465=10502|1466=20260204"),
        "IRAN": ("965=6291456,11535056|987=110115702|982=12345|1462=+0800"
                 "|1463=35|1464=432|1465=10240|1466=20260204"),
    }
    ROAMING_PROMPT_SQL = "SQL>>"

    def _setup_tab6(self, parent):
        frame = ttk.LabelFrame(parent, text=" Roaming Subscription Pass ")
        frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame, text="MSISDN:").grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
        self.t6_msisdn_entry = ttk.Entry(frame, width=32)
        self.t6_msisdn_entry.grid(row=0, column=1, padx=8, pady=8, sticky=tk.W)
        self.t6_msisdn_entry.bind("<Return>", lambda ev: self._t6_validate())

        self.t6_btn_val = ttk.Button(frame, text="Validate MSISDN", command=self._t6_validate)
        self.t6_btn_val.grid(row=0, column=2, padx=8, pady=8)

        ttk.Label(frame, text="Country:").grid(row=1, column=0, padx=8, pady=8, sticky=tk.W)
        self.t6_country_combo = ttk.Combobox(
            frame, values=["IRAN", "KENYA"], state="readonly", width=29)
        self.t6_country_combo.current(1)  # KENYA
        self.t6_country_combo.grid(row=1, column=1, padx=8, pady=8, sticky=tk.W)

        self.t6_btn_run = ttk.Button(frame, text="Execute in mdbtt", state="disabled",
                                     command=self._t6_execute, style="Success.TButton")
        self.t6_btn_run.grid(row=1, column=2, padx=8, pady=8)

        frame_log = ttk.LabelFrame(parent, text=" Operation Log ")
        frame_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)

        self.t6_log = self._create_console(frame_log)
        self.t6_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.t6_subs_ids = None

    def _t6_log(self, text):
        self.t6_log.config(state="normal")
        self.t6_log.insert(tk.END, text + "\n")
        self.t6_log.see(tk.END)
        self.t6_log.config(state="disabled")

    def _t6_validate(self):
        msisdn = self.t6_msisdn_entry.get().strip()
        if not msisdn:
            messagebox.showwarning("Input Error", "Please enter an MSISDN.")
            return

        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor()
        try:
            # CC.SUBS has no state/eff/exp columns - only ids/dates below.
            cursor.execute(
                "SELECT s.subs_id, s.acct_id, s.cust_id, s.created_date "
                "FROM subs s WHERE s.acc_nbr = :1 ORDER BY s.subs_id",
                [msisdn])
            rows = cursor.fetchall()
            if not rows:
                messagebox.showerror("Error", f"No record found in 'subs' for MSISDN {msisdn}")
                self.t6_btn_run.config(state="disabled")
                self.t6_subs_ids = None
                return

            self.t6_subs_ids = [str(r[0]) for r in rows]

            info = "--- MSISDN Validation Passed ---\n"
            info += f"MSISDN      : {msisdn}\n"
            info += f"Subscription(s) found: {len(rows)}\n\n"
            for r in rows:
                info += f"  SUBS_ID={r[0]}  acct_id={r[1]}  cust_id={r[2]}  created={r[3]}\n"
            info += "\nCountry AVP summary:\n"
            info += "  KENYA : 1463=03 | 1464=639  | 1465=10502\n"
            info += "  IRAN  : 1463=35 | 1464=432 | 1465=10240\n"
            self._t6_display(info, clear=True)
            self.t6_btn_run.config(state="normal")

        except Exception as e:
            messagebox.showerror("Query Error", str(e))
        finally:
            cursor.close()

    def _t6_display(self, text, clear=False):
        self.t6_log.config(state="normal")
        if clear:
            self.t6_log.delete('1.0', tk.END)
        self.t6_log.insert(tk.END, text + "\n")
        self.t6_log.config(state="disabled")

    def _t6_execute(self):
        if not self.t6_subs_ids:
            messagebox.showwarning("Missing Data", "Please validate the MSISDN first.")
            return
        country = self.t6_country_combo.get()
        msisdn = self.t6_msisdn_entry.get().strip()
        subs = list(self.t6_subs_ids)

        confirm = messagebox.askyesno(
            "Confirm",
            f"Insert roaming pass row(s) for country {country}?\n\n"
            f"MSISDN : {msisdn}\n"
            f"SUBS_ID(s): {', '.join(subs)}\n\n"
            "This will run inside the OCS mdbtt SQL console "
            "(asyn_call insert, EVENT_ID=2, STATE='A')."
        )
        if not confirm:
            return

        self.t6_btn_run.config(state="disabled")
        self.t6_btn_val.config(state="disabled")
        threading.Thread(target=self._t6_execute_worker,
                         args=(subs, country, msisdn), daemon=True).start()

    def _t6_execute_worker(self, subs_ids, country, msisdn):
        ssh = None
        chan = None
        ok_subs, failed_subs = [], []

        _ansi_re = __import__("re").compile(r"\x1b\[[0-9;?]*[A-Za-z]")

        def read_until(patterns, timeout=30.0, log_prefix="[mdbtt] "):
            """Read channel until a pattern appears; log finished lines."""
            deadline = time.time() + timeout
            buf = ""
            lines = []
            last_sent = getattr(self, "_t6_last_sent", None)
            while time.time() < deadline:
                got = False
                while chan.recv_ready():
                    data = chan.recv(4096)
                    if not data:
                        break
                    buf += data.decode("utf-8", errors="replace")
                    got = True
                    while "\n" in buf:
                        raw, buf = buf.split("\n", 1)
                        clean = _ansi_re.sub("", raw.rstrip("\r")).strip()
                        if not clean:
                            continue
                        if last_sent and clean == last_sent:
                            continue  # drop command echo
                        lines.append(clean)
                        self._t6_log(log_prefix + clean)
                if got or not lines:
                    tail = buf[-512:]
                    for p in patterns:
                        if p in tail or p in "\n".join(lines[-5:]):
                            return p, "\n".join(lines)
                else:
                    for p in patterns:
                        if p in "\n".join(lines[-5:]):
                            return p, "\n".join(lines)
                time.sleep(0.2)
            return None, "\n".join(lines)

        def send_line(line):
            self._t6_last_sent = (line or "").strip()
            chan.send(line + "\r\n")

        try:
            self._t6_log(f"\n--- Roaming pass [{country}] for {msisdn} ---")
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=self.config['ssh']['host'],
                username=self.config['ssh']['username'],
                password=self.config['ssh']['password'],
                timeout=10
            )
            chan = ssh.invoke_shell(term="vt100", width=500, height=50)
            chan.settimeout(5)

            # Wait for the plain shell prompt, then start mdbtt.
            read_until(["> ", "$ ", "# "], timeout=15, log_prefix="[ssh] ")
            self._t6_log("[ssh] shell ready, starting mdbtt ...")

            send_line("cd invoicing/")
            read_until(["> ", "$ ", "# "], timeout=15, log_prefix="[ssh] ")

            send_line("mdbtt")
            match, out = read_until([self.ROAMING_PROMPT_SQL], timeout=60)
            if match != self.ROAMING_PROMPT_SQL:
                self._t6_log("ERROR: mdbtt SQL prompt not detected. Console output:")
                for l in out.splitlines()[-12:]:
                    self._t6_log(f"    {l}")
                messagebox.showerror("mdbtt Error", "mdbtt SQL prompt (SQL>>) not detected.")
                return
            self._t6_log("[mdbtt] SQL console ready (Direct mode).")

            for idx, subs_id in enumerate(subs_ids, 1):
                avp = self.ROAMING_AVP[country]
                sql = (
                    "insert into asyn_call (ASYN_CAL_ID, SUBS_ID, AVP, EVENT_ID, "
                    "CREATED_DATE, STATE, STATE_DATE, COMMENTS, PRIORITY) values "
                    f"(asyn_call_id_seq.nextval, {subs_id}, '{avp}', 2, SYSDATE, 'A', "
                    "SYSDATE, null, 500)"
                )
                self._t6_log(f"[mdbtt] ({idx}/{len(subs_ids)}) SUBS_ID {subs_id}: submitting insert ...")
                # mdbtt requires an explicit ';' terminator (without it the
                # console waits for continuation lines and never executes).
                send_line(sql + ";")
                match, out = read_until(
                    [self.ROAMING_PROMPT_SQL, "ERROR", "error", "ORA-"], timeout=60)
                if match == self.ROAMING_PROMPT_SQL:
                    ok_subs.append(subs_id)
                    self._t6_log(f"[mdbtt] SUBS_ID {subs_id}: insert submitted OK.")
                else:
                    failed_subs.append(subs_id)
                    self._t6_log(f"[mdbtt] SUBS_ID {subs_id}: FAILED (matched '{match}').")

            send_line("commit;")
            read_until([self.ROAMING_PROMPT_SQL], timeout=30)
            # Let the OCS platform settle (async processing of the queued
            # asyn_call rows) before tearing the SQL console down.
            self._t6_log("[mdbtt] commit done; waiting 10s before disconnecting the SQL console ...")
            time.sleep(10)
            send_line("quit;")
            time.sleep(3)
            self._t6_log("[mdbtt] SQL console disconnected (quit;); closing SSH session.")

            if not failed_subs:
                self._t6_log(f"\nSUCCESS: {len(ok_subs)} asyn_call row(s) inserted via mdbtt and committed.")
                messagebox.showinfo("Success", f"Roaming pass rows inserted for {len(ok_subs)} subscription(s).")
            else:
                self._t6_log(f"\nFAILED for SUBS_ID(s): {', '.join(failed_subs)}")
                messagebox.showerror(
                    "Execution Failed",
                    f"Insert failed for SUBS_ID(s): {', '.join(failed_subs)}. Check the operation log.")

        except Exception as e:
            self._t6_log(f"Error during mdbtt execution: {e}")
            messagebox.showerror("mdbtt Execution Error", str(e))
        finally:
            if chan is not None:
                try:
                    chan.close()
                except Exception:
                    pass
            if ssh is not None:
                try:
                    ssh.close()
                except Exception:
                    pass
            self.t6_btn_run.config(state="normal")
            self.t6_btn_val.config(state="normal")


if __name__ == "__main__":
    app = TelecomOpsApp()
    app.mainloop()