# -*- coding: utf-8 -*-
"""登录态管理：扫码登录 / 粘贴 Cookie / 校验 / 登出。

B 站现在有三种拿登录态的路子，按可靠性排序：

1. 官方扫码接口（passport-login/web/qrcode）—— 本模块实现，最省事；
2. 浏览器 F12 复制 Cookie —— 万能兜底，扫码挂了还能用；
3. --cookies-from-browser —— 已失效，Chrome/Edge 127+ 的 App-Bound
   加密把密钥绑在浏览器进程里，外部程序解不开（DPAPI 报错）。

所以只提供 1 和 2，别再加 3。
"""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path

import requests

from . import hints
from .config import cookie_target

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
QR_GEN_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

# 写进 cookies.txt 的过期时间：2033 年。真实有效期由服务端 SESSDATA 决定，
# 这里只是防止 cookie jar 因为本地时间判断把它当过期丢掉。
COOKIE_EXPIRES = 1990000000

# 必须有的字段，缺了说明粘贴的内容不是登录态
REQUIRED = ("SESSDATA",)

# 扫码轮询的状态码
QR_STATE = {
    0: ("ok", "登录成功"),
    86101: ("wait", "等待扫码"),
    86090: ("scan", "已扫码，请在手机上确认"),
    86038: ("expired", "二维码已过期，请刷新"),
}


class AuthError(Exception):
    """登录相关错误。hint 是给用户看的下一步建议。"""

    def __init__(self, msg: str, hint: str = "", steps: list[str] | None = None) -> None:
        super().__init__(msg)
        self.hint = hint
        self.steps = steps or hints.AUTH_STEPS

    def payload(self) -> dict:
        return {"error": str(self), "kind": "auth", "hint": self.hint,
                "steps": self.steps, "code": -101, "retry_after": 0}


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False          # 绕开系统代理，B 站直连最稳
    s.headers.update(HEADERS)
    return s


# ==================== Cookie 解析 ====================

def _from_json(obj) -> dict:
    ck: dict[str, str] = {}
    if isinstance(obj, dict):
        # {"SESSDATA": "..."} 或 {"cookies": [...]}
        if isinstance(obj.get("cookies"), list):
            return _from_json(obj["cookies"])
        for k, v in obj.items():
            if isinstance(v, str):
                ck[str(k)] = v
    elif isinstance(obj, list):
        for it in obj:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("key") or it.get("Name")
            value = it.get("value") or it.get("Value")
            if name and value is not None:
                ck[str(name)] = str(value)
    return ck


def _from_netscape(text: str) -> dict:
    ck: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip("\r\n")
        if not line or line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) >= 7:
            ck[parts[5]] = parts[6]
    return ck


def _from_header(text: str) -> dict:
    ck: dict[str, str] = {}
    for chunk in re.split(r"[;\n\r]+", text):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        k, _, v = chunk.partition("=")
        k, v = k.strip(), v.strip().strip('"')
        if k and v and not k.lower().startswith(("path", "domain", "expires", "max-age",
                                                "secure", "httponly", "samesite")):
            ck[k] = v
    return ck


def parse_cookie_text(raw: str) -> dict:
    """把用户粘贴的内容解析成 {name: value}。

    支持四种形态，随便哪种都能吃：
      * 浏览器 Request Headers 里的整行 Cookie（分号分隔）
      * Netscape cookies.txt 全文（Tab 分隔）
      * Cookie-Editor / EditThisCookie 导出的 JSON
      * 单个 SESSDATA=xxx
    """
    text = (raw or "").strip().lstrip("\ufeff")
    if not text:
        raise AuthError("粘贴的内容是空的", hint="先把 Cookie 复制下来再粘")

    text = re.sub(r"(?is)^\s*cookie\s*:\s*", "", text)

    ck: dict = {}
    if text[:1] in "{[":
        try:
            ck = _from_json(json.loads(text))
        except Exception:
            ck = {}
    if not ck and "\t" in text:
        ck = _from_netscape(text)
    if not ck:
        ck = _from_header(text)

    if not ck:
        raise AuthError("没解析出任何 Cookie 字段",
                        hint="复制时要从 SESSDATA= 开始，整行一起复制")

    missing = [k for k in REQUIRED if not ck.get(k)]
    if missing:
        raise AuthError(
            f"缺少关键字段 {'、'.join(missing)}，这不是完整的登录态",
            hint="重新复制一次：F12 → Network → 任意 bilibili.com 请求 → "
                 "Request Headers 里的 Cookie 整行（SESSDATA 必须有）",
        )
    return ck


