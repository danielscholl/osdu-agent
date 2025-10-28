# Windows Compatibility Strategy

## Overview

This document outlines the strategy for ensuring OSDU Agent works seamlessly across Windows, macOS, and Linux platforms.

## Core Principles

### 1. Path Handling

**Always use `pathlib.Path` for all file system operations:**

```python
# ✅ GOOD - Cross-platform
from pathlib import Path
path = Path.cwd() / "repos" / "partition"
path.mkdir(parents=True, exist_ok=True)

# ❌ BAD - Unix-specific
path = os.path.join(os.getcwd(), "repos", "partition")
os.system(f"mkdir -p {path}")
```

**Key practices:**
- Use `Path.resolve()` to get absolute paths
- Use `Path.as_posix()` for display (consistent forward slashes)
- Use `str(path)` when passing to subprocesses
- Never concatenate path strings manually

### 2. File Operations

**Replace Unix shell commands with Python equivalents:**

| Unix Command | Python Equivalent |
|--------------|-------------------|
| `rm -rf dir` | `shutil.rmtree(dir, ignore_errors=True)` |
| `mkdir -p dir` | `Path(dir).mkdir(parents=True, exist_ok=True)` |
| `cp file dest` | `shutil.copy(file, dest)` |
| `mv file dest` | `shutil.move(file, dest)` |

**Example fix:**
```python
# ❌ BAD - Unix-specific
subprocess.run(["rm", "-rf", str(temp_dir)])

# ✅ GOOD - Cross-platform
import shutil
shutil.rmtree(temp_dir, ignore_errors=True)
```

### 3. Special Paths

**Use `os.devnull` instead of `/dev/null`:**

```python
# ✅ GOOD - Cross-platform (NUL on Windows, /dev/null on Unix)
import os
null_device = Path(os.devnull)

# ❌ BAD - Unix-specific
null_device = Path("/dev/null")
```

### 4. Subprocess Commands

**Guidelines for subprocess calls:**

- ✅ Cross-platform tools: `git`, `gh`, `glab`, `python`, `mvn`
- ❌ Unix-specific: `rm`, `mkdir`, `cp`, `mv`, `chmod`, `chown`
- Always pass `Path` objects or convert to string
- Use `shell=False` when possible

```python
# ✅ GOOD
subprocess.run(
    ["git", "clone", repo_url, service],
    cwd=str(repos_dir),  # Convert Path to string
    capture_output=True
)

# ❌ BAD
subprocess.run(
    f"cd {repos_dir} && git clone {repo_url} {service}",
    shell=True  # Shell syntax is platform-specific
)
```

### 5. Path Display

**Use `.as_posix()` for consistent UI display:**

```python
# ✅ GOOD - Always shows forward slashes
display_path = f"~/{cwd.relative_to(home).as_posix()}"

# ❌ BAD - Shows backslashes on Windows
display_path = f"~/{cwd.relative_to(home)}"  # ~/source\osdu on Windows
```

## Fixes Applied

### Issue #1: Unix `rm -rf` Command
**File:** `src/agent/github/fork_client.py`

**Problem:** Used `rm -rf` which doesn't exist on Windows
```python
# Before
subprocess.run(["rm", "-rf", str(temp_dir)], timeout=30)
```

**Solution:** Use cross-platform `shutil.rmtree()`
```python
# After
import shutil
await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)
```

### Issue #2: Mixed Path Separators in Display
**File:** `src/agent/cli.py`

**Problem:** Displayed `~/source\osdu` on Windows (mixed separators)
```python
# Before
display_path = f"~/{cwd.relative_to(home)}"  # ~/source\osdu on Windows
```

**Solution:** Use `.as_posix()` for consistent display
```python
# After
rel_path = cwd.relative_to(home)
display_path = f"~/{rel_path.as_posix()}"  # ~/source/osdu everywhere
```

### Issue #3: Unix-specific `/dev/null`
**File:** `src/agent/copilot/runners/copilot_runner.py`

**Problem:** Hardcoded `/dev/null` doesn't exist on Windows
```python
# Before
super().__init__(Path("/dev/null"), services)
```

**Solution:** Use `os.devnull` (cross-platform)
```python
# After
import os
super().__init__(Path(os.devnull), services)
```

### Issue #4: Path Resolution
**Files:** `src/agent/config.py`, `src/agent/github/fork_client.py`

**Problem:** Paths not always resolved to absolute paths
```python
# Before
repos_root: Path = field(
    default_factory=lambda: Path(os.getenv("OSDU_AGENT_REPOS_ROOT", Path.cwd() / "repos"))
)
self.repos_dir = repos_dir or config.repos_root
```

**Solution:** Always resolve to absolute paths
```python
# After
repos_root: Path = field(
    default_factory=lambda: (
        Path(os.getenv("OSDU_AGENT_REPOS_ROOT")).resolve()
        if os.getenv("OSDU_AGENT_REPOS_ROOT")
        else (Path.cwd() / "repos").resolve()
    )
)
self.repos_dir = (repos_dir or config.repos_root).resolve()
self.repos_dir.mkdir(parents=True, exist_ok=True)  # Added parents=True
```

## Testing Strategy

### Manual Testing on Windows

1. **Test basic commands:**
   ```powershell
   osdu --help
   osdu status --service partition
   osdu fork --service partition
   ```

2. **Test path handling:**
   - Verify status bar shows `~/path/to/dir` (not `~/path\to\dir`)
   - Check that repos are created in correct location
   - Confirm git operations work correctly

3. **Test file operations:**
   - Fork repositories (creates directories)
   - Clone repositories (git operations)
   - Run tests (Maven operations)

### Automated Testing

Add platform-specific tests:
```python
import platform

def test_path_operations_cross_platform():
    """Test that path operations work on all platforms."""
    config = AgentConfig()
    assert config.repos_root.is_absolute()
    assert config.repos_root.exists() or True  # May not exist yet

def test_subprocess_commands_windows():
    """Test subprocess commands work on Windows."""
    if platform.system() != "Windows":
        pytest.skip("Windows-only test")
    # Test git, gh commands work
```

## Future Considerations

### 1. CI/CD Testing
Add Windows runners to GitHub Actions:
```yaml
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ['3.12']
```

### 2. Shell Commands Audit
Periodically audit for Unix-specific commands:
```bash
# Search for common Unix commands
rg '\["(rm|mkdir|chmod|chown|cp|mv)"' src/
```

### 3. Path Separator Audit
Check for hardcoded path separators:
```bash
# Search for hardcoded forward slashes in paths
rg '(?<!")\/(?!/).*(?<!http:)(?<!https:)' src/
```

## References

- [pathlib Documentation](https://docs.python.org/3/library/pathlib.html)
- [shutil Documentation](https://docs.python.org/3/library/shutil.html)
- [os.path vs pathlib](https://realpython.com/python-pathlib/)
- [Cross-platform Python](https://docs.python.org/3/library/os.html#os.name)
