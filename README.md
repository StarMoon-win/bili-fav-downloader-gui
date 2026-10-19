# B站收藏夹下载器 · 图形界面版

把 B 站收藏夹批量下载到本地。**桌面窗口和浏览器界面两种用法，功能完全一样，任选。**

不需要 Python，不需要装 ffmpeg：下载一个 exe 双击就能用。

> 这是图形界面版本；命令行 / AI 技能版在 [bili-fav-downloader](https://github.com/StarMoon-win/bili-fav-downloader)，核心逻辑相同。

---

## 下载：便携版 vs 安装包，怎么选

去 [Releases 页面](../../releases/latest) 下载，**两个都自带 ffmpeg、功能完全一样**，区别只在"怎么装到电脑上"：

|                  | 🎒 便携版 Portable                        | 📦 安装包 Setup                                  |
| ---------------- | -------------------------------------- | --------------------------------------------- |
| 文件名              | `BiliFavDownloader-Portable-1.2.0.exe` | `BiliFavDownloader-Setup-1.2.0.exe`           |
| 体积               | 约 54 MB                                | 约 43 MB                                       |
| 需要安装吗            | **不用**，下载完双击就能跑                       | 需要，跑一遍安装向导（约 30 秒）                            |
| 装到哪              | 你把它放在哪就在哪                              | 默认 `%LOCALAPPDATA%\Programs\BiliFavDownloader`，向导里可以改成任意路径 |
| 开始菜单 / 桌面快捷方式    | 没有（自己建）                                | 自动创建，可选桌面图标                                   |
| 启动速度             | 3–5 秒（每次启动要把 110 MB 解压到临时目录）            | **1 秒内**                                      |
| 写注册表             | 不写                                     | 写卸载信息                                        |
| 怎么卸载             | 直接删掉 exe                               | 设置 → 应用 → 卸载（会单独问一次要不要连登录信息一起删）              |
| 登录信息 / 配置放哪     | `%APPDATA%\BiliFavDownloader`（放 `config.json` 到 exe 旁边则改为便携模式） | `%APPDATA%\BiliFavDownloader`               |
| 适合谁              | 放 U 盘带走、临时用一下、不想在系统里留痕迹                | 长期使用、想要开始菜单图标、讨厌等启动                          |

**一句话建议**：只想试试就下**便携版**；打算常用就下**安装包**，启动快 3 倍不骗人。

> 系统要求：Windows 10 / 11（64 位）。
> 两个包都**没有代码签名**，Windows Defender / SmartScreen 可能提示"未知发布者"，选「更多信息 → 仍要运行」即可。

安装包或便携版跑起来后，双击图标 → 先弹窗让你选界面（桌面窗口 / 浏览器界面）→ 没登录会自动弹登录框。

---

## 两种界面

| 界面    | 启动方式                       | 特点                     |
| ----- | -------------------------- | ---------------------- |
| 桌面窗口  | `python launcher.py --gui` | 原生应用，可以直接选保存目录（系统目录选择框） |
| 浏览器界面 | `python launcher.py --web` | 界面更精致，可多标签页，适合大屏幕       |

不带参数运行 `python launcher.py` 会弹窗让你选。打包成 exe 后双击也一样。

---

## 功能

- **登录自助搞定**：扫码登录（手机 B 站 App 扫一下就行），或者直接粘贴浏览器里的 Cookie
- **内置 ffmpeg**：下载完直接合并出 mp4，不用自己装
- 收藏夹下拉切换，自动读取全部条目
- 列表勾选（全选 / 全不选 / 反选 / 按标题和 UP 主搜索）
- 下载前显示总时长和预估体积，**别在体积上踩坑**（有些收藏夹几十条就 848 GB）
- 四档画质：4K HEVC / 4K AV1 / 4K 最高码率 / 1080P
- **视频 / 音频二选一**：可以只下视频（MP4），也可以只提取音频（MP3 192kbps）—— 只想听歌、存播客或做素材时不用把几 GB 的视频一起拖下来
- 实时进度、速度、剩余时间
- 增量下载（已下过的自动跳过，中断后能续）
- **按链接下载**：粘贴 BV 号 / 视频链接直接下，不读收藏夹接口（风控时的备用通道）
- **被风控时给明确提示**：告诉你触发了什么、为什么、怎么解，而不是甩一个 `412`

---

## 从源码运行

### 1. 装依赖

```bash
python -m pip install --user -r requirements.txt
```

或手动：

```bash
python -m pip install --user yt-dlp flask requests segno
```

`segno` 是纯 Python 二维码库，只用来画扫码登录的二维码（约 60 KB）。

ffmpeg 必需（B 站音视频分开存，要合并）：

```bash
python -m pip install --user imageio-ffmpeg
```

然后找到包里的 `binaries/ffmpeg-win-x86_64-*.exe`，复制到项目下 `bin/ffmpeg.exe`。
（exe 版本已经自带 ffmpeg，这段只针对源码运行。）

### 2. 登录

私密收藏夹、4K / 大会员画质都需要登录。程序启动后如果没登录，会自动弹登录框：

**方式 A：扫码（推荐，5 秒）** — 点「登录」→ 手机 B 站 App 扫码 → 手机点确认 → 完成。

**方式 B：粘贴 Cookie（扫码不灵时用）**

1. 浏览器打开 bilibili.com 并登录
2. `F12` → Network（网络）→ 刷新页面 → 点任意一条 bilibili.com 请求
3. Request Headers 里找到 `Cookie:`，**整行复制**（从 `SESSDATA=` 开始）
4. 粘进「粘贴 Cookie」页，点「验证并保存」

分号分隔、Netscape cookies.txt、JSON 三种格式都能自动识别，程序会先向 B 站校验通过才落盘。

> `cookies.txt` 等同登录凭证，**不要提交到仓库或分享给别人**。

**为什么不能用"从浏览器读 Cookie"**：Chrome / Edge 127+ 的 App-Bound 加密把密钥绑在浏览器进程里，
外部程序解不开（`Failed to decrypt with DPAPI`）。所以只能扫码或手动复制。

### 3. 运行

```bash
python launcher.py           # 弹窗选择
python launcher.py --gui     # 直接开桌面窗口
python launcher.py --web     # 直接开浏览器（自动打开 http://127.0.0.1:8765）
```

---

## 被风控了怎么办

B 站风控返回 `HTTP 412`（有时是接口码 `-412` / `-352` / `-509`），意思是
「你这次请求太像爬虫，先停一下」。程序会直接把原因和解决步骤列在界面上。核心几条：

1. **停手，等 10–30 分钟**（严重时 2–24 小时）。期间别反复点「刷新」「重载列表」，越点锁得越久。
2. **用浏览器打开 bilibili.com 播个视频**。如果浏览器也打不开 / 一直转圈，说明是 IP 被限，
   切手机热点或换网络。
3. **重新登录一次**。旧 Cookie 失效时，B 站会把它当异常流量。
4. **关掉代理 / VPN / 加速器**。B 站对代理 IP 特别敏感，直连最稳。
5. **急着要视频就用「按链接下载」**，把 BV 号或链接粘进去——这条路不碰被拦的收藏夹接口。

程序本身做了两层防护：

- **限速**：每个请求间隔约 0.5 秒 + 随机抖动，不是闷头狂翻页；
- **自动降级**：收藏夹列表接口一旦 412，自动改用 `fav/resource/ids` 拿 BV 号，再逐条补标题和时长。

其他错误也有对应提示：`-101` 未登录 / Cookie 过期、`-403` 无权限（私密收藏夹）、
`62002` / `62012` 视频已失效、网络不通等。

---

## 配置

项目根目录的 `config.json`（可选）：

```json
{
  "cookies": "D:\\tools\\cookies.txt",
  "tools_dir": "D:\\tools",
  "out_dir": "D:\\downloads\\bili"
}
```

| 字段          | 说明                                      |
| ----------- | --------------------------------------- |
| `cookies`   | cookies.txt 路径，不填则找项目根目录的 `cookies.txt` |
| `tools_dir` | ffmpeg / BBDown 所在目录                    |
| `out_dir`   | 默认保存目录，不填则是 `~/Downloads/bili`          |

exe 版本会依次看：exe 旁边的 `config.json`（便携模式）→ `%APPDATA%\BiliFavDownloader\config.json`。

---

## 数据放哪

| 内容                | 位置                                          |
| ----------------- | ------------------------------------------- |
| 登录态 `cookies.txt` | `%APPDATA%\BiliFavDownloader\cookies.txt`   |
| 配置 `config.json`  | 同上；**exe 旁边有 `config.json` 则优先用它**（便携模式）    |
| 收藏夹缓存             | `%APPDATA%\BiliFavDownloader\.cache\`       |

用户数据一律走 `%APPDATA%`，所以就算装进 `C:\Program Files`（只读），登录也能正常写。
卸载时会单独问一次「要不要连登录信息一起删」。

---

## 自己打包

```bash
python -m pip install --user pyinstaller
python make_icon.py            # 生成图标（只需跑一次，产物已在 assets/）
python build.py --all          # 便携版 + 目录版 + 安装包
```

产物在 `dist/`：

| 产物                                  | 体积     | 说明                                 |
| ----------------------------------- | ------ | ---------------------------------- |
| `BiliFavDownloader.exe`             | 约 54 MB | **便携版**：单文件、ffmpeg 内置、双击即用，不写注册表  |
| `BiliFavDownloader-Setup-1.2.0.exe` | 约 43 MB | **安装包**：可选安装路径，开始菜单 / 桌面快捷方式 + 卸载程序 |
| `build/onedir/BiliFavDownloader/`   | 约 130 MB | 目录版（安装包的源），启动 1 秒内                  |

单文件版冷启动 3–5 秒，目录版 1 秒内——**这就是为什么要出安装包**。

ffmpeg 查找顺序：`bin/ffmpeg.exe`（exe 旁边）→ 打包内置 → `config.json` 的 `tools_dir` → `PATH`。
想要小一点的包可以 `python build.py --no-ffmpeg`，但要自己把 `ffmpeg.exe` 放进 `bin/`。

安装包用 [Inno Setup](https://jrsoftware.org/isdl.php) 生成，脚本在 `installer/setup.iss`，
中文界面（语言包 `installer/ChineseSimplified.isl`，**必须存成 UTF-8 BOM**）。
默认装到当前用户的 `%LOCALAPPDATA%\Programs\BiliFavDownloader`，**不需要管理员权限**。

---

## 项目结构

```
bili-fav-downloader-gui/
├── launcher.py          统一入口（选择界面）
├── build.py             打包脚本（便携版 / 目录版 / 安装包）
├── make_icon.py         生成程序图标
├── requirements.txt     源码运行依赖
├── assets/
│   └── icon.ico         程序图标
├── installer/
│   ├── setup.iss        Inno Setup 安装包脚本
│   └── ChineseSimplified.isl
├── core/
│   ├── config.py        路径与配置解析（程序目录 vs 数据目录）
│   ├── auth.py          登录态：扫码 / 粘贴 Cookie / 校验 / 登出
│   ├── hints.py         给用户看的说明文案（风控、登录），只维护一份
│   ├── bili_api.py      收藏夹 API（限速、错误分类、风控降级）
│   └── downloader.py    下载任务（yt-dlp Python API + 进度钩子）
├── web/
│   └── app.py           Flask 后端
├── gui/
│   └── app.py           Tkinter 界面（含登录对话框）
└── static/
    └── index.html       前端页面（含登录弹窗、风控提示面板）
```

**两个界面共用 `core/`**，改逻辑只需改一处；提示文案在 `core/hints.py`，
两个界面读同一份，不会出现「桌面版说得清楚、网页版糊弄」。

---

## 已知限制

- 浏览器界面不能弹系统目录选择框（浏览器安全限制），只能手填路径；桌面窗口可以
- 已失效的视频无法下载（接口报 `62002` / `62012`）
- 收藏夹特别大（上千条）时首次读取较慢，之后有 1 小时本地缓存
- Chrome/Edge 127+ 的 cookie 无法被外部程序读取，只能用扫码或 F12 复制
- **便携版冷启动约 4 秒**（每次解压 110 MB 到临时目录）；要快就用安装包
- exe 没有代码签名，Defender 可能误报，加信任即可

---

## License

MIT © 2026 StarMoon-win
