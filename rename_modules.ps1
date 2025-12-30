# ============================================================================
# rename_modules.ps1
# Renames Python modules from *_auth, *_config, *_utils to auth_*, config_*, utils_*
# and updates all references in the codebase
# ============================================================================
# Usage: 
#   cd C:\Clients\SD\boloapi
#   .\rename_modules.ps1 -WhatIf    # Preview changes without making them
#   .\rename_modules.ps1            # Execute the changes
# ============================================================================

param(
    [switch]$WhatIf = $false,
    [string]$ProjectPath = "."
)

# Change to project directory
Set-Location $ProjectPath

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Module Renaming Script" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

if ($WhatIf) {
    Write-Host "`n[PREVIEW MODE] No changes will be made.`n" -ForegroundColor Yellow
} else {
    Write-Host "`n[EXECUTE MODE] Changes will be applied.`n" -ForegroundColor Green
}

# ============================================================================
# DEFINE RENAMES
# ============================================================================

# Hash table: OldName (without .py) -> NewName (without .py)
$renames = @{
    # _service -> service_
    "notification_service" = "service_nottification"
    "link_validation_service" = "service_link_validation"
}

# ============================================================================
# STEP 1: VERIFY ALL SOURCE FILES EXIST
# ============================================================================

Write-Host "`n[Step 1] Verifying source files exist..." -ForegroundColor Cyan

$missingFiles = @()
foreach ($oldName in $renames.Keys) {
    $oldFile = "$oldName.py"
    if (-not (Test-Path $oldFile)) {
        $missingFiles += $oldFile
        Write-Host "  [MISSING] $oldFile" -ForegroundColor Red
    } else {
        Write-Host "  [OK] $oldFile" -ForegroundColor Green
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host "`nError: Missing source files. Aborting." -ForegroundColor Red
    exit 1
}

# ============================================================================
# STEP 2: CHECK FOR CONFLICTS (target files already exist)
# ============================================================================

Write-Host "`n[Step 2] Checking for naming conflicts..." -ForegroundColor Cyan

$conflicts = @()
foreach ($oldName in $renames.Keys) {
    $newName = $renames[$oldName]
    $newFile = "$newName.py"
    if (Test-Path $newFile) {
        $conflicts += $newFile
        Write-Host "  [CONFLICT] $newFile already exists!" -ForegroundColor Red
    }
}

if ($conflicts.Count -gt 0) {
    Write-Host "`nError: Target files already exist. Aborting." -ForegroundColor Red
    exit 1
}

Write-Host "  No conflicts found." -ForegroundColor Green

# ============================================================================
# STEP 3: UPDATE REFERENCES IN ALL PYTHON FILES
# ============================================================================

Write-Host "`n[Step 3] Updating import references in Python files..." -ForegroundColor Cyan

# Get all Python files, excluding artifacts folder
$pyFiles = Get-ChildItem -Path . -Filter "*.py" -Recurse | Where-Object { $_.FullName -notmatch "\\artifacts\\" }

$totalReplacements = 0

foreach ($pyFile in $pyFiles) {
    $content = Get-Content $pyFile.FullName -Raw
    $originalContent = $content
    $fileReplacements = 0
    
    foreach ($oldName in $renames.Keys) {
        $newName = $renames[$oldName]
        
        # Pattern 1: "from oldname import ..."
        $pattern1 = "(?m)^(\s*from\s+)$oldName(\s+import)"
        if ($content -match $pattern1) {
            $content = $content -replace $pattern1, "`$1$newName`$2"
            $fileReplacements++
        }
        
        # Pattern 2: "import oldname"
        $pattern2 = "(?m)^(\s*import\s+)$oldName(\s*$|\s*,|\s+as\s+)"
        if ($content -match $pattern2) {
            $content = $content -replace $pattern2, "`$1$newName`$2"
            $fileReplacements++
        }
        
        # Pattern 3: "import x, oldname, y" (in comma-separated imports)
        $pattern3 = "(?m)^(\s*import\s+.+,\s*)$oldName(\s*,|\s*$)"
        if ($content -match $pattern3) {
            $content = $content -replace $pattern3, "`$1$newName`$2"
            $fileReplacements++
        }
        
        # Pattern 4: Module reference like "oldname.function()"
        $pattern4 = "(?<![a-zA-Z0-9_])$oldName\."
        if ($content -match $pattern4) {
            $content = $content -replace $pattern4, "$newName."
            $fileReplacements++
        }
        
        # Pattern 5: References in comments like "use jwt_auth.py" or "see jwt_auth.require_jwt_role()"
        $pattern5 = "(?<![a-zA-Z0-9_])$oldName\.py"
        if ($content -match $pattern5) {
            $content = $content -replace $pattern5, "$newName.py"
            $fileReplacements++
        }
    }
    
    if ($content -ne $originalContent) {
        $totalReplacements += $fileReplacements
        $relativePath = $pyFile.FullName.Replace((Get-Location).Path + "\", "")
        Write-Host "  [UPDATED] $relativePath ($fileReplacements replacements)" -ForegroundColor Yellow
        
        if (-not $WhatIf) {
            Set-Content -Path $pyFile.FullName -Value $content -NoNewline
        }
    }
}

Write-Host "  Total replacements: $totalReplacements" -ForegroundColor Cyan

# ============================================================================
# STEP 4: RENAME THE FILES
# ============================================================================

Write-Host "`n[Step 4] Renaming files..." -ForegroundColor Cyan

foreach ($oldName in $renames.Keys) {
    $newName = $renames[$oldName]
    $oldFile = "$oldName.py"
    $newFile = "$newName.py"
    
    Write-Host "  $oldFile -> $newFile" -ForegroundColor White
    
    if (-not $WhatIf) {
        Rename-Item -Path $oldFile -NewName $newFile
    }
}

# ============================================================================
# STEP 5: SUMMARY
# ============================================================================

Write-Host "`n" + "=" * 70 -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

Write-Host "`nFiles renamed:" -ForegroundColor White
foreach ($oldName in $renames.Keys | Sort-Object) {
    $newName = $renames[$oldName]
    Write-Host "  $oldName.py -> $newName.py" -ForegroundColor Gray
}

Write-Host "`nTotal files renamed: $($renames.Count)" -ForegroundColor Cyan
Write-Host "Total import references updated: $totalReplacements" -ForegroundColor Cyan

if ($WhatIf) {
    Write-Host "`n[PREVIEW COMPLETE] Run without -WhatIf to apply changes." -ForegroundColor Yellow
} else {
    Write-Host "`n[COMPLETE] All changes applied." -ForegroundColor Green
    Write-Host "`nRecommended: Test your application to verify everything works." -ForegroundColor Yellow
    Write-Host "  uvicorn app:app --reload" -ForegroundColor Gray
}

Write-Host ""