param(
    [switch]$Clean
)

# 构建 Windows 图形界面发布包；要求项目虚拟环境已安装 PyInstaller。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到项目虚拟环境：$python"
}

$arguments = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
    "--name", "DiskHTML", "--paths", (Join-Path $root "src"),
    "--distpath", (Join-Path $root "build\dist"),
    "--workpath", (Join-Path $root "build\work"),
    "--specpath", (Join-Path $root "build"),
    (Join-Path $root "scripts\gui_entry.py")
)

if ($Clean) {
    Remove-Item -LiteralPath (Join-Path $root "build") -Recurse -Force -ErrorAction SilentlyContinue
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
}
