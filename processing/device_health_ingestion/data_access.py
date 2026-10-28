"""Inspect app-ready telemetry without needing an API server yet."""

import argparse
import json
import sys

from .latest import LatestState, configured_cache
from .queries import TelemetryQueries
from .store import database_dsn


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    history = commands.add_parser("history")
    history.add_argument("device_id")
    history.add_argument("--run-id")
    history.add_argument("--start")
    history.add_argument("--end")
    history.add_argument("--limit", type=int, default=100)
    history.add_argument("--before", type=int)
    commands.add_parser("latest").add_argument("device_id")
    commands.add_parser("rebuild-cache")
    args = parser.parse_args(argv)
    queries, cache = None, None
    try:
        queries = TelemetryQueries(database_dsn())
        cache = configured_cache()
        latest = LatestState(queries, cache)
        if args.command == "history":
            result = queries.history(
                args.device_id,
                run_id=args.run_id,
                start=args.start,
                end=args.end,
                limit=args.limit,
                before=args.before,
            )
        elif args.command == "latest":
            reading = latest.get(args.device_id)
            result = reading.as_dict() if reading is not None else None
        else:
            result = latest.rebuild()
        print(json.dumps(result, sort_keys=True))
        return int(args.command == "rebuild-cache" and result["failed"] > 0)
    except Exception as error:
        # Driver messages may contain credentials. Never echo the connection URL.
        print(json.dumps({"error": type(error).__name__}), file=sys.stderr)
        return 1
    finally:
        if queries is not None:
            queries.close()
        if cache is not None:
            cache.close()


if __name__ == "__main__":
    sys.exit(main())
