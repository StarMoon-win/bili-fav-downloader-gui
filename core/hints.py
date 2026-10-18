# -*- coding: utf-8 -*-
"""给用户看的说明文案：怎么登录、被风控了怎么办。

集中放一处，Web / Tkinter / 命令行都用同一份，避免文案各写一套。
"""

# ---------------- 登录 ----------------

LOGIN_TITLE = "需要登录 B 站账号"

LOGIN_STEPS = [
    "推荐用「扫码登录」：点开手机 B 站 App → 右上角扫一扫 → 确认登录，全程 5 秒。",
    "扫码不行就用「粘贴 Cookie」：浏览器打开 bilibili.com 并登录 → 按 F12 → "
    "切到 Network（网络）面板 → 刷新页面 → 点任意一条 bilibili.com 的请求 → "
    "在 Request Headers 里找到 Cookie: 那一行，整行复制（从 SESSDATA= 开始到行尾）。",
    "把复制的内容原样粘进输入框即可，不用管格式 —— 分号分隔、Netscape、JSON 三种都能自动识别。",
    "Cookie 等同于密码，不要发给别人；本工具只保存在本机 cookies.txt，不上传任何地方。",
]

PASTE_PLACEHOLDER = (
    "把浏览器里复制的 Cookie 粘到这里，例如：\n"
    "SESSDATA=xxxxxxxx%2Cxxxxxxxxxx%2Cxxxxx%2Cxx; bili_jct=xxxxxxxx; "
    "DedeUserID=1234567; DedeUserID__ckMd5=xxxxxxxx; sid=xxxxx"
)

# ---------------- 风控 ----------------

RISK_TITLE = "触发了 B 站风控"

RISK_REASON = (
    "B 站判定当前请求「太像爬虫」：短时间翻页太密集、Cookie 已失效、"
    "或者当前 IP（含代理 / VPN 出口）被标记了。"
)

RISK_STEPS = [
    "立刻停手，等 10–30 分钟再试（严重时 2–24 小时）。期间别反复点「刷新」「重载列表」，"
    "越点风控越久。",
    "用浏览器打开 bilibili.com，随便点开一个视频播放一下。如果浏览器也打不开 / 一直转圈，"
    "说明是 IP 被限，切手机热点或换网络。",
    "重新登录一次（右上角「登录」→ 扫码）。旧 Cookie 失效时，B 站会把它当异常流量。",
    "关掉代理 / VPN / 加速器再试。B 站对代理 IP 特别敏感，直连最稳。",
    "着急要视频：用「按链接下载」，把 BV 号或视频链接粘进去。这条路不读收藏夹列表接口，"
    "绕开的就是被风控的那个接口。",
]

RISK_TIP = (
    "本工具已自动加了请求间隔（约 0.5 秒 + 随机抖动），正常用不会触发；"
    "只有连续翻几十页、或者同一时间开多个窗口才会。"
)

# 服务端额外风控码
RISK_CODES = {
    -412: "请求被拦截（-412）",
    -352: "风控校验失败（-352），通常是 buvid3 / b_nut 这类设备指纹缺失",
    -509: "请求过于频繁（-509）",
    -799: "请求过于频繁（-799）",
    412: "请求被拦截（412）",
}

AUTH_STEPS = [
    "点右上角「登录」，用手机 B 站扫码，或粘贴浏览器里的 Cookie。",
    "如果刚登录过还是提示未登录，说明 Cookie 已过期（B 站一般 30 天），重新登录即可。",
    "确认本机时间准确。系统时间偏差超过几分钟，Cookie 会被判无效。",
]

NETWORK_STEPS = [
    "检查网络是否通：浏览器能否打开 bilibili.com。",
    "如果开着代理 / VPN，先关掉再试（B 站直连更稳）。",
    "公司 / 学校网络可能拦截，换手机热点试试。",
]

FORBIDDEN_STEPS = [
    "这个收藏夹可能是私密的，需要用「收藏夹的主人」账号登录后才能读。",
    "确认账号有权限后，点右上角重新登录一次。",
]

NOTFOUND_STEPS = [
    "收藏夹可能已被删除，或者链接 / ID 填错了。",
    "刷新一下收藏夹列表再选一次。",
]

GENERIC_STEPS = [
    "先点「刷新」重试一次。",
    "还不行就重新登录，或者换「按链接下载」。",
]

# kind -> (标题, 步骤)
KIND_HELP = {
    "auth": (LOGIN_TITLE, AUTH_STEPS),
    "risk": (RISK_TITLE, RISK_STEPS),
    "network": ("网络请求失败", NETWORK_STEPS),
    "forbidden": ("没有访问权限", FORBIDDEN_STEPS),
    "notfound": ("内容不存在", NOTFOUND_STEPS),
    "api": ("B 站接口返回错误", GENERIC_STEPS),
}


def help_for(kind: str) -> tuple[str, list[str]]:
    return KIND_HELP.get(kind, ("出错了", GENERIC_STEPS))
