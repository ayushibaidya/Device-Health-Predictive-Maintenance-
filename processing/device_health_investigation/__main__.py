"""Validate or chunk an explicit local corpus; never download assets."""

import argparse
import json
import sys
from dataclasses import asdict

from .chunking import CHUNKER_VERSION, ChunkingConfig, ChunkingError, chunk_corpus
from .documents import DocumentError, load_corpus
from .tokenizer import MiniLMTokenizer, TokenizerUnavailable


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate and chunk local troubleshooting documents")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "chunk"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True)
        if name == "chunk":
            command.add_argument("--tokenizer", required=True, help="Approved local tokenizer.json")
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.manifest)
        output = {
            "schema_version": 1,
            "corpus_id": corpus.corpus_id,
            "review_status": corpus.review_status,
            "implementation_baseline": corpus.implementation_baseline,
            "documents": [
                {
                    "document_id": doc.document_id, "document_version": doc.document_version,
                    "source_path": doc.source_path, "title": doc.title,
                }
                for doc in corpus.documents
            ],
        }
        if args.command == "chunk":
            tokenizer = MiniLMTokenizer(args.tokenizer)
            config = ChunkingConfig()
            output["tokenizer_profile"] = tokenizer.profile
            output["chunking_profile"] = {"version": CHUNKER_VERSION, **asdict(config)}
            output["chunks"] = [asdict(chunk) for chunk in chunk_corpus(corpus, tokenizer, config)]
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except (DocumentError, ChunkingError) as error:
        code, status, message = "invalid_corpus", 2, str(error)
    except TokenizerUnavailable as error:
        code, status, message = "tokenizer_unavailable", 1, str(error)
    print(json.dumps({"error": {"code": code, "message": message}}), file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
