# -*- coding: utf-8 -*-
"""下载任务管理：直接用 yt-dlp 的 Python API（打包后不依赖外部 python 命令）"""
import threading
from pathlib import Path

from . import hints
from .config import cookie_file, default_out, ffmpeg_path

QUALITY_SORT = {
    "4k-av1": ["res:2160", "vcodec:av01"],
    "4k-hevc": ["res:2160", "vcodec:h265"],
    "4k": ["res:2160"],
    "1080": ["res:1080"],
}

# 这些字眼出现在 yt-dlp 的报错里，基本就是被风控 / 被掐连接了
RISK_WORDS = ("412", "RemoteDisconnected", "Unable to download webpage",
              "Connection aborted", "timed out", "ReadTimeout", "429")


class _Cancelled(Exception):
    pass


class _YdlLogger:
    """把 yt-dlp 的报错接进任务日志。

    不开这个的话，`ignoreerrors=True` + `quiet=True` 会把失败全吞掉，
    界面上看起来像「下载完成」，实际一个文件都没有。
    """

    def __init__(self, task: "DownloadTask") -> None:
        self.task = task

    def debug(self, msg) -> None:      # noqa: D401
        pass

    def info(self, msg) -> None:
        pass

    def warning(self, msg) -> None:
        pass

    def error(self, msg) -> None:
        self.task._fail(str(msg))


class DownloadTask:
    """一次批量下载任务。后台线程跑 yt-dlp，主线程读 snapshot() 拿进度。"""

    def __init__(self, urls: list[str], out_dir: str | Path | None = None,
                 quality: str = "4k-hevc", title_map: dict | None = None) -> None:
        self.urls = [u for u in urls if u.strip()]
        self.out_dir = Path(out_dir) if out_dir else default_out()
        self.quality = quality if quality in QUALITY_SORT else "4k-hevc"
        self.title_map = title_map or {}
        self._lock = threading.RLock()
        self._cancel = False
        self._thread: threading.Thread | None = None
        self._done_ids: set[str] = set()
        self._cur_bv = ""
        self._state = {
            "status": "idle",
            "total": len(self.urls),
            "finished": 0,
            "current_index": 0,
            "current_title": "",
            "percent": 0.0,
            "overall": 0.0,
            "speed": "",
            "eta": "",
            "log": [],
            "error": "",
            "failed": [],
            "kind": "",
            "hint": "",
            "steps": [],
        }

    # ---------------- 对外 ----------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._cancel = True
        with self._lock:
            if self._state["status"] == "running":
                self._state["status"] = "stopped"
                self._state["log"].append("已请求停止…")

    def snapshot(self) -> dict:
        with self._lock:
            s = dict(self._state)
            s["log"] = list(self._state["log"][-60:])
            s["failed"] = list(self._state["failed"])
            s["steps"] = list(self._state["steps"])
            return s

    # ---------------- 内部 ----------------
    def _log(self, msg: str) -> None:
        with self._lock:
            self._state["log"].append(msg)
            if len(self._state["log"]) > 500:
                del self._state["log"][:-250]

    def _fail(self, msg: str) -> None:
        """记录一条下载失败（来自 yt-dlp 的 logger.error）"""
        msg = msg.strip()
        if not msg:
            return
        with self._lock:
            self._state["failed"].append(msg[:300])
            self._state["log"].append("✗ " + msg[:160])
            if len(self._state["log"]) > 500:
                del self._state["log"][:-250]

    def _progress(self, d: dict) -> None:
        if self._cancel:
            raise _Cancelled()

        status = d.get("status")
        info = d.get("info_dict") or {}
        bv = info.get("id", "") or ""

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0.0
            with self._lock:
                if bv and bv != self._cur_bv:
                    self._cur_bv = bv
                    self._state["current_index"] += 1
                    self._state["current_title"] = self.title_map.get(
                        bv, (info.get("title") or "")[:60])
                self._state["percent"] = round(pct, 1)
                self._state["speed"] = (d.get("_speed_str") or "").strip()
                self._state["eta"] = (d.get("_eta_str") or "").strip()
                n = max(self._state["total"], 1)
                self._state["overall"] = round(min(
                    100.0, (len(self._done_ids) + pct / 100.0) / n * 100), 1)

        elif status == "finished":
            with self._lock:
                if bv and bv not in self._done_ids:
                    self._done_ids.add(bv)
                    self._state["finished"] = len(self._done_ids)
                    n = max(self._state["total"], 1)
                    self._state["overall"] = round(
                        min(100.0, len(self._done_ids) / n * 100), 1)
            self._log(f"完成：{self.title_map.get(bv, bv)}")

    def _postproc(self, d: dict) -> None:
        if self._cancel:
            raise _Cancelled()
        if d.get("status") == "started" and d.get("postprocessor") in ("Merger", "FFmpegMerger"):
            self._log("合并音视频…")

    def _run(self) -> None:
        try:
            import yt_dlp
        except ImportError:
            with self._lock:
                self._state["status"] = "error"
                self._state["error"] = "未安装 yt-dlp：python -m pip install --user yt-dlp"
            return

        self.out_dir.mkdir(parents=True, exist_ok=True)

        opts = {
            "outtmpl": str(self.out_dir / "%(uploader)s" / "%(title).80s [%(id)s].%(ext)s"),
            "format_sort": QUALITY_SORT[self.quality],
            "merge_output_format": "mp4",
            "download_archive": str(self.out_dir / ".downloaded.txt"),
            "continuedl": True,
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "proxy": "",                      # B站直连，绕开系统代理
            "logger": _YdlLogger(self),       # 失败要能看见，不能静默吞掉
            "progress_hooks": [self._progress],
            "postprocessor_hooks": [self._postproc],
        }
        ff = ffmpeg_path()
        if ff:
            opts["ffmpeg_location"] = str(ff)
        ck = cookie_file()
        if ck:
            opts["cookiefile"] = str(ck)

        with self._lock:
            self._state["status"] = "running"
        self._log(f"开始下载 {len(self.urls)} 条 -> {self.out_dir}")
        if ff:
            self._log(f"ffmpeg: {ff}")
        else:
            self._log("⚠ 未找到 ffmpeg，无法合并音视频 —— 请把 ffmpeg.exe 放到程序目录的 bin/ 下")

        err = ""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download(self.urls)
        except _Cancelled:
            err = ""
        except Exception as e:
            err = str(e)[:200]
        finally:
            with self._lock:
                failed = list(self._state["failed"])
                n_fail = len(failed)
                if self._state["status"] == "running":
                    if err:
                        self._state["status"] = "error"
                        self._state["error"] = err
                        self._state["kind"] = "api"
                    elif n_fail:
                        joined = " ".join(failed)
                        risk = any(w.lower() in joined.lower() for w in RISK_WORDS)
                        self._state["kind"] = "risk" if risk else "api"
                        self._state["hint"] = (hints.RISK_TITLE if risk
                                               else "有视频没能下载")
                        self._state["steps"] = hints.RISK_STEPS if risk else []
                        self._state["error"] = (
                            f"{n_fail} 条失败"
                            + ("（像是被 B 站风控拦了）" if risk else ""))
                        # 一条都没成功才算彻底失败；部分成功保留 done
                        self._state["status"] = "done" if self._state["finished"] else "error"
                    else:
                        self._state["status"] = "done"
                        self._state["overall"] = 100.0
                ok_n = self._state["finished"]
                self._log(f"任务结束：成功 {ok_n} 条，失败 {n_fail} 条")
