# Third-party notices

Ultron incorporates design patterns and a small set of vendored configuration
files derived from third-party open-source projects. Each is listed below with
its license and the scope of what was incorporated.

## aider (Apache License 2.0)

Repository: https://github.com/Aider-AI/aider
License: Apache License, Version 2.0 (a copy is included verbatim below).

The following ultron components are clean-room re-implementations whose
*approach* was informed by the corresponding aider modules. No source code
is copied verbatim except for the vendored tree-sitter query files listed
in the next paragraph.

| Ultron component | Inspired by | Notes |
| --- | --- | --- |
| `src/ultron/coding/important_files.py` | `aider/special.py` | Allowlist of well-known root files. List extended with ultron-specific entries. |
| `src/ultron/utils/mtime_cache.py` | `aider/repomap.py` cache layer | mtime-keyed SQLite cache with dict fallback. |
| `src/ultron/utils/token_budget.py` | `aider/repomap.py` binary search | Token-budget binary search with tolerance. |
| `src/ultron/utils/snapshot_guard.py` | `aider/coders/base_coder.py` summarize race protection | Snapshot-identity guard for background work. |
| `src/ultron/utils/relative_indent.py` | `aider/coders/search_replace.py` `RelativeIndenter` | Indent-relative text transform. |
| `src/ultron/coding/tree_sitter_tags.py` | `aider/repomap.py` `get_tags_raw` | Tree-sitter symbol extraction with pygments ref fallback. |
| `src/ultron/coding/repo_map.py` | `aider/repomap.py` | PageRank-weighted repo map (batch 2). |
| `src/ultron/memory/background_summarizer.py` (tail-preserve revisions) | `aider/history.py` | Tail-preserve binary split + race-protected summarize (batch 3). |
| `src/ultron/coding/python_lint.py` | `aider/linter.py` | Fatal-only Python lint cascade (batch 4). |

### Vendored tree-sitter query files

The `src/ultron/coding/queries/` directory contains tree-sitter `*-tags.scm`
files adapted from
`aider/queries/tree-sitter-language-pack/*-tags.scm`. Each file carries a
short attribution header. These query files are configuration data describing
how to extract symbol definitions and references from a parsed AST, not
executable source code.

### Apache License 2.0 (verbatim)

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
   implied. See the License for the specific language governing permissions
   and limitations under the License.
```

The full Apache License 2.0 text is available at the URL above. Section 4(c)
requires retention of copyright notices in derivative works; this file
satisfies that obligation for the components listed above.
