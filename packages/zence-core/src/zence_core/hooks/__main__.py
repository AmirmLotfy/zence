"""Entry point for `python -m zence_core.hooks`.

This module exists to keep Claude Code's hook output clean. Invoking
`python -m zence_core.hooks.main` makes runpy import the package first — whose
`__init__` re-exports from `main` — and then execute `main` as `__main__`, which
it warns about:

    RuntimeWarning: 'zence_core.hooks.main' found in sys.modules after import of
    package 'zence_core.hooks', but prior to execution of 'zence_core.hooks.main'

Harmless to the decision, but Claude Code surfaces a hook's stderr, so every user
saw a Python warning on every tool call. Running `__main__` instead is a
different module from `main`, so nothing is executed twice and nothing warns.

Found by running the plugin inside a real Claude Code session and reading the
hook_response, which is the only place it was visible.
"""

from __future__ import annotations

from zence_core.hooks.main import main

if __name__ == "__main__":
    main()
