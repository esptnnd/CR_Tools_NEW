# GUI Crashing Issue - Fix Summary

## Problem Description
GUI crashes when performing concurrent uploads across multiple SSH sessions (7+ servers) in duplicated session groups like "CR EXECUTOR TRUE" and "CR EXECUTOR TRUE CLONE 1".

## Root Causes Identified

### 1. **Missing Parameter in Method Signature**
- `SSHTab.perform_sftp_and_remote_commands()` was missing the `collect_prepost_checked` parameter
- This caused errors when the parameter was passed from `GUI.py`

### 2. **Race Conditions on File System Operations**
- Multiple concurrent `UploadWorker` threads writing/reading same files simultaneously
- `sites_list_*.txt` files being created/deleted by multiple threads
- Temporary `tmp_command_mos_*.txt` files conflicting across sessions

### 3. **Thread Safety Issues**
- No synchronization for file I/O operations
- Concurrent access to `Temp/` directory without locking
- Multiple threads creating/deleting files in CR folders simultaneously

### 4. **Resource Management**
- SSH/SFTP connections not properly closed on errors
- Worker threads not cleaning up properly
- No timeout on SSH connections (hanging connections)

### 5. **GUI Blocking**
- QMessageBox popups during concurrent uploads blocked the event loop
- No staggered delays between upload initiations

## Fixes Applied

### 1. **Added Missing Parameter** ✓
**Files Modified:** `lib/SSHTab.py`
- Added `collect_prepost_checked` parameter to `perform_sftp_and_remote_commands()`
- Added parameter to `_setup_upload_worker()` method
- Ensured parameter is passed to `UploadWorker` constructor

### 2. **Thread-Safe File Operations** ✓
**Files Modified:** `lib/workers.py`
- Added `threading.Lock()` for file system operations: `_file_operation_lock`
- Protected all file creation/deletion with lock:
  - `sites_list_*.txt` generation
  - `tmp_command_mos_*.txt` creation
  - Temporary directory operations
  - File cleanup operations

### 3. **Unique Temporary Directories** ✓
**Files Modified:** `lib/workers.py`
- Changed temp directory naming from `tmp_upload_{ENM_SERVER}` to `tmp_upload_{ENM_SERVER}_{timestamp}`
- Changed temp file naming to include timestamps: `tmp_command_mos_{ENM_SERVER}_{timestamp}.txt`
- Prevents file conflicts between concurrent uploads

### 4. **Improved Resource Management** ✓
**Files Modified:** `lib/workers.py`, `lib/SSHTab.py`

**workers.py:**
- Added connection timeouts (30s) to prevent hanging
- Properly initialize `sftp = None` to handle cleanup
- Added safe close for both SFTP and SSH in finally block
- Better exception handling with specific error messages

**SSHTab.py:**
- Added `upload_error_handler()` for better error handling
- Added `_safe_cleanup_upload()` with exception handling
- Improved `cleanup_upload_thread()` with try-except blocks
- Check for `RuntimeError` when stopping deleted workers

### 5. **Staggered Upload Initiation** ✓
**Files Modified:** `GUI.py`
- Added 0.5 second delay between concurrent upload initiations
- Prevents resource contention and overwhelming the system
- Uses indexed loop to apply staggered delays

### 6. **Non-Blocking Error Handling** ✓
**Files Modified:** `lib/SSHTab.py`
- Removed `QMessageBox.critical()` from concurrent uploads
- Errors now logged to output window instead
- Separate error handler: `upload_error_handler()`
- Prevents GUI event loop blocking

## Testing Recommendations

### Test Scenario 1: Concurrent Upload - Same Session Group
1. Connect all 6-7 servers in "CR EXECUTOR TRUE"
2. Upload 1-2 CR folders to subset of servers
3. Immediately upload another CR folder to all 7 servers
4. **Expected:** No crash, all uploads complete, no file conflicts

### Test Scenario 2: Concurrent Upload - Duplicated Sessions
1. Duplicate "CR EXECUTOR TRUE" → "CR EXECUTOR TRUE CLONE 1"
2. Connect all servers in both session groups
3. Upload CR folders to both groups simultaneously
4. **Expected:** No crash, independent uploads work correctly

### Test Scenario 3: Rapid Sequential Uploads
1. Upload to 7 servers
2. Immediately upload again (before first completes)
3. Repeat 3-4 times rapidly
4. **Expected:** Queue properly, no race conditions, no crashes

### Test Scenario 4: collect_prepost_checked
1. Enable "Collect Pre/Post" checkbox
2. Upload to multiple servers
3. **Expected:** Proper command_mos.txt modification, no parameter errors

## Performance Improvements

1. **0.5s stagger delay** - Prevents simultaneous resource access
2. **Thread locks** - Ensures atomic file operations
3. **Unique temp directories** - Eliminates file conflicts
4. **Connection timeouts** - Prevents indefinite hangs
5. **Better cleanup** - Releases resources promptly

## Code Quality Improvements

1. **Better error logging** - Uses debug_print() for troubleshooting
2. **Safer cleanup** - Try-except blocks around all cleanup operations
3. **Resource initialization** - Proper None checks before cleanup
4. **Type safety** - Better handling of None values

## Files Modified

1. `lib/SSHTab.py` - Fixed method signatures, improved error handling
2. `lib/workers.py` - Added thread safety, resource management
3. `GUI.py` - Added staggered upload initiation

## Backward Compatibility

All changes are backward compatible:
- No API changes to public methods (only added optional parameters)
- Default values provided for new parameters
- Existing functionality preserved
