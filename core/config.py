# -*- coding: utf-8 -*-
"""配置与路径解析（兼容 PyInstaller 打包后的运行环境）

两类目录要分清，混用会出问题：

* **程序目录 `BASE`** —— exe 所在目录，放只读资源（bin/、static/）。
  装到 `C:\\Program Files` 时这个目录**不可写**。
* **数据目录 `DATA`** —— 放 cookies.txt / config.json / 缓存。
  打包后固定用 `%APPDATA%\\BiliFavDownloader`，开发时就是项目目录。
"""
import json
import os
import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """程序所在目录：打包后是 exe 所在目录，否则是项目根目录"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """可写的数据目录（登录态、配置、缓存都放这儿）"""
    if not getattr(sys, "frozen", False):
        return app_dir()
    base = Path(os.environ.get("APPDATA") or Path.home())
    d = base / "BiliFavDownloader"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        return app_dir()


BASE = app_dir()
DATA = data_dir()


def config_file() -> Path:
    """配置文件位置：exe 旁边有就用它（便携模式），否则用数据目录"""
    portable = BASE / "config.json"
    if portable.exists():
        return portable
    return DATA / "config.json"


def load_config() -> dict:
    p = config_file()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


CFG = load_config()


def save_config(data: dict) -> None:
    """合并写入，不覆盖已有字段"""
    try:
        p = config_file()
        cur = load_config()
        cur.update(data)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _search_dirs() -> list[Path]:
    """找 ffmpeg 等外部程序的顺序：用户放的 > 打包内置的 > 配置的 > PATH"""
    dirs: list[Path] = [BASE / "bin", BASE]
    mei = getattr(sys, "_MEIPASS", None)          # 打包内置资源（onefile 临时目录 / onedir 的 _internal）
    if mei:
        dirs += [Path(mei) / "bin", Path(mei)]
    if CFG.get("tools_dir"):
        dirs.append(Path(CFG["tools_dir"]))
    if os.environ.get("BILI_TOOLS_DIR"):
        dirs.append(Path(os.environ["BILI_TOOLS_DIR"]))
    return dirs


def find_exe(*rel_paths: str) -> Path | None:
    for d in _search_dirs():
        for rp in rel_paths:
            p = d / rp
            if p.exists():
                return p
    hit = shutil.which(Path(rel_paths[-1]).name)
    return Path(hit) if hit else None


def ffmpeg_path() -> Path | None:
    return find_exe("ffmpeg/bin/ffmpeg.exe", "bin/ffmpeg.exe", "ffmpeg.exe")


def cookie_target() -> Path:
    """cookies 的「应该写到哪」。

    优先级：环境变量 > config.json 里已存在的路径 > 程序目录里的旧文件 >
    数据目录（打包后是 %APPDATA%\\BiliFavDownloader）。
    配置里指了个不存在的路径时不照写，避免在别人机器上写失败。
    """
    if os.environ.get("BILI_COOKIES"):
        return Path(os.environ["BILI_COOKIES"])
    cfg_p = CFG.get("cookies")
    if cfg_p and Path(cfg_p).exists():
        return Path(cfg_p)
    legacy = BASE / "cookies.txt"
    if legacy.exists():
        return legacy
    return DATA / "cookies.txt"


def cookie_file() -> Path | None:
    """实际可用的 cookies 文件；一个都没有返回 None"""
    p = cookie_target()
    if p.exists():
        return p
    for cand in (BASE / "cookies.txt", DATA / "cookies.txt",
                 BASE / "scripts" / "cookies.txt"):
        if cand.exists():
            return cand
    return None


def default_out() -> Path:
    p = CFG.get("out_dir")
    if p:
        return Path(p)
    return Path.home() / "Downloads" / "bili"


def ytdlp_cmd() -> list[str] | None:
    """返回调用 yt-dlp 的命令前缀"""
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        pass
    exe = find_exe("yt-dlp.exe")
    return [str(exe)] if exe else None
