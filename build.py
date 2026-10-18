# -*- coding: utf-8 -*-
"""
build.py — 一键打包（便携版 / 目录版 / 安装包）

用法:
    python build.py                  # 便携版：单文件 exe，内置 ffmpeg
    python build.py --no-ffmpeg      # 不内置 ffmpeg（体积小，需自备）
    python build.py --onedir         # 目录版（启动更快，安装包的源）
    python build.py --installer      # 打安装包（需要 Inno Setup）
    python build.py --all            # 便携版 + 目录版 + 安装包
    python build.py --console        # 保留控制台窗口（调试用）
    python build.py --ffmpeg <path>  # 手动指定 ffmpeg.exe

产物（dist/）:
    BiliFavDownloader.exe               便携版，双击即用
    BiliFavDownloader-Setup-<版本>.exe  安装包，可选安装路径
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "dist"
BUILD = BASE / "build"
NAME = "BiliFavDownloader"
ICON = BASE / "assets" / "icon.ico"


def _read_version() -> str:
    """版本号只在 core/__init__.py 维护一份，这里读出来用"""
    txt = (BASE / "core" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
    return m.group(1) if m else "0.0.0"


VERSION = _read_version()

ISCC_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(r"D:\AI-Models\tools\InnoSetup\ISCC.exe"),
]

HIDDEN = ["flask", "jinja2", "werkzeug", "core", "core.auth", "core.hints",
          "core.bili_api", "core.downloader", "core.config", "segno",
          "web.app", "gui.app"]
EXCLUDE = ["numpy", "pandas", "matplotlib", "PIL", "scipy", "test"]


# ---------------- 工具 ----------------
def find_ffmpeg(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"指定的 ffmpeg 不存在：{p}")
        return p
    cands = [BASE / "bin" / "ffmpeg.exe"]
    cfg = BASE / "config.json"
    if cfg.exists():
        try:
            c = json.loads(cfg.read_text(encoding="utf-8"))
            if c.get("tools_dir"):
                cands.append(Path(c["tools_dir"]) / "ffmpeg" / "bin" / "ffmpeg.exe")
                cands.append(Path(c["tools_dir"]) / "ffmpeg.exe")
        except Exception:
            pass
    cands.append(Path(r"D:\AI-Models\tools\ffmpeg\bin\ffmpeg.exe"))
    for p in cands:
        if p.exists():
            return p
    hit = shutil.which("ffmpeg")
    return Path(hit) if hit else None


def write_version_file() -> Path:
    parts = (VERSION.split(".") + ["0", "0"])[:3]
    major, minor, patch = parts
    p = BUILD / "version_info.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404B0', [
      StringStruct('CompanyName', 'StarMoon'),
      StringStruct('FileDescription', 'B站收藏夹下载器'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', '{NAME}'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', '{NAME}.exe'),
      StringStruct('ProductName', 'B站收藏夹下载器'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)""", encoding="utf-8")
    return p


def ensure_not_running() -> None:
    """PyInstaller 删不掉正在运行的旧 exe，提前拦一下并给出可执行的命令"""
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {NAME}.exe"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return
    if NAME.lower() in (out or "").lower():
        sys.exit(f"检测到 {NAME}.exe 正在运行，请先关掉窗口"
                 f"（或 taskkill /IM {NAME}.exe /F）再打包。")


def pyinstaller(mode: str, ffmpeg: Path | None, console: bool, distpath: Path) -> Path:
    ver = write_version_file()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(BASE / "launcher.py"),
        "--name", NAME,
        "--noconfirm", "--clean",
        "--add-data", f"{BASE / 'static'};static",
        "--icon", str(ICON),
        "--version-file", str(ver),
        "--distpath", str(distpath),
        "--workpath", str(BUILD / f"work-{mode}"),
        "--specpath", str(BUILD),
    ]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    for e in EXCLUDE:
        cmd += ["--exclude-module", e]
    if ffmpeg:
        cmd += ["--add-data", f"{ffmpeg};bin"]
    cmd.append("--onedir" if mode == "onedir" else "--onefile")
    if not console:
        cmd.append("--windowed")

    print(f"\n=== 打包 {mode}（{'内置 ffmpeg' if ffmpeg else '不含 ffmpeg'}）===")
    r = subprocess.run(cmd, cwd=BASE)
    if r.returncode != 0:
        sys.exit(f"打包失败，退出码 {r.returncode}")

    target = (distpath / NAME) if mode == "onedir" else (distpath / f"{NAME}.exe")
    if not target.exists():
        sys.exit(f"打包产物不存在：{target}")
    return target


