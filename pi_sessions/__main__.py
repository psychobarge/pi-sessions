from __future__ import annotations

import sys

from .core.resume import ResumeError, ResumeRequest, execute_resume
from .ui.app import PiSessionsApp


def main() -> int:
    app = PiSessionsApp()
    result = app.run()
    if isinstance(result, ResumeRequest):
        try:
            execute_resume(result)  # replaces process; does not return on success
        except ResumeError as e:
            print(f"Resume failed: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
