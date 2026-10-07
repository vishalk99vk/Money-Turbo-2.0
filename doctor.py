"""Check that this installation is ready: python doctor.py [--json]"""

import json
import sys

from app.services import diagnostics


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    report = diagnostics.run_diagnostics()
    if "--json" in argv:
        print(json.dumps(report, indent=2))
    else:
        print(diagnostics.format_report(report))
    return 1 if report["status"] == diagnostics.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