def build_installer(src_dir: Path) -> Path | None:
    iscc = next((p for p in ISCC_CANDIDATES if p.exists()), None)
    if not iscc:
        print("\n[跳过] 没找到 Inno Setup（ISCC.exe）。")
        print("       装一个：winget install JRSoftware.InnoSetup")
        print("       或手动下载 https://jrsoftware.org/isdl.php")
        return None

    DIST.mkdir(parents=True, exist_ok=True)
    cmd = [str(iscc),
           f"/DMyAppVersion={VERSION}",
           f"/DSourceDir={src_dir}",
           f"/DOutputDir={DIST}",
           str(BASE / "installer" / "setup.iss")]
    print("\n=== 打安装包 ===")
    r = subprocess.run(cmd, cwd=BASE)
    if r.returncode != 0:
        print(f"安装包制作失败（退出码 {r.returncode}）")
        return None
    out = DIST / f"{NAME}-Setup-{VERSION}.exe"
    return out if out.exists() else None


def human(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


# ---------------- 主流程 ----------------
def main() -> None:
    ap = argparse.ArgumentParser(description="打包 B站收藏夹下载器")
    ap.add_argument("--onedir", action="store_true", help="打成目录（启动更快）")
    ap.add_argument("--installer", action="store_true", help="打安装包")
    ap.add_argument("--all", action="store_true", help="便携版 + 目录版 + 安装包")
    ap.add_argument("--no-ffmpeg", action="store_true", help="不内置 ffmpeg")
    ap.add_argument("--ffmpeg", help="指定 ffmpeg.exe 路径")
    ap.add_argument("--console", action="store_true", help="保留控制台（调试）")
    args = ap.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("缺少 PyInstaller：python -m pip install --user pyinstaller")

    ensure_not_running()
    DIST.mkdir(parents=True, exist_ok=True)

    ffmpeg = None if args.no_ffmpeg else find_ffmpeg(args.ffmpeg)
    if not args.no_ffmpeg and not ffmpeg:
        print("⚠ 没找到 ffmpeg，这次打出来的包不含 ffmpeg。")
        print("  用 --ffmpeg <路径> 指定，或把 ffmpeg.exe 放到 bin/ 下。")
    elif ffmpeg:
        print(f"ffmpeg: {ffmpeg}（{human(ffmpeg.stat().st_size)}）")

    results: list[tuple[str, Path]] = []
    do_portable = (not (args.onedir or args.installer)) or args.all
    do_onedir = args.onedir or args.installer or args.all

    if do_portable:
        p = pyinstaller("onefile", ffmpeg, args.console, DIST)
        results.append(("便携版（单文件）", p))

    app_dir = None
    if do_onedir:
        app_dir = pyinstaller("onedir", ffmpeg, args.console, BUILD / "onedir")
        results.append(("目录版", app_dir))

    if args.installer or args.all:
        if app_dir is None:
            sys.exit("打安装包需要先有目录版")
        setup = build_installer(app_dir)
        if setup:
            results.append(("安装包", setup))

    print("\n" + "=" * 56)
    for label, p in results:
        size = p.stat().st_size if p.is_file() else sum(
            f.stat().st_size for f in p.rglob("*") if f.is_file())
        print(f"{label:<14} {p}  ({human(size)})")
    print("=" * 56)
    if not ffmpeg:
        print("\n提示：没有内置 ffmpeg。用户需要把 ffmpeg.exe 放到程序目录的 bin/ 下，")
        print("      或装到 PATH 里，否则下载完无法合并音视频。")


if __name__ == "__main__":
    main()
