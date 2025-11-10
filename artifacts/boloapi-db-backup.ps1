Set-Location C:\Clients\SD\boloapi

Start-Transcript -Path "artifacts\boloapi.log" -Append

$env:PGPASSWORD = "Rxh1m3d3s!@#"
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -p 5432 -U postgres -d postgres -F c -f "artifacts/boloapi_db_backup.dump"
Remove-Item Env:\PGPASSWORD

# Commit to git
& "C:\Program Files\Git\bin\git.exe" add .
& "C:\Program Files\Git\bin\git.exe" commit -m "Daily db backup plus collateral changes on $(Get-Date -Format 'yyyy-MM-dd')"
& "C:\Program Files\Git\bin\git.exe" push

Stop-Transcript

Start-Sleep -s 10