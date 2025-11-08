# Email Integration Helper Script for Windows
# Automates the integration of email functionality into FBI Wanted API

param(
    [Parameter(Mandatory=$false)]
    [string]$ProjectPath = ".",
    
    [Parameter(Mandatory=$false)]
    [switch]$TestOnly,
    
    [Parameter(Mandatory=$false)]
    [string]$TestEmail
)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  FBI API - Email Integration Helper" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Get absolute path
$ProjectPath = Resolve-Path $ProjectPath -ErrorAction SilentlyContinue
if (-not $ProjectPath) {
    Write-Host "❌ Invalid project path" -ForegroundColor Red
    exit 1
}

Write-Host "Project Path: $ProjectPath" -ForegroundColor Yellow
Write-Host ""

# Function to check if file exists
function Test-FileExists {
    param([string]$FilePath)
    Test-Path -Path $FilePath -PathType Leaf
}

# Function to backup file
function Backup-File {
    param([string]$FilePath)
    $BackupPath = "$FilePath.backup"
    if (Test-FileExists $FilePath) {
        Copy-Item $FilePath $BackupPath -Force
        Write-Host "✅ Backed up: $(Split-Path $FilePath -Leaf) → $(Split-Path $BackupPath -Leaf)" -ForegroundColor Green
        return $true
    }
    return $false
}

# Check if this is test mode
if ($TestOnly) {
    Write-Host "===== TEST MODE ONLY =====" -ForegroundColor Yellow
    Write-Host ""
    
    if (-not $TestEmail) {
        $TestEmail = Read-Host "Enter test email address"
    }
    
    Write-Host "Running email tests..." -ForegroundColor Cyan
    python test_email.py $TestEmail
    exit $LASTEXITCODE
}

# Step 1: Check prerequisites
Write-Host "Step 1: Checking Prerequisites" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor Cyan

$Prerequisites = @{
    "Python" = { python --version 2>&1 }
    "pip" = { pip --version 2>&1 }
    ".env file" = { Test-FileExists "$ProjectPath\.env" }
    "router_auth.py" = { Test-FileExists "$ProjectPath\router_auth.py" }
}

$AllPrereqsMet = $true
foreach ($Prereq in $Prerequisites.Keys) {
    $Result = & $Prerequisites[$Prereq]
    if ($Result -or $LASTEXITCODE -eq 0) {
        Write-Host "✅ $Prereq" -ForegroundColor Green
    } else {
        Write-Host "❌ $Prereq not found" -ForegroundColor Red
        $AllPrereqsMet = $false
    }
}

