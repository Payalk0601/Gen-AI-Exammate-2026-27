# Builds PROGRESS.md from the evidence files that really exist in your repo.
# Run from the repo folder:
#   powershell -ExecutionPolicy Bypass -File scripts\make_progress.ps1
# If PROGRESS.md already exists it is NOT overwritten: PROGRESS.generated.md is written instead.

$days = [ordered]@{
    "D1 project card and first scripts"   = "README.md", "day01_intro.py", "day01_menu.py"
    "D2 records and CLI"                  = "data/sample_records.json|data/records.json", "app/records.py", "app/cli.py"
    "D5 how LLMs work, checkpoint 1"      = "docs/how_llms_work.md", "docs/checkpoint-1.md", "analysis"
    "D6 LLM wrapper and prompts"          = "app/llm.py", "prompts", "eval/prompt_compare.md"
    "D7-D8 retrieval"                     = "app/chunking.py", "app/embed.py", "app/vectorstore.py"
    "D9 agent tool, loop and graph"       = "app/tools.py", "app/agent_loop.py", "app/graph.py"
    "D10 UI and checkpoint 2"             = "ui/app.py", "docs/checkpoint-2.md", "docs/ui_screenshot.png"
    "D11 tests, lint and Docker"          = "tests", "ruff.toml", "Dockerfile", "docker-compose.yml"
    "D12 CI workflow"                     = ".github/workflows/ci.yml"
    "D13 production guards and resume"    = "app/prod.py", "scripts/benchmark.py", "docs/benchmark.json", "docs/resume.md"
    "D14 interview notes and rehearsal"   = "docs/interview.md", "docs/rehearsal.md"
}

$rows = @()
$open = @()

foreach ($name in $days.Keys) {
    $missing = @()
    foreach ($item in $days[$name]) {
        $found = $false
        foreach ($alt in $item.Split("|")) {
            if (Test-Path $alt) { $found = $true }
        }
        if (-not $found) { $missing += $item }
    }
    $evidence = $days[$name] -join ", "
    if ($missing.Count -eq 0) {
        $rows += "| $name | $evidence | Done | |"
    } else {
        $list = $missing -join ", "
        $rows += "| $name | $evidence | OPEN | missing: $list |"
        $open += "- $name : missing $list"
    }
}

$tags = git tag --list
foreach ($t in "week-1", "checkpoint-1", "checkpoint-2", "final") {
    if ($tags -contains $t) {
        $rows += "| tag $t | git tag | Done | |"
    } else {
        $rows += "| tag $t | git tag | OPEN | create it and push it |"
        $open += "- tag $t is missing"
    }
}

$left = Select-String -Path README.md -Pattern "YOUR-VIDEO-LINK|PASTE-YOUR|Not measured yet" -ErrorAction SilentlyContinue
if ($left) {
    $rows += "| README | demo video link, measured numbers | OPEN | placeholder still in README |"
    $open += "- README still has a placeholder (video link or results table)"
} else {
    $rows += "| README | demo video link, measured numbers | Done | |"
}

$out = "PROGRESS.md"
if (Test-Path $out) { $out = "PROGRESS.generated.md" }

$lines = @()
$lines += "# Progress"
$lines += ""
$lines += "Status is worked out from files that exist in the repo. Done means the evidence files are there, not that they are perfect."
$lines += ""
$lines += "| Item | Evidence | Status | Notes |"
$lines += "|---|---|---|---|"
$lines += $rows
$lines += ""
$lines += "## Open items"
if ($open.Count -eq 0) { $lines += "None." } else { $lines += $open }
$lines += ""
$lines += "## Not done (and why)"
$lines += "Move an item here, with a one-line honest reason, if you decide not to do it."
$lines += ""
$lines += "- (none yet)"

$lines | Set-Content $out -Encoding utf8
Write-Host "Wrote $out"
Write-Host ""
if ($open.Count -eq 0) { Write-Host "No open items." -ForegroundColor Green }
else { Write-Host "Open items:" -ForegroundColor Yellow; $open | ForEach-Object { Write-Host $_ } }
