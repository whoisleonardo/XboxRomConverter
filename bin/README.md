# bin/ – Bundled Conversion Binaries

Place the following Windows executables in this directory before packaging:

| File          | Purpose                                      | Source                            |
|---------------|----------------------------------------------|-----------------------------------|
| `exiso.exe`   | Extract XEX content from an Xbox 360 ISO     | https://github.com/Halofreak1990/exiso (or equivalent) |
| `iso2god.exe` | Convert Xbox 360 ISO to Games-on-Demand format | https://www.360haven.com/forums/  |

Both tools are third-party; ensure you have the right to distribute them
alongside this application.

The binaries are resolved at runtime via:

```python
import os, sys
base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath('.')
exe  = os.path.join(base, 'bin', 'exiso.exe')
```

PyInstaller is configured (see `romtool.spec`) to include the entire `bin/`
directory in the frozen bundle using the `--add-data` flag.
