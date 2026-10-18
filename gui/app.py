# -*- coding: utf-8 -*-
"""桌面界面（Tkinter，无第三方依赖）"""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import (BiliClient, BiliError, DownloadTask, __version__, auth,
                  data_dir, default_out, ffmpeg_path, fmt_duration, hints,
                  parse_links, save_config)

QUALITY_LABEL = [
    ("4k-hevc", "4K HEVC（兼容性最好）"),
    ("4k-av1", "4K AV1（体积最省）"),
    ("4k", "4K 最高码率（最费空间）"),
    ("1080", "1080P"),
]
RATE = {"4k-av1": 0.60, "4k-hevc": 1.00, "4k": 1.50, "1080": 0.45}


def show_bili_error(parent, err) -> None:
    """把 BiliError / AuthError 变成「出了什么事 + 怎么解决」的对话框"""
    steps = getattr(err, "steps", None) or []
    title = getattr(err, "hint", "") or "出错了"
    msg = str(err)
    if steps:
        msg += "\n\n怎么解决：\n" + "\n".join(
            f"{i + 1}. {s}" for i, s in enumerate(steps))
    messagebox.showerror(title, msg, parent=parent)


# ==================== 登录对话框 ====================
class LoginDialog(tk.Toplevel):
    """扫码 + 粘贴 Cookie 两种登录方式"""

    def __init__(self, master: tk.Misc, on_ok) -> None:
        super().__init__(master)
        self.title("登录 B 站")
        self.geometry("540x600")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.on_ok = on_ok
        self._alive = True
        self._qr_key = ""
        self._busy = False

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)
        self._build_qr(nb)
        self._build_paste(nb)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(120, self._new_qr)

    # ---------- 扫码页 ----------
    def _build_qr(self, nb) -> None:
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="  扫码登录  ")

        ttk.Label(f, text="用手机 B 站 App 扫一扫，确认后自动登录",
                  foreground="#555").pack(pady=(0, 8))

        self.canvas = tk.Canvas(f, width=260, height=260, bg="#ffffff",
                                highlightthickness=1, highlightbackground="#ddd")
        self.canvas.pack()

        self.qr_status = ttk.Label(f, text="正在申请二维码…", foreground="#666")
        self.qr_status.pack(pady=10)

        row = ttk.Frame(f)
        row.pack()
        ttk.Button(row, text="刷新二维码", command=self._new_qr).pack(side="left", padx=4)
        ttk.Button(row, text="改用粘贴 Cookie",
                   command=lambda: nb.select(1)).pack(side="left", padx=4)

    def _draw_qr(self, matrix) -> None:
        c = self.canvas
        c.delete("all")
        n = len(matrix)
        size = 260
        cell = max(2, size // (n + 4))
        off = (size - cell * n) // 2
        for y, row in enumerate(matrix):
            x = 0
            while x < n:
                if row[x]:
                    run = 1
                    while x + run < n and row[x + run]:
                        run += 1
                    c.create_rectangle(off + x * cell, off + y * cell,
                                       off + (x + run) * cell, off + (y + 1) * cell,
                                       fill="#0b0c10", outline="")
                    x += run
                else:
                    x += 1

    def _new_qr(self) -> None:
        self.canvas.delete("all")
        self._set_status("正在申请二维码…", "#666")
        self._qr_key = ""

        def work():
            try:
                g = auth.qr_generate()
                m = auth.qr_matrix(g["url"])
            except Exception as e:                      # noqa: BLE001
                self._ui(lambda: self._set_status(f"申请失败：{e}", "#c00"))
                return
            self._qr_key = g["key"]
            self._ui(lambda: (self._draw_qr(m),
                              self._set_status("请用手机扫码", "#666"),
                              self._schedule_poll(1200)))

        threading.Thread(target=work, daemon=True).start()

    def _schedule_poll(self, delay: int = 1800) -> None:
        if self._alive:
            self.after(delay, self._poll_qr)

    def _poll_qr(self) -> None:
        if not self._alive or not self._qr_key:
            return
        key = self._qr_key

        def work():
            try:
                st = auth.qr_poll(key)
            except Exception as e:                      # noqa: BLE001
                self._ui(lambda: self._set_status(f"轮询失败：{e}", "#c00"))
                return
            state = st.get("state")
            if state == "ok":
                self._ui(lambda: self._finish(st.get("account")))
            elif state == "scan":
                self._ui(lambda: (self._set_status("已扫码，请在手机上点确认", "#b8860b"),
                                  self._schedule_poll()))
            elif state == "expired":
                self._ui(lambda: self._set_status("二维码已过期，点「刷新二维码」", "#c00"))
            else:
                self._ui(lambda: self._schedule_poll())

        threading.Thread(target=work, daemon=True).start()

    def _set_status(self, text: str, color: str = "#666") -> None:
        try:
            self.qr_status.config(text=text, foreground=color)
        except tk.TclError:
            pass

    # ---------- 粘贴页 ----------
    def _build_paste(self, nb) -> None:
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="  粘贴 Cookie  ")

        ttk.Label(f, text="浏览器打开 bilibili.com 并登录 → F12 → Network → "
                          "刷新页面 → 点任意请求 → 复制 Request Headers 里的 "
                          "Cookie 整行", foreground="#555", wraplength=470,
                  justify="left").pack(anchor="w", pady=(0, 8))

        self.txt = tk.Text(f, height=10, wrap="word", font=("Consolas", 9),
                           relief="solid", borderwidth=1)
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", hints.PASTE_PLACEHOLDER)

        self.paste_status = ttk.Label(f, text="", foreground="#666")
        self.paste_status.pack(anchor="w", pady=8)

        row = ttk.Frame(f)
        row.pack(fill="x")
        self.save_btn = ttk.Button(row, text="验证并保存", command=self._save_paste)
        self.save_btn.pack(side="left")
        ttk.Button(row, text="取消", command=self._close).pack(side="left", padx=6)

    def _save_paste(self) -> None:
        text = self.txt.get("1.0", "end").strip()
        if not text:
            self.paste_status.config(text="先粘贴 Cookie", foreground="#c00")
            return
        self.save_btn.config(state="disabled")
        self.paste_status.config(text="正在向 B 站校验…", foreground="#666")

        def work():
            try:
                acc = auth.save_from_text(text)
            except Exception as e:                      # noqa: BLE001
                def fail():
                    self.save_btn.config(state="normal")
                    self.paste_status.config(text=str(e), foreground="#c00")
                    if isinstance(e, (auth.AuthError, BiliError)):
                        show_bili_error(self, e)
                self._ui(fail)
                return
            self._ui(lambda: self._finish(acc))

        threading.Thread(target=work, daemon=True).start()

    # ---------- 收尾 ----------
    def _finish(self, acc) -> None:
        self._alive = False
        try:
            self.on_ok(acc or {"is_login": True, "uname": "已登录"})
        finally:
            self.destroy()

    def _ui(self, fn) -> None:
        if self._alive:
            try:
                self.after(0, fn)
            except tk.TclError:
                pass

    def _close(self) -> None:
        self._alive = False
        self.destroy()


