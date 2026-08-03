# Optional PowerShell wrapper for the Python-based Windows build.
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$builder = Join-Path $PSScriptRoot "build_windows.py"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "未找到项目虚拟环境：$python"
}

$arguments = @($builder)
if ($Clean) {
    $arguments += "--clean"
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}