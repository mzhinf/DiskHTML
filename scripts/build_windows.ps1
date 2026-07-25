param(
    [switch]$Clean
)

# 构建不依赖本机 Python 的 Windows 目录式 EXE，并生成可直接分发的 ZIP。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$buildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
$dist = Join-Path $buildRoot "dist"
$package = Join-Path $dist "DiskHTML"
$outputExecutable = Join-Path $package "DiskHTML.exe"
$internalDirectory = Join-Path $package "_internal"
$legacySingleFile = Join-Path $dist "DiskHTML.exe"
$releaseRoot = Join-Path $buildRoot "release"
$releaseArchive = Join-Path $releaseRoot "DiskHTML-win-x64.zip"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "未找到项目虚拟环境：$python"
}

function Remove-GeneratedPath {
    param([Parameter(Mandatory)][string]$Path)

    # 删除前限定目标必须是 build 目录或其子项，防止路径计算错误扩大清理范围。
    $fullPath = [IO.Path]::GetFullPath($Path)
    $buildPrefix = $buildRoot + [IO.Path]::DirectorySeparatorChar
    if (
        $fullPath -ne $buildRoot -and
        -not $fullPath.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "拒绝清理 build 目录外的路径：$fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

if ($Clean) {
    Remove-GeneratedPath -Path $buildRoot
}

# 清理旧目录包、旧 ZIP 和可能残留的 onefile 产物，确保发布入口唯一。
Remove-GeneratedPath -Path $package
Remove-GeneratedPath -Path $releaseArchive
Remove-GeneratedPath -Path $legacySingleFile

$arguments = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
    "--name", "DiskHTML", "--paths", (Join-Path $root "src"),
    "--distpath", $dist,
    "--workpath", (Join-Path $buildRoot "work"),
    "--specpath", $buildRoot,
    (Join-Path $root "scripts\gui_entry.py")
)

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $outputExecutable -PathType Leaf)) {
    throw "构建完成但未找到 EXE：$outputExecutable"
}
if (-not (Test-Path -LiteralPath $internalDirectory -PathType Container)) {
    throw "构建完成但缺少运行库目录：$internalDirectory"
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Compress-Archive -LiteralPath $package -DestinationPath $releaseArchive -CompressionLevel Optimal
if (-not (Test-Path -LiteralPath $releaseArchive -PathType Leaf)) {
    throw "未能生成发布 ZIP：$releaseArchive"
}

Write-Host "DiskHTML EXE 已生成：$outputExecutable"
Write-Host "可分发 ZIP 已生成：$releaseArchive"
