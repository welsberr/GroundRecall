# Native Windows PowerShell quickstart

This guide installs GroundRecall from a checkout and sets up one local memory
workspace for multiple assistants. It uses native Windows CPython 3.12 and
PowerShell; commands run the virtual environment's Python directly, so they do
not require PowerShell activation. GroundRecall requires Python 3.10 or newer.

## Select a native Python and install

Install native Windows CPython 3.12 and Git for Windows, then open PowerShell.
Git is needed to install the pinned Epistemap dependency. Check the interpreter
selected by the Python launcher:

```powershell
py -3.12 -c "import sys; print(sys.executable); print(sys.version); print(sys.platform)"
```

The platform should be `win32` and the executable should be the intended native
Windows Python. If the launcher cannot find it, use the full path to the native
`python.exe` for the version check and venv creation below. Avoid assuming that
`python` on PATH or `py -3` selects the intended interpreter.

Place the checkout somewhere the intended assistants can access, outside any
one assistant's private directory. For example, clone the repository into
`$env:USERPROFILE\GroundRecall\app`, then run:

```powershell
Set-Location "$env:USERPROFILE\GroundRecall\app"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m groundrecall --help
```

If a selected native interpreter is not registered with `py`, substitute its
path, for example `& 'C:\Python312\python.exe' -m venv .venv`. The install
needs access to the package dependencies and a working temporary directory. If
installation fails, check the selected runtime, Git, network, and the current
user's temporary-directory permissions. Environment-specific TLS or sandbox
failures do not by themselves establish a GroundRecall runtime bug.

## Initialize shared memory

The installation above is separate from the workspace, which holds source
notes, imports, the canonical store, and exports. For example, create a
workspace root alongside the checkout:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\GroundRecall\workspace" | Out-Null
$Root = "$env:USERPROFILE\GroundRecall\workspace"
.\.venv\Scripts\python.exe -m groundrecall protocol-init $Root --host-id windows-local --host-role development --assistant codex --assistant claude_code
```

The generated workspace is `$Root\.groundrecall`; the host and assistant
bootstrap files are under `$Root`. Give each intended local assistant access
to this location according to the operating system permissions and its own
sandbox settings. Tell each assistant to read the generated protocol and use
the same workspace; an assistant's private configuration or bundle does not
own the canonical memory. Assistants with local file access can use the
assistant-neutral protocol even if they do not support MCP. Coordinate changes
to the store so only one writer mutates it at a time. Different hosts should
maintain separate stores and exchange selected notes or exports, as described in
the [assistant protocol](assistant-protocol.md).

## Connect Codex over local stdio MCP

In the Codex user configuration at `%USERPROFILE%\.codex\config.toml`, add
the following table, replacing `YOURNAME` with the actual Windows user and
adjusting the path if the checkout is elsewhere:

```toml
[mcp_servers.groundrecall]
command = 'C:\Users\YOURNAME\GroundRecall\app\.venv\Scripts\python.exe'
args = ['-m', 'groundrecall.mcp']
```

These are TOML literal strings, so the Windows backslashes are not escape
characters. Restart Codex after saving. Confirm that GroundRecall tools are
available, then call `search_store` with a query and the absolute canonical
store path, for example `C:\Users\YOURNAME\GroundRecall\workspace\.groundrecall\store`.
The store path is a tool argument, not part of the server command. `search_store`
creates its index if absent or rebuilds it when requested. The index includes
canonical records and, for the standard layout, Markdown files directly under
the sibling `source-notes` directory; it does not cover every possible source
location. Search results can expose those notes, so grant clients access only
when they are authorized to read them. Each other MCP-capable
local assistant can configure the same executable and arguments using that
client's own settings. A web-only client cannot start a local stdio process;
see the repository's HTTP integration documentation for a separate deployment.

## Write and retrieve memory

Write durable Markdown notes in `$Root\.groundrecall\source-notes`. The
following example imports that directory, reviews and promotes the import,
then refreshes exports and the canonical-store FTS index. Run it from the
checkout as above; choose a new import ID for each import and replace
`your-name` with the reviewer identity.

```powershell
$Memory = Join-Path $Root '.groundrecall'
$Import = Join-Path $Memory 'imports\notes-example'
$Store = Join-Path $Memory 'store'
.\.venv\Scripts\python.exe -m groundrecall import (Join-Path $Memory 'source-notes') --out-root (Join-Path $Memory 'imports') --mode quick --import-id notes-example
.\.venv\Scripts\python.exe -m groundrecall lint $Import
.\.venv\Scripts\python.exe -m groundrecall review-server $Import
.\.venv\Scripts\python.exe -m groundrecall promote $Import $Store --reviewer your-name
.\.venv\Scripts\python.exe -m groundrecall export $Store (Join-Path $Memory 'exports\canonical')
.\.venv\Scripts\python.exe -m groundrecall assistant-export $Store codex (Join-Path $Memory 'exports\codex')
.\.venv\Scripts\python.exe -m groundrecall assistant-export $Store claude_code (Join-Path $Memory 'exports\claude_code')
.\.venv\Scripts\python.exe -m groundrecall index $Store --rebuild
.\.venv\Scripts\python.exe -m groundrecall index $Store 'your search terms'
```

Review the import in the workbench and resolve lint errors before promotion.
The review server runs until stopped. Produce assistant-specific exports only
for the assistants you use. MCP contribution and handoff proposal tools do not
promote canonical memory: source notes still go through the review and
promotion workflow above.

Canonical and assistant exports apply public export guardrails, so they can
omit private material and records that depend on excluded material. Export
filtering is not a license check; independently respect restrictions on
unlicensed material. If an export lacks needed context, an
authorized local user can inspect the original notes in
`$Root\.groundrecall\source-notes` or other approved source locations. Check
the export's guardrail report and respect the source's access and licensing
restrictions; do not copy protected material into an export to bypass them.
Store locations of secrets, not secret values.

The native Windows test covered installation, protocol initialization,
import/lint/promotion, export, FTS5 indexing, and stdio MCP initialization,
tool discovery, and search. It did not certify optional systemd, SIGHUP reload,
HTTP deployment, or federation.
