# Export adapter 0.2 and run every comparison for the model card, one after another.
# Base 4B reasoning results already exist (evals/results/reasoning-base4b-*.json).
$ErrorActionPreference = "Continue"
Set-Location D:\Thrones
$env:HF_HOME = 'D:\Thrones\.cache\hf'; $env:HF_HUB_OFFLINE = '1'; $env:PYTHONIOENCODING = 'utf-8'
$py = '.venv-train\Scripts\python.exe'
$held = 'training\datasets\thrones_sft_v0.2.heldout.jsonl'
function Run($label, [string[]]$cmd) {
    "=== $label  $(Get-Date -Format HH:mm)"
    & $py -X utf8 @cmd 2>&1 | Where-Object { $_ -notmatch 'Warning|_pytree|Enum|regex for|cached|Found the latest|RemoteException|INFO:|Writing' } | ForEach-Object { "$_" }
}
Run 'export 0.2' @('training\export_adapter.py', '--run', 'thrones-adapter-0.2')
Run 'held-out: base'        @('evals\eval_adapter.py', '--label', 'v02-base', '--heldout', $held)
Run 'held-out: adapter 0.1' @('evals\eval_adapter.py', '--label', 'v02-adapter01', '--heldout', $held, '--lora', 'models\thrones-adapter-0.1.gguf')
Run 'held-out: adapter 0.2' @('evals\eval_adapter.py', '--label', 'v02-adapter02', '--heldout', $held, '--lora', 'models\thrones-adapter-0.2.gguf')
Run 'reasoning: adapter 0.1' @('evals\eval_reasoning.py', '--model', 'qwen3.5-4b-q4km', '--label', 'adapter01', '--lora', 'models\thrones-adapter-0.1.gguf')
Run 'reasoning: adapter 0.2' @('evals\eval_reasoning.py', '--model', 'qwen3.5-4b-q4km', '--label', 'adapter02', '--lora', 'models\thrones-adapter-0.2.gguf')
"=== ALL DONE  $(Get-Date -Format HH:mm)"
