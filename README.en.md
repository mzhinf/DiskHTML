# DiskHTML

[中文](README.md) | [English](README.en.md)

DiskHTML is a Windows 10/11 directory snapshot and Hash precheck/comparison tool. It uses full SHA-256 by default and can use a fixed-target-read, fixed-count sampled fingerprint for large-file prechecks. A sampled match is not proof of full content equality.

## Key features

- Create directory snapshots: produce one visual HTML file and a same-named SQLite index.
- Create comparison reports: choose any directory inside a historical HTML snapshot and compare it with any local directory.
- Render from SQLite: generate the current HTML format from a historical index without rescanning the source directory.
- Record Name, Size, Modified, Created, digest, exact algorithm, volume details, and optional physical disk details.
- Generated HTML has no external CDN dependency and can be opened, searched, sorted, exported, and switched between Chinese and English offline.
- The desktop app supports Chinese and English. Use the language selector in the lower-right status bar; switching languages keeps the paths and options already entered.

## Windows usage

The release is a portable directory package, not a single EXE that can be copied alone. Download and completely extract `DiskHTML-win-x64.zip`, then run:

~~~text
DiskHTML\DiskHTML.exe
DiskHTML\_internal\...
DiskHTML\config.toml (created on first launch)
~~~

Keep `DiskHTML.exe` and `_internal` together. Copying only the EXE causes `Failed to load Python DLL`.

The release embeds its default template at `_internal\config\config.example.toml`. On first launch, the EXE copies it to `config.toml` beside `DiskHTML.exe` if that file does not already exist. Later launches preserve user edits. The desktop app and EXE CLI load this file by default; an explicit `--config` path still takes precedence.

The desktop app has three task tabs:

1. **Create Snapshot**: choose a source directory and output HTML.
2. **Create Comparison**: choose a baseline snapshot, its directory, the current directory, and an output report.
3. **Render from SQLite**: choose a `.sqlite3` index and a new HTML path.

Command-line examples:

~~~cmd
DiskHTML.exe snapshot F:\Documents .\Documents_snapshot.html
DiskHTML.exe compare-source .\Documents_snapshot.html Documents\Photos E:\CurrentPhotos .\Photos_comparison.html
DiskHTML.exe render-sqlite .\Documents_snapshot.sqlite3 .\Documents_snapshot-new.html
~~~

For complete steps, see the [DiskHTML.exe guide](docs/diskhtml-exe-guide.md) and [user guide](docs/user-guide.md). These detailed guides are currently maintained in Chinese.

## Development and testing

DiskHTML requires Python 3.12 and uses the project `.venv`:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
~~~

The build does not require PowerShell:

~~~powershell
.\.venv\Scripts\python.exe .\scripts\build_windows.py --clean
.\.venv\Scripts\python.exe .\scripts\verify_release.py .\build\release\DiskHTML-win-x64.zip
~~~

`scripts/build_windows.ps1` is an optional wrapper for familiar workflows. See [Windows build and acceptance](docs/windows-build.md) for details.

## Documentation

The [documentation index](docs/README.md) lists the purpose, audience, and maintenance trigger for every maintained document. The [architecture guide](docs/architecture.md) lists entry points, module responsibilities, dependency boundaries, and the three core data flows.

## Known boundaries

- Browser security prevents offline HTML from scanning arbitrary local directories; directory comparison scans are performed by the EXE.
- Physical disk model, serial number, and partition details use a best-effort PowerShell query. A failure does not block scanning, hashing, HTML, or SQLite output.
- Releases use a PyInstaller `onedir` directory package and ZIP, not a `onefile` executable.

## License status

DiskHTML is released under the [MIT License](LICENSE). The build derives an English notice and complete license texts for Python, Tcl/Tk, PyInstaller, Lucide, and the native components actually present in the final package. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [docs/release-licenses.md](docs/release-licenses.md).
