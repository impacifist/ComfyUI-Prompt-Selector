# Validation record

Checked on 2026-10-06 before creating the local share archive.

| Check | Result |
| --- | --- |
| Standalone Python backend tests | 10 passed |
| Node.js library tests | 18 passed |
| Browser smoke checks, Canvas mode | 26 passed |
| Browser smoke checks, Vue mode | 26 passed |
| Public demo capture and text-only graph execution | Passed |
| Relative Markdown links | All targets exist |
| Example workflow contents | Public starter entries only; empty deleted slots; drafts match public selections |

The browser checks ran on the isolated ComfyUI instance at port 8198. Its installed frontend files were compared byte-for-byte with this package's three frontend files and matched. The standalone package backend was tested separately with its own unit tests. This is not a claim of compatibility with every ComfyUI version.

The examples contain only PromptSelector and built-in PreviewAny nodes. The node's public package excludes the source installation's I2V/Ollama helpers. These checks were completed before the initial GitHub publication; they do not include registry registration.

The author subsequently selected the MIT License. The root LICENSE, package metadata, and both READMEs reflect that choice. The share archive was rebuilt and checked to include the license and updated files; runtime code was unchanged.

The share ZIP uses an explicit file list and excludes browser test artifacts, Python caches, private workflows, and local server state.
