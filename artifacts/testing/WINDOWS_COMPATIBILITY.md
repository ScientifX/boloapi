# Windows Compatibility Notes

## Issue Fixed: UnicodeEncodeError

### The Problem

On Windows, Python's default file encoding is `cp1252` (Windows-1252), which doesn't support Unicode characters like emoji (✅ ❌ ⚠️ 🎉).

**Error you were seeing:**
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 4-5: character maps to <undefined>
```

### The Fix

**Two fixes applied:**

#### 1. Explicit UTF-8 Encoding
Changed from:
```python
with open(filename, 'w') as f:
```

To:
```python
with open(filename, 'w', encoding='utf-8') as f:
```

This ensures the file is written with UTF-8 encoding on all platforms.

#### 2. Cross-Platform Path Handling
Changed from:
```python
filename = f"/mnt/user-data/outputs/test_report_{timestamp}.md"
```

To:
```python
output_dir = "/mnt/user-data/outputs" if os.path.exists("/mnt/user-data/outputs") else "."
filename = os.path.join(output_dir, f"test_report_{timestamp}.md")
```

This makes the code work on both:
- **Linux/Mac**: Saves to `/mnt/user-data/outputs/`
- **Windows**: Saves to current directory (where you run the script)

### How to Use on Windows

#### Default Behavior
Reports save to the current directory:
```
C:\Clients\SD\boloapi\artifacts\testing\test_report_20241107_142345.md
```

#### Custom Output Directory (Optional)
If you want reports in a specific folder, modify `test_roles.py`:

```python
# Option 1: Use a Windows path
output_dir = "C:\\reports"

# Option 2: Use relative path
output_dir = "./test_reports"

# Then create the directory if it doesn't exist
import os
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
```

### Verifying UTF-8 Encoding

To check your report was saved correctly:

**In Windows PowerShell:**
```powershell
Get-Content .\test_report_20241107_142345.md -Encoding UTF8
```

**In Python:**
```python
with open('test_report_20241107_142345.md', 'r', encoding='utf-8') as f:
    content = f.read()
    print(content[:100])  # First 100 chars
```

### Viewing the Report

**Option 1: VS Code**
- Right-click → Open Preview (Ctrl+Shift+V)
- Native markdown rendering with emoji support

**Option 2: Browser**
- Install markdown viewer extension
- Or use online viewer like [StackEdit](https://stackedit.io/)

**Option 3: GitHub**
- Push to GitHub and view there (perfect rendering)

### Common Windows Issues and Solutions

#### Issue: Emoji Not Displaying

**In Windows Terminal:**
```powershell
# Check your terminal supports Unicode
[Console]::OutputEncoding
# Should show: System.Text.UTF8Encoding

# If not, set it:
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

**In PowerShell ISE:**
- PowerShell ISE has limited Unicode support
- Use Windows Terminal or VS Code instead

#### Issue: Path Not Found

**Error:**
```
FileNotFoundError: [Errno 2] No such file or directory
```

**Solution:**
```python
# Create output directory first
import os
output_dir = "./test_reports"
os.makedirs(output_dir, exist_ok=True)
```

#### Issue: Permission Denied

**Error:**
```
PermissionError: [Errno 13] Permission denied
```

**Solutions:**
1. Run PowerShell as Administrator
2. Choose a directory where you have write permissions
3. Check if file is open in another program

### Best Practices for Windows

1. **Use UTF-8 everywhere:**
```python
# Reading
with open(file, 'r', encoding='utf-8') as f:
    data = f.read()

# Writing
with open(file, 'w', encoding='utf-8') as f:
    f.write(data)
```

2. **Use os.path for cross-platform paths:**
```python
import os
path = os.path.join("folder", "subfolder", "file.txt")
# Works on Windows, Linux, Mac
```

3. **Check paths exist before writing:**
```python
import os
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
```

4. **Use pathlib for modern path handling:**
```python
from pathlib import Path

output_dir = Path("./test_reports")
output_dir.mkdir(exist_ok=True)
filename = output_dir / f"test_report_{timestamp}.md"
```

### Current Configuration

The fixed code now:
- ✅ Uses UTF-8 encoding explicitly
- ✅ Works on Windows and Linux
- ✅ Saves to current directory on Windows
- ✅ Saves to `/mnt/user-data/outputs/` on Linux
- ✅ Handles emoji and Unicode correctly

### Testing the Fix

Run the tests again:
```bash
python test_driver_extended.py --roles
```

You should now see:
```
📄 Detailed report saved to: .\test_report_20241107_142345.md
```

And the file will contain proper emoji rendering: ✅ ⚠️ ❌ 🎉

### Quick Test

Create a test file to verify Unicode support:
```python
# test_unicode.py
with open('test_unicode.md', 'w', encoding='utf-8') as f:
    f.write("# Test Report\n")
    f.write("✅ Pass\n")
    f.write("❌ Fail\n")
    f.write("⚠️ Warning\n")
    f.write("🎉 Success\n")

print("✓ File created successfully!")
```

Run it:
```bash
python test_unicode.py
```

If it works without errors, you're all set!

## Summary

The issue is **fixed** in the updated `test_roles.py`. The report will now:
1. Save with proper UTF-8 encoding on Windows
2. Save to the current directory (not `/mnt/user-data/outputs/`)
3. Display all emoji and Unicode characters correctly

**Savvy?** 🎯
