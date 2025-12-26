# Branch Status: qtpy/Nuitka Migration (nuitka branch)

This branch contains work toward modernizing the build system and Python compatibility. It diverges from sval-gui (the reference 3.6/fbs branch) before the native Python version work began, making it a clean merge point if needed.

## Summary

| Component | sval-gui (reference) | nuitka (this branch) |
|-----------|---------------------|-------------|
| Desktop Python | 3.6 | System Python 3.x |
| Web Python | 3.10/3.11 | 3.10/3.11 |
| Qt bindings | PyQt5 direct | qtpy abstraction |
| Desktop build | fbs freeze | Nuitka standalone |
| Linux base | Ubuntu 18.04 | Ubuntu 22.04 |
| Web container | ghcr.io/ilc/vial-gui-build | Same (with qtpy/packaging added) |

## Web Build (Working)

The web build has been tested and works with the existing ilc container (Python 3.10/3.11).

### Changes from sval-gui

**webmain.py**: Changed imports from PyQt5 to qtpy:
```python
# Before
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal

# After
from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Signal
```

The `init_storage()` and `set_theme()` functions are unchanged from sval-gui.

**build.sh**: Added lines to copy qtpy and packaging from container:
```bash
cp -r /vial-web/deps/qtpy usr/local/lib/python3.11/
cp -r /vial-web/deps/packaging usr/local/lib/python3.11/
```

**build-local.sh**: Same but copies from local `web/qtpy/` and `web/packaging/` directories for testing before container is updated.

### Container Updates (ilc-web repo)

The ilc-web repo (builds ghcr.io/ilc/vial-gui-build) was updated to include qtpy and packaging:

- **version.sh**: Added QTPY_VER, QTPY_HASH, PACKAGING_VER, PACKAGING_HASH
- **fetch-deps.sh**: Downloads QtPy-2.4.3 and packaging-24.2 wheels from ilc/vial-deps
- **build-deps.sh**: Extracts wheels to /vial-web/deps/

Wheels uploaded to both ilc/vial-deps and svalboard/vial-deps releases (v1).

### Architecture

The web build uses the original sval-gui architecture:
- PROXY_TO_PTHREAD (main runs in worker thread)
- worker.js appended to .worker.js
- sed hack intercepts worker messages for my_onmessage routing
- main.c calls execLastQApp() directly

This architecture works. The earlier py312 experiments with ASYNCIFY and event bridges were abandoned.

### Container Stack

The working container (ghcr.io/ilc/vial-gui-build) has:
- Python 3.11 (libpython3.11.a compiled for WASM)
- Qt 5.14.2 (qt-everywhere-src)
- PyQt5 5.15.2
- SIP 5.5.0 / PyQt5_sip 12.8.1
- Emscripten SDK

Note: Qt 5.14.2 and PyQt5 5.15.2 are mismatched versions but work together. This is a fragile equilibrium - changing any component risks breaking the stack.

Python 3.12 was attempted but failed due to PyQt5/SIP compatibility issues with removed deprecated APIs. Would require newer PyQt5 (5.15.9+) and SIP.

## Native Builds (Untested on this branch)

The native builds have been reworked for Nuitka but may not be fully tested.

### Linux

**util/linux-builder/Dockerfile**:
- Ubuntu 22.04 (was 18.04)
- System Python 3 (was custom 3.6)
- appimagetool (was pkg2appimage)

**util/linux-builder/_builder.sh**:
- Uses Nuitka via `build-nuitka/build-linux.sh`
- Sets `QT_API=pyside6`
- Custom AppImage creation

**build-nuitka/build-linux.sh**:
- Nuitka standalone with `--enable-plugin=pyside6`

### Windows

**build-nuitka/build-windows.bat**:
- Nuitka standalone with `--enable-plugin=pyqt5` (note: different from Linux)

**build-nuitka/installer.iss**:
- Inno Setup 6.x script

### Discrepancy

Linux uses PySide6, Windows uses PyQt5. Both work via qtpy abstraction, but this inconsistency may need resolution.

## Local Testing (Web)

Until the container rebuild completes, local web testing requires:

1. Local qtpy and packaging directories in `web/`:
   ```bash
   # Copy from py312 container (has these packages)
   podman run --rm -v $(pwd)/web:/out localhost/vial-web-py312:latest \
     cp -r /vial-web/deps/qtpy-2.4.3/qtpy \
           /vial-web/deps/venv/lib/python3.12/site-packages/packaging /out/
   ```

2. Use build-local.sh (copies from local dirs) instead of build.sh (copies from container)

