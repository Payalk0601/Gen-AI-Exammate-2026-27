# Final check before tagging. Run from the repo folder:
#   powershell -ExecutionPolicy Bypass -File scripts\final_check.ps1
$py = ".venv\Scripts\python.exe"
$fails = 0

function Check($name, $ok, $detail) {
    if ($ok) { Write-Host "PASS  $name" -ForegroundColor Green }
    else { Write-Host "FAIL  $name  $detail" -ForegroundColor Red; $script:fails++ }
}

$dirty = git status --porcelain
Check "git working tree is clean" (-not $dirty) (($dirty | Select-Object -First 5) -join "; ")

git fetch --quiet 2>$null
$ahead = git rev-list --count "origin/main..HEAD" 2>$null
Check "everything is pushed to origin/main" ($ahead -eq "0") "($ahead commits not pushed)"

$null = & $py -m pytest -q 2>&1
Check "pytest passes" ($LASTEXITCODE -eq 0) "(run: $py -m pytest -q)"

$null = & $py -m ruff check . 2>&1
Check "ruff check passes" ($LASTEXITCODE -eq 0) "(run: $py -m ruff check .)"

foreach ($f in "README.md", "docs\interview.md", "docs\resume.md", "docs\rehearsal.md", "docs\ui_screenshot.png", "PROGRESS.md") {
    Check "file exists: $f" (Test-Path $f) ""
}

$left = Select-String -Path README.md, docs\*.md -Pattern "YOUR-VIDEO-LINK|PASTE-YOUR|Not measured yet|____" -ErrorAction SilentlyContinue
Check "no blanks or placeholders left in README and docs" (-not $left) (($left | ForEach-Object { "$($_.Filename):$($_.LineNumber)" }) -join ", ")

if (Test-Path PROGRESS.md) {
    $open = Select-String -Path PROGRESS.md -Pattern "\| OPEN \||\[ \]|TODO" -CaseSensitive:$false
    Check "PROGRESS.md has no open items" (-not $open) (($open | ForEach-Object { "line $($_.LineNumber)" }) -join ", ")
}

$envTracked = git ls-files .env
Check ".env is not tracked by git" (-not $envTracked) ""

$rehearsal = Select-String -Path docs\rehearsal.md -Pattern "^\| (1|2) \| +\|" -ErrorAction SilentlyContinue
Check "rehearsal log filled in for both runs" (-not $rehearsal) "(fill docs\rehearsal.md)"

Write-Host ""
if ($fails -eq 0) { Write-Host "All checks passed. Safe to tag: git tag final" -ForegroundColor Green }
else { Write-Host "$fails check(s) failed. Fix them, then run this again." -ForegroundColor Red }