if (-not $AllPrereqsMet) {
    Write-Host ""
    Write-Host "⚠️  Please install missing prerequisites before continuing" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Step 2: Install dependencies
Write-Host "Step 2: Installing Dependencies" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor Cyan

$InstallDeps = Read-Host "Install 'requests' package? (Y/n)"
if ($InstallDeps -ne "n") {
    Write-Host "Installing requests..." -ForegroundColor Yellow
    pip install requests
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# Step 3: Copy email_utils.py
Write-Host "Step 3: Adding Email Module" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor Cyan

$EmailUtilsSource = "email_utils.py"
$EmailUtilsTarget = "$ProjectPath\email_utils.py"

if (-not (Test-FileExists $EmailUtilsSource)) {
    Write-Host "❌ email_utils.py not found in current directory" -ForegroundColor Red
    Write-Host "   Please run this script from the directory containing email_utils.py" -ForegroundColor Yellow
    exit 1
}

if (Test-FileExists $EmailUtilsTarget) {
    $Overwrite = Read-Host "email_utils.py already exists. Overwrite? (y/N)"
    if ($Overwrite -ne "y") {
        Write-Host "⏭️  Skipping email_utils.py" -ForegroundColor Yellow
    } else {
        Copy-Item $EmailUtilsSource $EmailUtilsTarget -Force
        Write-Host "✅ email_utils.py copied" -ForegroundColor Green
    }
} else {
    Copy-Item $EmailUtilsSource $EmailUtilsTarget
    Write-Host "✅ email_utils.py copied" -ForegroundColor Green
}

Write-Host ""

# Step 4: Update router_auth.py
Write-Host "Step 4: Updating Authentication Router" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor Cyan

$RouterAuthTarget = "$ProjectPath\router_auth.py"
$RouterAuthUpdated = "router_auth_updated.py"

if (Test-FileExists $RouterAuthUpdated) {
    $UpdateRouter = Read-Host "Replace router_auth.py with updated version? This will backup your current file. (Y/n)"
    if ($UpdateRouter -ne "n") {
        # Backup current file
        Backup-File $RouterAuthTarget
        
        # Copy updated version
        Copy-Item $RouterAuthUpdated $RouterAuthTarget -Force
        Write-Host "✅ router_auth.py updated" -ForegroundColor Green
        Write-Host "   Your original file was backed up to router_auth.py.backup" -ForegroundColor Yellow
    } else {
        Write-Host "⏭️  Skipping router update" -ForegroundColor Yellow
        Write-Host "   You'll need to manually integrate email functionality" -ForegroundColor Yellow
        Write-Host "   See INTEGRATION_GUIDE.md for manual steps" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️  router_auth_updated.py not found" -ForegroundColor Yellow
    Write-Host "   Manual integration required - see INTEGRATION_GUIDE.md" -ForegroundColor Yellow
}

Write-Host ""

# Step 5: Check .env configuration
Write-Host "Step 5: Checking Environment Configuration" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor Cyan

$EnvFile = "$ProjectPath\.env"
if (Test-FileExists $EnvFile) {
    $EnvContent = Get-Content $EnvFile -Raw
    
    $RequiredVars = @(
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "EMAIL_FROM_ADDRESS",
        "API_BASE_URL"
    )
    
    $MissingVars = @()
    foreach ($Var in $RequiredVars) {
        if ($EnvContent -notmatch "$Var=.+") {
            $MissingVars += $Var
        }
    }
    
    if ($MissingVars.Count -eq 0) {
        Write-Host "✅ All email configuration variables present in .env" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Missing configuration variables in .env:" -ForegroundColor Yellow
        foreach ($Var in $MissingVars) {
            Write-Host "   - $Var" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "Please add these to your .env file" -ForegroundColor Yellow
        Write-Host "See .env.example for reference" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ .env file not found" -ForegroundColor Red
    Write-Host "   Create .env file based on .env.example" -ForegroundColor Yellow
}

Write-Host ""

# Step 6: Test email functionality
Write-Host "Step 6: Testing Email Functionality" -ForegroundColor Cyan
Write-Host "--------------------------------" -ForegroundColor Cyan

$RunTests = Read-Host "Run email tests now? (Y/n)"
if ($RunTests -ne "n") {
    if (-not $TestEmail) {
        $TestEmail = Read-Host "Enter test email address"
    }
    
    Write-Host ""
    Write-Host "Running tests..." -ForegroundColor Yellow
    python test_email.py $TestEmail
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Email tests completed" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "❌ Some tests failed" -ForegroundColor Red
        Write-Host "   Check the output above for details" -ForegroundColor Yellow
    }
} else {
    Write-Host "⏭️  Skipping tests" -ForegroundColor Yellow
    Write-Host "   Run manually: python test_email.py your-email@example.com" -ForegroundColor Yellow
}

Write-Host ""

# Summary
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Integration Summary" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Files Added/Updated:" -ForegroundColor Yellow
Write-Host "  ✅ email_utils.py" -ForegroundColor Green
if (Test-FileExists "$ProjectPath\router_auth.py.backup") {
    Write-Host "  ✅ router_auth.py (backup created)" -ForegroundColor Green
}
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Complete Azure AD setup (see MICROSOFT_365_EMAIL_SETUP.md)" -ForegroundColor White
Write-Host "  2. Configure environment variables in .env" -ForegroundColor White
Write-Host "  3. Run tests: python test_email.py your-email@example.com" -ForegroundColor White
Write-Host "  4. Test with real registration flow" -ForegroundColor White
Write-Host ""

Write-Host "Documentation:" -ForegroundColor Yellow
Write-Host "  📄 MICROSOFT_365_EMAIL_SETUP.md - Azure AD setup guide" -ForegroundColor White
Write-Host "  📄 INTEGRATION_GUIDE.md - Complete integration guide" -ForegroundColor White
Write-Host "  📄 .env.example - Environment variable template" -ForegroundColor White
Write-Host ""

Write-Host "✅ Integration helper completed!" -ForegroundColor Green
Write-Host ""