# ==================== 按链接下载 ====================
class LinkDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_submit) -> None:
        super().__init__(master)
        self.title("按链接下载")
        self.geometry("560x420")
        self.transient(master.winfo_toplevel())
        self.on_submit = on_submit

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="把视频链接或 BV 号粘进来，一行一个或混在一起都行。\n"
                          "这条路不读收藏夹接口，收藏夹被风控时可以用。",
                  foreground="#555", justify="left").pack(anchor="w", pady=(0, 8))

        self.txt = tk.Text(f, height=12, wrap="word", font=("Consolas", 9),
                           relief="solid", borderwidth=1)
        self.txt.pack(fill="both", expand=True)

        self.status = ttk.Label(f, text="", foreground="#666")
        self.status.pack(anchor="w", pady=8)

        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="解析并下载", command=self._submit).pack(side="left")
        ttk.Button(row, text="取消", command=self.destroy).pack(side="left", padx=6)

    def _submit(self) -> None:
        urls = parse_links(self.txt.get("1.0", "end"))
        if not urls:
            self.status.config(text="没识别到 BV 号或链接", foreground="#c00")
            return
        self.on_submit(urls)
        self.destroy()


# ==================== 主界面 ====================
class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.client = BiliClient()
        self.items: list[dict] = []
        self.selected: set[int] = set()
        self.task: DownloadTask | None = None
        self._login_dialog: LoginDialog | None = None
        self._build()
        self._load_account(auto_login=True)
        self._load_folders()
        self._poll()

    # ---------------- 界面 ----------------
    def _build(self) -> None:
        self.root.title("B站收藏夹下载器")
        self.root.geometry("1000x720")
        self.root.minsize(860, 600)

        pad = {"padx": 10, "pady": 4}

        # 顶部
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="收藏夹").pack(side="left")
        self.folder_var = tk.StringVar()
        self.folder_box = ttk.Combobox(top, textvariable=self.folder_var, state="readonly", width=42)
        self.folder_box.pack(side="left", padx=6)
        self.folder_box.bind("<<ComboboxSelected>>", lambda e: self._load_items())
        ttk.Button(top, text="刷新", command=self._load_folders).pack(side="left")
        ttk.Button(top, text="重载列表", command=lambda: self._load_items(refresh=True)).pack(side="left", padx=6)

        self.login_btn = ttk.Button(top, text="登录 / 换号", command=self._open_login)
        self.login_btn.pack(side="right")
        self.account_lbl = ttk.Label(top, text="读取账号…", foreground="#666")
        self.account_lbl.pack(side="right", padx=8)

        # 统计
        stat = ttk.Frame(self.root)
        stat.pack(fill="x", **pad)
        self.stat_lbl = ttk.Label(stat, text="—", font=("Microsoft YaHei", 10))
        self.stat_lbl.pack(side="left")

        # 工具条
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", **pad)
        ttk.Button(bar, text="全选", command=self._sel_all).pack(side="left")
        ttk.Button(bar, text="全不选", command=self._sel_none).pack(side="left", padx=4)
        ttk.Button(bar, text="反选", command=self._sel_invert).pack(side="left")
        ttk.Label(bar, text="搜索").pack(side="left", padx=(14, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._render())
        ttk.Entry(bar, textvariable=self.search_var, width=26).pack(side="left")
        self.sel_lbl = ttk.Label(bar, text="已选 0 条", foreground="#555")
        self.sel_lbl.pack(side="right")

        # 列表
        wrap = ttk.Frame(self.root)
        wrap.pack(fill="both", expand=True, **pad)
        cols = ("check", "idx", "title", "up", "dur")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="none")
        for c, t, w, anchor in [
            ("check", "", 34, "center"), ("idx", "#", 44, "center"),
            ("title", "标题", 480, "w"), ("up", "UP主", 130, "w"), ("dur", "时长", 70, "e"),
        ]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "title"))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.tag_configure("odd", background="#f7f8fa")

        # 底部选项
        opt = ttk.Frame(self.root)
        opt.pack(fill="x", **pad)
        ttk.Label(opt, text="画质").pack(side="left")
        self.quality_var = tk.StringVar(value=QUALITY_LABEL[0][1])
        qbox = ttk.Combobox(opt, textvariable=self.quality_var, state="readonly", width=26,
                            values=[lbl for _, lbl in QUALITY_LABEL])
        qbox.pack(side="left", padx=6)
        qbox.bind("<<ComboboxSelected>>", lambda e: self._update_stats())
        ttk.Label(opt, text="保存到").pack(side="left", padx=(12, 4))
        self.out_var = tk.StringVar(value=str(default_out()))
        ttk.Entry(opt, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(opt, text="浏览…", command=self._pick_dir).pack(side="left", padx=6)

        # 按钮
        btn = ttk.Frame(self.root)
        btn.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btn, text="开始下载", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn, text="停止", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Button(btn, text="按链接下载…", command=self._open_link).pack(side="left")
        ttk.Button(btn, text="遇到问题？", command=self._show_help).pack(side="right")
        self.hint_lbl = ttk.Label(btn, text="勾选要下载的条目，点开始", foreground="#777")
        self.hint_lbl.pack(side="left", padx=10)

        # 进度
        prog = ttk.Frame(self.root)
        prog.pack(fill="x", **pad)
        self.pbar = ttk.Progressbar(prog, mode="determinate", maximum=100)
        self.pbar.pack(fill="x")
        self.pinfo = ttk.Label(prog, text="", foreground="#555")
        self.pinfo.pack(anchor="w", pady=(3, 0))

        logf = ttk.Frame(self.root)
        logf.pack(fill="both", **pad)
        self.log = tk.Text(logf, height=7, wrap="none", font=("Consolas", 9),
                           bg="#fbfbfc", fg="#555", relief="solid", borderwidth=1)
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")

    # ---------------- 登录 ----------------
    def _open_login(self) -> None:
        if self._login_dialog and self._login_dialog.winfo_exists():
            self._login_dialog.lift()
            return
        self._login_dialog = LoginDialog(self.root, self._after_login)

    def _after_login(self, acc) -> None:
        self.client.reload_cookies()
        self._load_account()
        self._load_folders()
        self.hint_lbl.config(text=f"已登录：{acc.get('uname', '')}")

    def _show_help(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("遇到问题？")
        win.geometry("620x520")
        win.transient(self.root)
        txt = tk.Text(win, wrap="word", padx=14, pady=12,
                      font=("Microsoft YaHei", 9), relief="flat", bg="#fbfbfc")
        sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        body = [f"版本 {__version__}",
                f"ffmpeg：{ffmpeg_path() or '未找到（下载完无法合并音视频）'}",
                f"登录态/配置目录：{data_dir()}",
                "", f"【{hints.RISK_TITLE}】", hints.RISK_REASON, ""]
        body += [f"{i + 1}. {s}" for i, s in enumerate(hints.RISK_STEPS)]
        body += ["", hints.RISK_TIP, "", f"【{hints.LOGIN_TITLE}】", ""]
        body += [f"{i + 1}. {s}" for i, s in enumerate(hints.LOGIN_STEPS)]
        txt.insert("1.0", "\n".join(body))
        txt.config(state="disabled")

    # ---------------- 数据加载 ----------------
    def _bg(self, fn, done) -> None:
        def run():
            try:
                r = fn()
            except Exception as e:                      # noqa: BLE001
                self.root.after(0, lambda: done(None, e))
                return
            self.root.after(0, lambda: done(r, None))
        threading.Thread(target=run, daemon=True).start()

    def _load_account(self, auto_login: bool = False) -> None:
        def done(acc, err):
            if err or not acc:
                self.account_lbl.config(text="账号读取失败", foreground="#c00")
                return
            if not acc.get("is_login"):
                self.account_lbl.config(text="未登录", foreground="#c00")
                self.login_btn.config(text="登录 B 站")
                if auto_login and not auth.status().get("has_cookie"):
                    self.root.after(400, self._open_login)
                return
            vip = "（大会员）" if acc.get("vip") else ""
            self.account_lbl.config(text=f"{acc['uname']}{vip}", foreground="#2a7")
            self.login_btn.config(text="换号")
        self._bg(self.client.account, done)

    def _load_folders(self) -> None:
        def done(fs, err):
            if err is not None:
                self.folder_box["values"] = []
                show_bili_error(self.root, err)
                return
            if fs is None:
                return
            self._folders = fs
            self.folder_box["values"] = [f"{f['title']}（{f['count']} 条）" for f in fs]
            if fs:
                self.folder_box.current(0)
                self._load_items()
        self._bg(self.client.folders, done)

    def _current_fid(self) -> int | None:
        idx = self.folder_box.current()
        if idx < 0 or not getattr(self, "_folders", None):
            return None
        return self._folders[idx]["id"]

    def _load_items(self, refresh: bool = False) -> None:
        fid = self._current_fid()
        if not fid:
            return
        self.hint_lbl.config(text="加载列表…")

        def prog(msg: str) -> None:
            self.root.after(0, lambda: self.hint_lbl.config(text=msg))

        self._bg(lambda: self.client.medias(fid, refresh=refresh, on_progress=prog),
                 lambda items, err: self._apply_items(items, err))

    def _apply_items(self, items, err) -> None:
        if err is not None:
            self.hint_lbl.config(text=f"加载失败：{err}")
            show_bili_error(self.root, err)
            return
        self.items = items or []
        self.selected.clear()
        self._render()
        self._update_stats()
        self.hint_lbl.config(text="勾选要下载的条目，点开始")

    # ---------------- 列表渲染 ----------------
    def _filtered(self):
        kw = self.search_var.get().strip().lower()
        out = []
        for i, it in enumerate(self.items):
            if kw and kw not in it["title"].lower() and kw not in it["upper"].lower():
                continue
            out.append((i, it))
        return out

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for n, (i, it) in enumerate(self._filtered()):
            mark = "☑" if i in self.selected else "☐"
            self.tree.insert("", "end", iid=str(i), tags=("odd",) if n % 2 else (),
                             values=(mark, i + 1, it["title"], it["upper"],
                                     fmt_duration(it["duration"])))
        self._update_sel()

    def _on_click(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        i = int(row)
        self.selected.symmetric_difference_update({i})
        self.tree.set(row, "check", "☑" if i in self.selected else "☐")
        self._update_sel()

    def _update_sel(self) -> None:
        self.sel_lbl.config(text=f"已选 {len(self.selected)} 条")

    def _sel_all(self) -> None:
        self.selected = {i for i, _ in self._filtered()}
        self._render()

    def _sel_none(self) -> None:
        self.selected.clear()
        self._render()

    def _sel_invert(self) -> None:
        visible = {i for i, _ in self._filtered()}
        self.selected = visible - self.selected
        self._render()

    # ---------------- 统计 ----------------
    def _quality_key(self) -> str:
        label = self.quality_var.get()
        for k, lbl in QUALITY_LABEL:
            if lbl == label:
                return k
        return "4k-hevc"

    def _update_stats(self) -> None:
        if not self.items:
            self.stat_lbl.config(text="—")
            return
        sec = sum(i["duration"] for i in self.items)
        gb = sec * RATE[self._quality_key()] / 1024
        self.stat_lbl.config(
            text=f"{len(self.items)} 条  ·  {sec/3600:.1f} 小时  ·  预估 {gb:.1f} GB")

    # ---------------- 下载 ----------------
    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_var.get() or str(Path.home()))
        if d:
            self.out_var.set(d)

    def _open_link(self) -> None:
        LinkDialog(self.root, self._start_urls)

    def _start(self) -> None:
        if not self.selected:
            messagebox.showinfo("提示", "先勾选要下载的条目")
            return
        idxs = sorted(self.selected)
        urls = [f"https://www.bilibili.com/video/{self.items[i]['bvid']}" for i in idxs]
        title_map = {self.items[i]["bvid"]: self.items[i]["title"] for i in idxs}
        self._start_urls(urls, title_map)

    def _start_urls(self, urls: list[str], title_map: dict | None = None) -> None:
        if self.task and self.task.snapshot()["status"] == "running":
            messagebox.showinfo("提示", "已有任务在运行")
            return
        out = self.out_var.get().strip() or str(default_out())
        save_config({"out_dir": out})
        self.task = DownloadTask(urls, out_dir=out, quality=self._quality_key(),
                                 title_map=title_map or {})
        self.task.start()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log.delete("1.0", "end")
        self.hint_lbl.config(text=f"下载 {len(urls)} 条到 {out}")

    def _stop(self) -> None:
        if self.task:
            self.task.stop()
            self.hint_lbl.config(text="已停止")

    # ---------------- 轮询 ----------------
    def _poll(self) -> None:
        if self.task:
            s = self.task.snapshot()
            self.pbar["value"] = s["overall"]
            speed = f" · {s['speed']}" if s.get("speed") else ""
            eta = f" · 剩余 {s['eta']}" if s.get("eta") else ""
            self.pinfo.config(
                text=f"{s['overall']:.1f}%  ({s['finished']}/{s['total']}){speed}{eta}"
                     f"   当前：{s['current_title'][:50]}")
            if s["log"]:
                self.log.delete("1.0", "end")
                self.log.insert("end", "\n".join(s["log"][-30:]))
                self.log.see("end")
            if s["status"] in ("done", "error", "stopped"):
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")
                err = s.get("error") or ""
                msg = {"done": "下载完成", "error": f"出错：{err}",
                       "stopped": "已停止"}[s["status"]]
                self.hint_lbl.config(text=msg)
                self.task = None            # 先清掉，避免弹窗阻塞时 _poll 重复进来
                if err:
                    detail = err
                    if s.get("steps"):
                        detail += "\n\n怎么解决：\n" + "\n".join(
                            f"{i + 1}. {x}" for i, x in enumerate(s["steps"]))
                    messagebox.showerror(s.get("hint") or "下载失败", detail,
                                         parent=self.root)
        self.root.after(600, self._poll)


def run() -> None:
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    run()
