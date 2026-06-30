$ErrorActionPreference = "Stop"
$venv = "C:\venv312\Scripts"

Write-Host "Installing dependencies... This will auto-resume if the network drops."

$packages = @(
    "fastapi", "uvicorn", "structlog", "rank-bm25", "python-dotenv", "filelock", "httpx",
    "gitpython", "tree-sitter", "networkx",
    "langchain-groq", "langchain-huggingface",
    "streamlit",
    "chromadb",
    "sentence-transformers"
)

foreach ($pkg in $packages) {
    $success = $false
    $attempts = 0
    while (-not $success) {
        $attempts++
        Write-Host "Installing $pkg (Attempt $attempts)..."
        try {
            $process = Start-Process -FilePath "$venv\pip.exe" -ArgumentList "install $pkg --index-url https://mirrors.aliyun.com/pypi/simple/ --default-timeout=15" -Wait -NoNewWindow -PassThru
            if ($process.ExitCode -eq 0) {
                $success = $true
                Write-Host "$pkg installed successfully!" -ForegroundColor Green
            } else {
                Write-Host "Network dropped, resuming $pkg download..." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "Error occurred, resuming..." -ForegroundColor Yellow
        }
    }
}
Write-Host "ALL PACKAGES INSTALLED." -ForegroundColor Green
