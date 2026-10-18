# -*- coding: utf-8 -*-
"""Web 界面后端（Flask）"""
import shutil
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from core import (BiliClient, BiliError, DownloadTask, QUALITY_SORT, __version__,
                  app_dir, auth, data_dir, default_out, ffmpeg_path, hints,
                  parse_links)

BASE = app_dir()

# 打包后静态资源在 PyInstaller 的解压目录里
if getattr(sys, "frozen", False):
    STATIC = Path(getattr(sys, "_MEIPASS", BASE)) / "static"
else:
    STATIC = Path(__file__).resolve().parent.parent / "static"

app = Flask(__name__, static_folder=None)
_client = BiliClient()
_lock = threading.Lock()
_task: DownloadTask | None = None
_qr = {"key": "", "ts": 0.0}
_progress = {"fid": None, "msg": ""}


def ok(**kw):
    return jsonify({"ok": True, **kw})


def fail(err, code: int = 400):
    """把 BiliError / AuthError 统一成带解决步骤的 JSON"""
    if hasattr(err, "payload"):
        return jsonify({"ok": False, **err.payload()}), code
    return jsonify({"ok": False, "error": str(err), "kind": "api"}), code


def disk_free_gb(path: str | Path) -> float:
    try:
        return round(shutil.disk_usage(str(path)).free / 1024 ** 3, 1)
    except Exception:
        return 0.0


# ---------------- 页面 ----------------
@app.get("/")
def index():
    return send_file(STATIC / "index.html")


# ---------------- 账号 ----------------
@app.get("/api/account")
def api_account():
    try:
        with _lock:
            acc = _client.account()
        return ok(account=acc, cookie=auth.status())
    except BiliError as e:
        return fail(e)


@app.post("/api/logout")
def api_logout():
    auth.logout()
    _client.reload_cookies()
    return ok()


# ---------------- 登录：粘贴 Cookie ----------------
@app.post("/api/login/cookie")
def api_login_cookie():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text") or data.get("cookie") or ""
    try:
        acc = auth.save_from_text(text)
    except auth.AuthError as e:
        return fail(e)
    except Exception as e:                       # noqa: BLE001
        return fail(f"保存失败：{e}")
    _client.reload_cookies()
    return ok(account=acc)


# ---------------- 登录：扫码 ----------------
@app.get("/api/login/qrcode")
def api_qrcode():
    try:
        g = auth.qr_generate()
    except auth.AuthError as e:
        return fail(e)
    except Exception as e:                       # noqa: BLE001
        return fail(f"生成二维码失败：{e}")
    _qr["key"], _qr["ts"] = g["key"], time.time()
    return ok(key=g["key"], svg=g["svg"], url=g["url"])


@app.get("/api/login/qrcode/poll")
def api_qrcode_poll():
    key = request.args.get("key") or _qr.get("key") or ""
    if not key:
        return fail("没有可用的二维码，请刷新")
    try:
        st = auth.qr_poll(key)
    except auth.AuthError as e:
        return fail(e)
    except Exception as e:                       # noqa: BLE001
        return fail(f"轮询失败：{e}")
    if st.get("state") == "ok":
        _client.reload_cookies()
        return ok(state="ok", message=st.get("message", "登录成功"),
                  account=st.get("account"))
    return ok(state=st.get("state"), message=st.get("message", ""))


# ---------------- 收藏夹 ----------------
@app.get("/api/folders")
def api_folders():
    try:
        with _lock:
            return ok(folders=_client.folders())
    except BiliError as e:
        return fail(e)


@app.get("/api/progress")
def api_progress():
    return ok(progress=_progress)


@app.get("/api/folders/<int:fid>/items")
def api_items(fid: int):
    refresh = request.args.get("refresh") == "1"
    _progress.update({"fid": fid, "msg": "读取中…"})

    def on_progress(msg: str) -> None:
        _progress["msg"] = msg

    try:
        with _lock:
            items = _client.medias(fid, refresh=refresh, on_progress=on_progress)
        _progress["msg"] = ""
        return ok(items=items, estimate=_client.estimate(items, "4k-hevc"))
    except BiliError as e:
        _progress["msg"] = ""
        return fail(e)
    except Exception as e:                       # noqa: BLE001
        _progress["msg"] = ""
        return fail(f"读取失败：{e}")


# ---------------- 下载 ----------------
def _start_task(urls: list[str], quality: str, out_dir: str,
                title_map: dict | None = None):
    global _task
    with _lock:
        if _task and _task.snapshot()["status"] == "running":
            return fail("已有任务在运行，请先停止")
    _task = DownloadTask(urls, out_dir=out_dir, quality=quality,
                         title_map=title_map or {})
    _task.start()
    return ok(total=len(urls), out_dir=out_dir)


@app.post("/api/download")
def api_download():
    data = request.get_json(force=True, silent=True) or {}
    bvids = data.get("bvids") or []
    if not bvids:
        return fail("没有选中任何条目")
    quality = data.get("quality") or "4k-hevc"
    if quality not in QUALITY_SORT:
        return fail(f"未知画质档位: {quality}")
    out_dir = data.get("out_dir") or str(default_out())
    urls = [f"https://www.bilibili.com/video/{b}" for b in bvids]
    return _start_task(urls, quality, out_dir, data.get("title_map") or {})


@app.post("/api/download/links")
def api_download_links():
    """按 BV 号 / 链接直接下载 —— 风控时的逃生通道，不读收藏夹接口"""
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text") or ""
    urls = parse_links(text)
    if not urls:
        return fail("没识别到 BV 号或视频链接（示例：BV1pXnu6nEkK 或完整视频网址）")
    quality = data.get("quality") or "4k-hevc"
    if quality not in QUALITY_SORT:
        return fail(f"未知画质档位: {quality}")
    out_dir = data.get("out_dir") or str(default_out())
    return _start_task(urls, quality, out_dir)


@app.get("/api/status")
def api_status():
    if not _task:
        return ok(status={"status": "idle", "total": 0, "finished": 0,
                          "overall": 0, "percent": 0, "log": []})
    return ok(status=_task.snapshot())


@app.post("/api/stop")
def api_stop():
    if _task:
        _task.stop()
        return ok()
    return fail("没有正在运行的任务")


@app.get("/api/quality")
def api_quality():
    out = str(default_out())
    return ok(qualities=list(QUALITY_SORT.keys()), default="4k-hevc",
              out_dir=out, disk_free=disk_free_gb(out if Path(out).exists()
                                                  else Path.home()))


@app.get("/api/help")
def api_help():
    """把提示文案给前端，文案只维护一份"""
    return ok(login={"title": hints.LOGIN_TITLE, "steps": hints.LOGIN_STEPS,
                     "placeholder": hints.PASTE_PLACEHOLDER},
              risk={"title": hints.RISK_TITLE, "reason": hints.RISK_REASON,
                    "steps": hints.RISK_STEPS, "tip": hints.RISK_TIP})


@app.get("/api/env")
def api_env():
    """运行环境自检：ffmpeg 找没找到、数据存哪（出问题时先看这个）"""
    ff = ffmpeg_path()
    return ok(version=__version__,
              ffmpeg=str(ff) if ff else "",
              ffmpeg_ok=bool(ff),
              data_dir=str(data_dir()),
              app_dir=str(BASE),
              cookie=auth.status()["path"])


def run(port: int = 8765, open_browser: bool = True) -> None:
    if open_browser:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False,
            threaded=True)


if __name__ == "__main__":
    run()