def to_netscape(ck: dict, domain: str = ".bilibili.com") -> str:
    lines = [
        "# Netscape HTTP Cookie File",
        "# 由 BiliFavDownloader 自动生成，可直接给 yt-dlp / curl 使用",
        "# 注意：这个文件等同于你的 B 站登录凭证，不要外传",
        "",
    ]
    for name, value in ck.items():
        if not name or value is None:
            continue
        value = str(value).replace("\t", "").replace("\n", "").replace("\r", "")
        lines.append("\t".join([domain, "TRUE", "/", "FALSE",
                                str(COOKIE_EXPIRES), str(name), value]))
    return "\n".join(lines) + "\n"


def load_cookies() -> dict:
    p = cookie_target()
    if not p.exists():
        return {}
    try:
        return _from_netscape(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


# ==================== 校验与保存 ====================

def verify(ck: dict, timeout: int = 15) -> dict:
    """用给定 Cookie 请求 nav 接口，确认登录态有效并拿到账号信息"""
    if not ck:
        raise AuthError("还没有登录", hint="点「扫码登录」或用「粘贴 Cookie」")
    s = _session()
    s.cookies.update(ck)
    try:
        r = s.get(NAV_URL, timeout=timeout)
    except requests.RequestException as e:
        raise AuthError(f"网络请求失败：{e}",
                        hint="检查网络，或先关掉代理 / VPN", steps=hints.NETWORK_STEPS)
    if r.status_code == 412:
        raise AuthError("校验登录态时被 B 站风控拦截（412）",
                        hint=hints.RISK_TITLE, steps=hints.RISK_STEPS)
    try:
        j = r.json()
    except Exception:
        raise AuthError(f"B 站返回了非 JSON 内容（HTTP {r.status_code}）",
                        steps=hints.NETWORK_STEPS)
    if j.get("code") != 0:
        raise AuthError(f"B 站接口报错 {j.get('code')}: {j.get('message')}")
    d = j.get("data") or {}
    if not d.get("isLogin"):
        raise AuthError(
            "Cookie 无效或已过期",
            hint="B 站的 SESSDATA 一般 30 天有效。重新扫码登录，或重新复制一次 Cookie。"
                 "另外确认电脑时间准确 —— 时间偏差太大会直接判无效。",
        )
    return {
        "is_login": True,
        "uname": d.get("uname", ""),
        "mid": d.get("mid", 0),
        "vip": d.get("vipStatus", 0) == 1,
        "vip_label": (d.get("vip_label") or {}).get("text", ""),
        "level": (d.get("level_info") or {}).get("current_level", 0),
        "face": d.get("face", ""),
    }


def save(ck: dict, path: Path | None = None) -> Path:
    """写入 cookies.txt（Netscape 格式），返回路径"""
    target = Path(path) if path else cookie_target()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_netscape(ck), encoding="utf-8")
    try:
        target.chmod(0o600)
    except Exception:
        pass
    return target


def save_from_text(raw: str) -> dict:
    """粘贴 → 解析 → 校验 → 落盘。失败抛 AuthError，不会写坏原文件。"""
    ck = parse_cookie_text(raw)
    acc = verify(ck)          # 先验证，通过才覆盖
    save(ck)
    return acc


def logout() -> None:
    """删除本地 cookies（不动浏览器里的）"""
    p = cookie_target()
    if p.exists():
        try:
            p.unlink()
        except Exception:
            p.write_text(to_netscape({}), encoding="utf-8")


