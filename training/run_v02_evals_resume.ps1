# Re-run the three evaluations that were lost to out-of-memory crashes on 13 Nov 2026.
$ErrorActionPreference = "Continue"
Set-Location D:\Thrones
$env:HF_HOME = 'D:\Thrones\.cache\hf'; $env:HF_HUB_OFFLINE = '1'; $env:PYTHONIOENCODING = 'utf-8'
$py = '.venv-train\Scripts\python.exe'
$held = 'training\datasets\thrones_sft_v0.2.heldout.jsonl'
function Run($label, [string[]]$cmd) {
    $os = Get-CimInstance Win32_OperatingSystem
    "=== $label  $(Get-Date -Format HH:mm)  (free RAM {0:N1} GB)" -f ($os.FreePhysicalMemory/1MB)
    & $py -X utf8 @cmd 2>&1 | Where-Object { $_ -notmatch 'Warning|_pytree|Enum|regex for|cached|Found the latest|RemoteException|INFO:|Writing' } | ForEach-Object { "$_" }
}
Run 'held-out: adapter 0.2' @('evals\eval_adapter.py', '--label', 'v02-adapter02', '--heldout', $held, '--lora', 'models\thrones-adapter-0.2.gguf')
Run 'reasoning: adapter 0.2' @('evals\eval_reasoning.py', '--model', 'qwen3.5-4b-q4km', '--label', 'adapter02', '--lora', 'models\thrones-adapter-0.2.gguf')
Run 'reasoning: adapter 0.1' @('evals\eval_reasoning.py', '--model', 'qwen3.5-4b-q4km', '--label', 'adapter01', '--lora', 'models\thrones-adapter-0.1.gguf')
"=== ALL DONE  $(Get-Date -Format HH:mm)"