3. Run with existing container:
   ```bash
   podman run --rm -v $(pwd):/gui ghcr.io/ilc/vial-gui-build:latest \
     bash -c 'cd /gui/web && ./build-local.sh'
   ```

4. Serve and test:
   ```bash
   cd web/build && python3 http-server-cors.py
   # Open http://localhost:8000
   ```

## Files Changed from sval-gui

### Python (qtpy imports)
- `src/main/python/webmain.py` - qtpy imports
- Other Python files with PyQt5 imports need qtpy conversion

### Web Build
- `web/build.sh` - copies qtpy/packaging from container
- `web/build-local.sh` - copies from local dirs

### Native Build (Nuitka)
- `build-nuitka/build-linux.sh` - new
- `build-nuitka/build-windows.bat` - new
- `build-nuitka/installer.iss` - new
- `util/linux-builder/Dockerfile` - Ubuntu 22.04, appimagetool
- `util/linux-builder/_builder.sh` - Nuitka workflow

### Not Changed
- `web/main.c` - identical to sval-gui
- `web/worker.js` - identical to sval-gui
- `web/index.html` - identical to sval-gui

## Resuming This Work

1. The web build works now with Python 3.10/3.11
2. Container will have qtpy/packaging after rebuild (~2 hours from commit)
3. Native builds need testing
4. qtpy migration of remaining Python files may be incomplete
5. PySide6 vs PyQt5 backend choice needs decision

## Lessons Learned (Python 3.12 / WASM Experiments)

The following approaches were tried and failed. Documented here as warnings for future explorers.

### ASYNCIFY Instead of PROXY_TO_PTHREAD

**Tried:** Replace PROXY_TO_PTHREAD with ASYNCIFY to allow synchronous Python code to yield to the browser event loop.

**Failed because:** ASYNCIFY significantly increases code size and has performance overhead. More critically, Qt's WASM event dispatcher and Python's interaction with it didn't work reliably - resulted in MainLoop.scheduler errors and hangs.

**Lesson:** PROXY_TO_PTHREAD is the architecture that works. Qt expects to own its event loop, and running main() in a pthread lets that happen.

### Event Bridge Between Threads

**Tried:** Create an event_bridge.py to proxy Qt signals/events between the main browser thread and the Python worker thread.

**Failed because:** The complexity exploded. Qt WASM already has its own event handling that works with PROXY_TO_PTHREAD. Adding another layer created race conditions and didn't solve the underlying Qt initialization issues.

**Lesson:** Don't fight the existing architecture. The sed hack that intercepts worker messages is simple and works.

### Qt Cursor/Event Dispatcher Patches

**Tried:** Patch Qt's WASM cursor handling (qwasmcursor.cpp) and event dispatcher to fix crashes in py312 builds.

**Failed because:** These were symptoms, not causes. The crashes stemmed from component version mismatches (Python 3.12 + older PyQt5/SIP). Patching Qt was whack-a-mole.

**Lesson:** The container's component matrix (Qt 5.14.2, PyQt5 5.15.2, Python 3.11, specific emscripten version) is a fragile equilibrium. Changing Python version requires updating PyQt5 and SIP to versions that support it.

### Python 3.12 with PyQt5 5.15.2

**Tried:** Use Python 3.12 with the existing PyQt5 5.15.2 / SIP 5.5.0.

**Failed because:** Python 3.12 removed deprecated C APIs that PyQt5 5.15.2 and SIP 5.5.0 depend on. Results in crashes and undefined behavior.

**Lesson:** Python 3.12 requires PyQt5 5.15.9+ and newer SIP. This means rebuilding the entire container stack. The current 3.11 stack works; don't upgrade Python without upgrading PyQt5/SIP.

### Summary for Future Explorers

If you want to upgrade Python for WASM builds:

1. **Don't just change CPYTHON_VER** - you need matching PyQt5 and SIP versions
2. **Don't switch from PROXY_TO_PTHREAD** - it's the working architecture
3. **Don't add complexity** (event bridges, async wrappers) - the simple approach works
4. **Test incrementally** - the interaction between emscripten, Qt WASM, PyQt5, and Python is fragile
5. **Consider whether it's worth it** - 3.11 works, native builds can use any Python version

## Why This Branch Exists

- Modernize from Python 3.6 to newer versions
- Abstract Qt bindings via qtpy for flexibility
- Replace fbs (abandoned) with Nuitka
- Keep web build working while updating native builds

The branch preserves a clean merge point before native Python changes, so web work can be integrated independently.
