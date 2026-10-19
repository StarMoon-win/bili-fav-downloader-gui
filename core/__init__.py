# -*- coding: utf-8 -*-
"""B站收藏夹下载器 - 核心逻辑（Web 与桌面界面共用）"""
__version__ = "1.2.0"

from . import auth, hints
from .bili_api import (QUALITY_RATE, BiliClient, BiliError, fmt_duration,
                       parse_links)
from .config import (app_dir, cookie_file, cookie_target, data_dir,
                     default_out, ffmpeg_path, save_config, ytdlp_cmd)
from .downloader import QUALITY_SORT, DownloadTask

__all__ = [
    "__version__",
    "BiliClient", "BiliError", "fmt_duration", "QUALITY_RATE", "parse_links",
    "DownloadTask", "QUALITY_SORT",
    "app_dir", "cookie_file", "cookie_target", "data_dir", "default_out",
    "ffmpeg_path", "save_config", "ytdlp_cmd",
    "auth", "hints",
]
