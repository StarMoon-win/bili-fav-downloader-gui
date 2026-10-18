#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B站收藏夹下载器 - 统一入口

不带参数运行时会弹窗让你选界面：
    --gui   直接打开桌面窗口
    --web   直接打开浏览器界面（默认端口 8765）
"""
import argparse
import sys
import threading


def run_gui() -> None:
    from gui.app import run as gui_run
    gui_run()


def run_web(port: int = 8765, open_browser: bool = True) -> None:
    from web.app import run as web_run
    web_run(port=port, open_browser=open_browser)


def choose_mode() -> str | None:
    """弹一个选择窗口，返回 'gui' / 'web' / None"""
    import tkinter as tk
    from tkinter import font as tkfont

    choice = {"mode": None}
    root = tk.Tk()
    root.title("B站收藏夹下载器")
    root.geometry("440x280")
    root.resizable(False, False)
    try:
        root.eval("tk::PlaceWindow . center")
    except Exception:
        pass

    big = tkfont.Font(family="Microsoft YaHei", size=12, weight="bold")
    small = tkfont.Font(family="Microsoft YaHei", size=9)

    tk.Label(root, text="选择界面", font=big, pady=14).pack()
    tk.Label(root, text="两种界面功能完全一样，随你习惯", font=small,
             fg="#777").pack(pady=(0, 16))

    box = tk.Frame(root)
    box.pack()

    def pick(mode: str) -> None:
        choice["mode"] = mode
        root.destroy()

    tk.Button(box, text="桌面窗口", font=big, width=13, height=3,
              command=lambda: pick("gui")).pack(side="left", padx=10)
    tk.Button(box, text="浏览器界面", font=big, width=13, height=3,
              command=lambda: pick("web")).pack(side="left", padx=10)

    tk.Label(root, text="桌面窗口：原生应用，可直接选目录\n浏览器界面：界面更精致，可开多个标签页",
             font=small, fg="#999", justify="center").pack(pady=18)

    root.mainloop()
    return choice["mode"]


def main() -> int:
    ap = argparse.ArgumentParser(description="B站收藏夹下载器")
    ap.add_argument("--gui", action="store_true", help="直接打开桌面窗口")
    ap.add_argument("--web", action="store_true", help="直接打开浏览器界面")
    ap.add_argument("--port", type=int, default=8765, help="Web 端口，默认 8765")
    ap.add_argument("--no-browser", action="store_true", help="Web 模式下不自动开浏览器")
    args = ap.parse_args()

    if args.gui:
        run_gui()
        return 0
    if args.web:
        run_web(args.port, not args.no_browser)
        return 0

    mode = choose_mode()
    if mode == "gui":
        run_gui()
    elif mode == "web":
        run_web(args.port, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
