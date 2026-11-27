"""Copy the reviewed local MiniLM snapshot; does not install or download anything."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "processing"))

from device_health_investigation.model_assets import (  # noqa: E402
    DEFAULT_MANIFEST,
    ModelAssetError,
    load_model_manifest,
    prepare_local_model,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        destination, created = prepare_local_model(args.source, args.destination, args.manifest)
        manifest = load_model_manifest(args.manifest)
    except ModelAssetError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({
        "model_dir": str(destination), "revision": manifest["revision"],
        "files": len(manifest["files"]), "status": "prepared" if created else "reused",
        "downloads": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
