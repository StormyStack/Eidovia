# ─────────────────────────────────────────────────────────
# EduAR-AI Docker Stack Startup Script
# Automates setup and starts all services
# 
# Usage:
#   .\startup.ps1
# ─────────────────────────────────────────────────────────

Write-Host "═════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🚀 EduAR-AI Docker Stack Startup" -ForegroundColor Cyan
Write-Host "═════════════════════════════════════════════════════════" -ForegroundColor Cyan

# ─── Step 1: Check Docker ───
Write-Host "`n[1/5] Checking Docker installation..." -ForegroundColor Yellow

$docker_check = docker --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Docker found: $docker_check" -ForegroundColor Green

# ─── Step 2: Check .env file ───
Write-Host "`n[2/5] Checking .env configuration..." -ForegroundColor Yellow

if (!(Test-Path ".env")) {
    Write-Host "❌ .env file not found" -ForegroundColor Red
    Write-Host "   Creating from template..." -ForegroundColor Yellow
    
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "✅ Created .env from template" -ForegroundColor Green
        Write-Host "`n⚠️  IMPORTANT: Edit .env and set:" -ForegroundColor Yellow
        Write-Host "   - DB_PASSWORD (from SE)" -ForegroundColor Yellow
        Write-Host "   - REDIS_PASSWORD (from SE)" -ForegroundColor Yellow
        exit 1
    } else {
        Write-Host "❌ .env.example not found. Please copy configuration files first." -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ .env file found" -ForegroundColor Green

# Check for required passwords
$env_content = Get-Content ".env" -Raw
if ($env_content -match "changeme") {
    Write-Host "⚠️  .env still has placeholder passwords!" -ForegroundColor Yellow
    Write-Host "   Edit .env and replace 'changeme_strong_password_from_SE'" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ .env configured properly" -ForegroundColor Green

# ─── Step 3: Check required files ───
Write-Host "`n[3/5] Checking required files..." -ForegroundColor Yellow

$required_files = @(
    "docker-compose.yml",
    "01_schema.sql",
    "Dockerfile",
    "main_service.py",
    "config_prod.py"
)

$missing = @()
foreach ($file in $required_files) {
    if (!(Test-Path $file)) {
        $missing += $file
    }
}

if ($missing.Count -gt 0) {
    Write-Host "❌ Missing files:" -ForegroundColor Red
    foreach ($file in $missing) {
        Write-Host "   - $file" -ForegroundColor Red
    }
    exit 1
}

Write-Host "✅ All required files found" -ForegroundColor Green

# ─── Step 4: Start Docker containers ───
Write-Host "`n[4/5] Starting Docker containers..." -ForegroundColor Yellow

docker-compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to start containers" -ForegroundColor Red
    docker-compose logs
    exit 1
}

Write-Host "✅ Containers started" -ForegroundColor Green

# ─── Step 5: Wait for health checks ───
Write-Host "`n[5/5] Waiting for services to be ready..." -ForegroundColor Yellow

$max_attempts = 30
$attempt = 0

while ($attempt -lt $max_attempts) {
    $postgres_health = docker-compose exec -T postgres pg_isready -U appuser 2>$null
    $redis_health = docker-compose exec -T redis redis-cli -a (Get-Content .env -Raw | Select-String "REDIS_PASSWORD=([^\r\n]+)" | ForEach-Object { $_.Matches[0].Groups[1].Value }) ping 2>$null
    
    if ($postgres_health -match "accepting" -and $redis_health -match "PONG") {
        Write-Host "✅ PostgreSQL and Redis are ready" -ForegroundColor Green
        break
    }
    
    Write-Host "⏳ Waiting for services... ($($attempt + 1)/$max_attempts)" -ForegroundColor Gray
    Start-Sleep -Seconds 1
    $attempt++
}

if ($attempt -eq $max_attempts) {
    Write-Host "⚠️  Services took longer to start. Checking status..." -ForegroundColor Yellow
}

# ─── Display Summary ───
Write-Host "`n═════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ Stack Started Successfully" -ForegroundColor Green
Write-Host "═════════════════════════════════════════════════════════" -ForegroundColor Green

Write-Host "`n📋 Services:" -ForegroundColor Cyan
docker-compose ps

Write-Host "`n🌐 URLs:" -ForegroundColor Cyan
Write-Host "  API:        http://localhost:8001" -ForegroundColor White
Write-Host "  Health:     http://localhost:8001/health" -ForegroundColor White
Write-Host "  Database:   localhost:5432 (PostgreSQL)" -ForegroundColor White
Write-Host "  Cache:      localhost:6379 (Redis)" -ForegroundColor White

Write-Host "`n📝 Logs:" -ForegroundColor Cyan
Write-Host "  docker-compose logs -f              # All services" -ForegroundColor White
Write-Host "  docker-compose logs -f ai-service  # AI service only" -ForegroundColor White
Write-Host "  docker-compose logs -f postgres    # Database only" -ForegroundColor White

Write-Host "`n🛑 Stop stack:" -ForegroundColor Cyan
Write-Host "  docker-compose down" -ForegroundColor White

Write-Host "`n"