def status() -> dict:
    """本地是否有 Cookie 文件（不联网）"""
    p = cookie_target()
    ck = load_cookies()
    return {
        "has_cookie": bool(ck.get("SESSDATA")),
        "path": str(p),
        "mtime": p.stat().st_mtime if p.exists() else 0,
        "keys": sorted(k for k in ck if k in ("SESSDATA", "bili_jct", "DedeUserID")),
    }


# ==================== 扫码登录 ====================

def qr_generate() -> dict:
    """申请一个登录二维码，返回 {key, url, svg}"""
    s = _session()
    try:
        r = s.get(QR_GEN_URL, timeout=15)
    except requests.RequestException as e:
        raise AuthError(f"申请二维码失败：{e}",
                        hint="检查网络，或改用「粘贴 Cookie」", steps=hints.NETWORK_STEPS)
    if r.status_code == 412:
        raise AuthError("申请二维码时被风控（412）", hint=hints.RISK_TITLE,
                        steps=hints.RISK_STEPS)
    j = r.json()
    if j.get("code") != 0:
        raise AuthError(f"申请二维码失败 {j.get('code')}: {j.get('message')}",
                        hint="换「粘贴 Cookie」这条路过")
    d = j["data"]
    url = d["url"]
    return {"key": d["qrcode_key"], "url": url, "svg": qr_svg(url)}


def _raw_query(qs: str) -> dict:
    """解析 query string 但**不解码** —— SESSDATA 里的 %2C 必须原样保留"""
    out: dict[str, str] = {}
    for part in qs.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        if k and v:
            out[k] = v
    return out


def qr_poll(key: str) -> dict:
    """轮询扫码状态。state: wait / scan / expired / ok"""
    if not key:
        raise AuthError("缺少二维码 key")
    s = _session()
    try:
        r = s.get(QR_POLL_URL, params={"qrcode_key": key, "source": "main-fe-header"},
                  timeout=15)
    except requests.RequestException as e:
        raise AuthError(f"轮询失败：{e}", steps=hints.NETWORK_STEPS)
    j = r.json()
    if j.get("code") != 0:
        raise AuthError(f"轮询失败 {j.get('code')}: {j.get('message')}")
    d = j.get("data") or {}
    code = d.get("code")
    state, msg = QR_STATE.get(code, ("error", d.get("message") or f"未知状态 {code}"))
    if state != "ok":
        return {"state": state, "message": msg}

    # 登录成功：Cookie 在返回 url 的 query 里（crossDomain 跳转地址）
    ck: dict[str, str] = {}
    url = d.get("url") or ""
    if "?" in url:
        ck.update(_raw_query(url.split("?", 1)[1]))
    for c in s.cookies:
        if c.name not in ck and c.value:
            ck[c.name] = c.value

    if not ck.get("SESSDATA"):
        raise AuthError("扫码成功但没拿到 SESSDATA",
                        hint="改用「粘贴 Cookie」，或稍后重试")
    acc = verify(ck)
    save(ck)
    return {"state": "ok", "message": "登录成功", "account": acc}


# ==================== 二维码渲染 ====================

def qr_matrix(url: str) -> list[list[int]]:
    """给 Tkinter 画布用的 0/1 矩阵"""
    import segno
    qr = segno.make(url, error="m")
    return [[1 if cell else 0 for cell in row] for row in qr.matrix]


def qr_svg(url: str, scale: int = 6) -> str:
    """给网页内联嵌入的 SVG（不带 xml 声明）"""
    import segno
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, border=2,
            dark="#0b0c10", light="#ffffff")
    svg = buf.getvalue().decode("utf-8", "replace")
    return re.sub(r"(?s)^\s*<\?xml[^>]*\?>\s*", "", svg).strip()


def qr_png_bytes(url: str, scale: int = 8) -> bytes:
    """备用：PNG 字节流"""
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def now() -> float:
    return time.time()
