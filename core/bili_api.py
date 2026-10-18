# -*- coding: utf-8 -*-
"""B 站收藏夹 API 封装（不依赖 yt-dlp，直接调官方接口）

两个设计要点：

* **限速**：每个请求之间强制间隔 ~0.5 秒 + 随机抖动。B 站的 412 风控
  就是「翻页太快」触发的，限速是最有效的预防。
* **降级**：收藏夹列表接口（fav/resource/list）最容易被风控，
  一旦 412 就自动改用 fav/resource/ids 拿 BV 号，再用 view 接口补标题。
  这条路慢一些，但能绕开被拦的那个接口。
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from pathlib import Path

import requests

from . import hints
from .auth import load_cookies
from .config import data_dir

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

API = "https://api.bilibili.com"
LIST_URL = f"{API}/x/v3/fav/resource/list"
IDS_URL = f"{API}/x/v3/fav/resource/ids"
VIEW_URL = f"{API}/x/web-interface/view"
NAV_URL = f"{API}/x/web-interface/nav"
FOLDERS_URL = f"{API}/x/v3/fav/folder/created/list-all"

# 各画质档位的经验码率（MB/s），用于体积估算
QUALITY_RATE = {
    "4k-av1": 0.60,
    "4k-hevc": 1.00,
    "4k": 1.50,
    "1080": 0.45,
}

# 请求间隔（秒）。0.5 + 0~0.25 抖动
MIN_INTERVAL = 0.5

# 风控类返回码
RISK_CODES = {-412, -352, -509, -799, 412}


class BiliError(Exception):
    """带分类和「怎么办」的错误。

    kind: auth / risk / network / forbidden / notfound / api
    steps: 给用户看的解决步骤
    retry_after: 建议等待秒数（风控用）
    """

    def __init__(self, msg: str, kind: str = "api", code=None,
                 hint: str = "", steps: list[str] | None = None,
                 retry_after: int = 0) -> None:
        super().__init__(msg)
        self.kind = kind
        self.code = code
        self.retry_after = retry_after
        title, default_steps = hints.help_for(kind)
        self.hint = hint or title
        self.steps = steps if steps is not None else default_steps

    def payload(self) -> dict:
        return {"error": str(self), "kind": self.kind, "code": self.code,
                "hint": self.hint, "steps": self.steps,
                "retry_after": self.retry_after}


def _risk_error(msg: str, code=None, retry_after: int = 900) -> BiliError:
    return BiliError(msg, kind="risk", code=code, hint=hints.RISK_TITLE,
                     steps=hints.RISK_STEPS, retry_after=retry_after)


def _classify_code(code: int, message: str) -> BiliError:
    msg = f"B 站接口返回 {code}: {message or '未知错误'}"
    if code == -101:
        return BiliError(msg, kind="auth", code=code, hint=hints.LOGIN_TITLE)
    if code in RISK_CODES:
        detail = hints.RISK_CODES.get(code, "")
        return _risk_error(f"{msg}（{detail}）" if detail else msg, code=code)
    if code == -403:
        return BiliError(msg, kind="forbidden", code=code)
    if code in (-404, 62002, 62012):
        return BiliError(msg, kind="notfound", code=code)
    return BiliError(msg, kind="api", code=code)


class BiliClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(HEADERS)
        self.reload_cookies()
        self._cache_dir = data_dir() / ".cache"
        self._throttle_lock = threading.Lock()
        self._last_req = 0.0

    # ---------- 登录态 ----------
    def reload_cookies(self) -> dict:
        """重新从 cookies.txt 读登录态（登录 / 登出后调用）"""
        ck = load_cookies()
        self.session.cookies.clear()
        if ck:
            self.session.cookies.update(ck)
        return ck

    @property
    def logged_in(self) -> bool:
        return bool(self.session.cookies.get("SESSDATA"))

    # ---------- 底层请求 ----------
    def _throttle(self) -> None:
        with self._throttle_lock:
            gap = MIN_INTERVAL + random.uniform(0, 0.25)
            wait = self._last_req + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_req = time.time()

    def _api(self, url: str, params: dict | None = None, retries: int = 3,
             risk_waits: tuple[int, ...] = (20,)) -> object:
        """请求一个 B 站接口，返回 data 字段。

        risk_waits：遇到 412 时依次等待的秒数（空元组 = 不重试，直接抛）。
        """
        delay = 1.0
        last: Exception | None = None
        waits = list(risk_waits)

        for i in range(retries):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=20)
            except requests.RequestException as e:
                last = e
                if i == retries - 1:
                    break
                time.sleep(delay)
                delay *= 2
                continue

            if r.status_code == 412:
                if waits:
                    time.sleep(waits.pop(0))
                    continue
                raise _risk_error("触发 B 站风控（HTTP 412）", code=412)
            if r.status_code == 429:
                if waits:
                    time.sleep(waits.pop(0))
                    continue
                raise _risk_error("请求过于频繁（HTTP 429）", code=429, retry_after=600)
            if r.status_code in (401, 403):
                raise BiliError(f"没有访问权限（HTTP {r.status_code}）",
                                kind="forbidden", code=r.status_code)
            if r.status_code != 200:
                last = BiliError(f"HTTP {r.status_code}", kind="network",
                                 code=r.status_code)
                if i == retries - 1:
                    break
                time.sleep(delay)
                delay *= 2
                continue

            try:
                j = r.json()
            except Exception:
                raise BiliError("B 站返回了非 JSON 内容（可能被劫持或需要验证）",
                                kind="network")

            code = j.get("code")
            if code == 0:
                return j.get("data")
            err = _classify_code(code, j.get("message", ""))
            if err.kind == "risk" and waits:
                time.sleep(waits.pop(0))
                continue
            raise err

        if isinstance(last, BiliError):
            raise last
        raise BiliError(f"请求失败：{last}", kind="network")

    # ---------- 账号 ----------
    def account(self) -> dict:
        try:
            d = self._api(NAV_URL) or {}
        except BiliError as e:
            if e.kind == "auth":
                return {"is_login": False, "uname": "", "mid": 0, "vip": False,
                        "error": str(e)}
            raise
        return {
            "is_login": bool(d.get("isLogin")),
            "uname": d.get("uname", ""),
            "mid": d.get("mid", 0),
            "vip": d.get("vipStatus", 0) == 1,
            "level": (d.get("level_info") or {}).get("current_level", 0),
            "face": d.get("face", ""),
        }

    # ---------- 收藏夹 ----------
    def folders(self) -> list[dict]:
        acc = self.account()
        if not acc["is_login"]:
            raise BiliError("未登录，读不到收藏夹列表", kind="auth", code=-101,
                            hint=hints.LOGIN_TITLE)
        d = self._api(FOLDERS_URL, {"up_mid": acc["mid"], "type": 2, "rid": 0,
                                    "web_location": "333.1387"}) or {}
        out = []
        for f in d.get("list") or []:
            out.append({
                "id": f["id"],
                "title": f["title"],
                "count": f["media_count"],
                "private": bool(f["attr"] & 1),
            })
        return out

    def _cache_path(self, fid: int) -> Path:
        self._cache_dir.mkdir(exist_ok=True)
        return self._cache_dir / f"fav_{fid}.json"

    def medias(self, fid: int, refresh: bool = False,
               on_progress=None) -> list[dict]:
        """读收藏夹内容。列表接口被风控时自动降级到 ids + view。"""
        cache = self._cache_path(fid)
        if not refresh and cache.exists() and time.time() - cache.stat().st_mtime < 3600:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                pass

        try:
            items = self._medias_via_list(fid, on_progress)
        except BiliError as e:
            if e.kind != "risk":
                raise
            if on_progress:
                on_progress("收藏夹列表接口被风控，自动改用 ids 接口…")
            items = self._medias_via_ids(fid, on_progress)

        try:
            cache.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return items

    def _medias_via_list(self, fid: int, on_progress=None) -> list[dict]:
        items, pn = [], 1
        while True:
            d = self._api(LIST_URL, {
                "media_id": fid, "pn": pn, "ps": 20, "platform": "web",
                "order": "mtime", "type": 0, "tid": 0,
            }, risk_waits=()) or {}
            batch = d.get("medias") or []
            if not batch:
                break
            for m in batch:
                items.append({
                    "bvid": m.get("bvid", ""),
                    "title": m.get("title", ""),
                    "duration": m.get("duration") or 0,
                    "upper": (m.get("upper") or {}).get("name", ""),
                })
            if on_progress and pn % 5 == 0:
                on_progress(f"已读取 {len(items)} 条…")
            if not d.get("has_more"):
                break
            pn += 1
        return items

    def _medias_via_ids(self, fid: int, on_progress=None) -> list[dict]:
        """风控逃生路线：ids 接口只返 bvid，标题时长再逐条补"""
        d = self._api(IDS_URL, {"media_id": fid}, risk_waits=(15, 45))
        raw = d if isinstance(d, list) else (d or {}).get("data") or []
        bvids = [x.get("bvid") or x.get("bv_id") for x in raw]
        bvids = [b for b in bvids if b]
        if not bvids:
            # 空收藏夹：不是错误，正常返回空列表（无权限的情况接口会给 -403）
            return []

        items: list[dict] = []
        fails = 0
        for n, bv in enumerate(bvids, 1):
            try:
                v = self._api(VIEW_URL, {"bvid": bv}, retries=2, risk_waits=()) or {}
                items.append({
                    "bvid": bv,
                    "title": v.get("title", bv),
                    "duration": v.get("duration") or 0,
                    "upper": (v.get("owner") or {}).get("name", ""),
                })
                fails = 0
            except BiliError as e:
                fails += 1
                # 单条取不到（稿件失效）不算事，但连续失败说明是被系统性拦了
                if e.kind in ("risk", "network") and fails >= 5:
                    raise
                items.append({"bvid": bv, "title": bv, "duration": 0, "upper": ""})
            if on_progress and n % 10 == 0:
                on_progress(f"补全信息 {n}/{len(bvids)}…")
        return items

    # ---------- 估算 ----------
    @staticmethod
    def estimate(items: list[dict], quality: str = "4k-hevc") -> dict:
        total_sec = sum(i["duration"] for i in items)
        rate = QUALITY_RATE.get(quality, 1.0)
        return {
            "count": len(items),
            "total_sec": total_sec,
            "total_hours": round(total_sec / 3600, 1),
            "size_gb": round(total_sec * rate / 1024, 1),
        }


def fmt_duration(sec: int) -> str:
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------- 链接解析（按 BV 号下载用） ----------
_BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
_AV_RE = re.compile(r"(?:^|[^0-9a-zA-Z])av(\d{1,12})", re.I)
_SHORT_RE = re.compile(r"https?://b23\.tv/\S+")


def parse_links(text: str) -> list[str]:
    """从一堆文本里揪出 BV 号 / av 号，返回去重后的 URL 列表。

    支持：完整链接、短链 b23.tv（原样保留，yt-dlp 会自己跳）、
    BV 号裸串、av 号、每行一个或混在一起都行。
    """
    urls: list[str] = []
    seen: set[str] = set()

    def add(u: str, key: str) -> None:
        if key not in seen:
            seen.add(key)
            urls.append(u)

    for bv in _BV_RE.findall(text or ""):
        add(f"https://www.bilibili.com/video/{bv}", bv)
    for av in _AV_RE.findall(text or ""):
        add(f"https://www.bilibili.com/video/av{av}", f"av{av}")
    for m in _SHORT_RE.findall(text or ""):
        add(m.rstrip("，。,.)）"), m)
    return urls
