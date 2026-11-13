# Thrones first-time setup for Windows 10/11.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [-Cpu] [-SkipRuntime]
#
# Everything is installed inside this folder:
#   .venv\            Python environment for the backend
#   frontend\dist\    built interface
#   runtime\llama.cpp official llama.cpp release binaries (from github.com/ggml-org/llama.cpp)
# Nothing is installed system-wide and no system settings are changed.
# Models are downloaded later from inside the app (Settings > Models).

param(
  [switch]$Cpu,          # download the CPU-only llama.cpp build instead of CUDA
  [switch]$SkipRuntime,  # keep an existing runtime\llama.cpp
  [string]$LlamaBuild = "b12289"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Yellow }

# ---- Python -------------------------------------------------------------
Step "Python environment"
$python = $null
foreach ($cand in @("py -3.12", "python")) {
  try {
    $v = Invoke-Expression "$cand --version" 2>$null
    if ($v -match "Python 3\.(1[1-9])") { $python = $cand; break }
  } catch {}
}
if (-not $python) { throw "Python 3.11 or newer is required. Install it from python.org and run this again." }
if (-not (Test-Path ".venv\Scripts\python.exe")) { Invoke-Expression "$python -m venv .venv" }
& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .venv\Scripts\python.exe -m pip install -r backend\requirements.txt --quiet
Write-Host "Backend dependencies installed."

# ---- Interface -----------------------------------------------------------
Step "Interface"
if (Test-Path "frontend\dist\index.html") {
  Write-Host "Using the pre-built interface in frontend\dist (from the release download)."
} else {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js 20+ is required to build the interface from source. Install it from nodejs.org, or use the release download, which includes a pre-built interface."
  }
  Push-Location frontend
  npm ci --no-audit --no-fund
  npm run build
  Pop-Location
}

# ---- Inference runtime ---------------------------------------------------
if (-not $SkipRuntime) {
  Step "llama.cpp runtime ($LlamaBuild)"
  $dl = Join-Path $root "runtime\_dl"
  New-Item -ItemType Directory -Force $dl, "runtime\llama.cpp" | Out-Null
  $hasNvidia = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
  $base = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaBuild"
  if ($Cpu -or -not $hasNvidia) {
    Write-Host "Using the CPU build$(if (-not $hasNvidia) { ' (no NVIDIA GPU detected)' })."
    $files = @("llama-$LlamaBuild-bin-win-cpu-x64.zip")
  } else {
    $files = @("llama-$LlamaBuild-bin-win-cuda-13.5-x64.zip", "cudart-llama-bin-win-cuda-13.5-x64.zip")
  }
  foreach ($f in $files) {
    Write-Host "Downloading $f"
    Invoke-WebRequest "$base/$f" -OutFile (Join-Path $dl $f)
    Expand-Archive -Force (Join-Path $dl $f) "runtime\llama.cpp"
  }
  & "runtime\llama.cpp\llama-server.exe" --version
}

Step "Done"
Write-Host "Start Thrones by double-clicking Thrones.bat. Then pick a model in Settings > Models."
