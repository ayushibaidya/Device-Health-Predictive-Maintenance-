"""Validate, chunk, index or query an explicit local corpus; never download assets."""

import argparse
import json
import sys
from dataclasses import asdict

from .chunking import CHUNKER_VERSION, ChunkingConfig, ChunkingError, chunk_corpus
from .documents import DocumentError, load_corpus
from .embeddings import EmbeddingFailed, EmbeddingInputError, EmbeddingUnavailable, MiniLMEncoder
from .index import IndexBusy, IndexInvalid, build_index, load_index
from .tokenizer import MiniLMTokenizer, TokenizerUnavailable


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local troubleshooting document preparation and search")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "chunk"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True)
        if name == "chunk":
            command.add_argument("--tokenizer", required=True, help="Approved local tokenizer.json")
    for name in ("build-index", "search"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True)
        command.add_argument("--model-dir", required=True, help="Prepared local MiniLM directory")
        command.add_argument("--index", required=True, help="Local derived JSON index path")
        if name == "search":
            command.add_argument("--question", required=True)
            command.add_argument("--limit", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if args.command in {"build-index", "search"}:
            encoder = MiniLMEncoder(args.model_dir)
            from pathlib import Path

            tokenizer = MiniLMTokenizer(Path(args.model_dir) / "tokenizer.json")
            if args.command == "build-index":
                index, reused = build_index(args.index, args.manifest, encoder, tokenizer)
                output = {
                    "status": "reused" if reused else "built", "index_id": index.index_id,
                    "corpus_id": index.corpus_id, "review_status": index.review_status,
                    "chunk_count": len(index.chunks),
                }
            else:
                index = load_index(args.index, args.manifest, encoder, tokenizer)
                output = {
                    "index_id": index.index_id, "review_status": index.review_status,
                    "relevance": "uncalibrated", "score_kind": "cosine_similarity",
                    "candidates": [asdict(hit) for hit in index.search(
                        args.question, encoder, args.limit,
                    )],
                }
            print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
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
    except EmbeddingInputError as error:
        code, status, message = "invalid_embedding_input", 2, str(error)
    except (EmbeddingUnavailable, EmbeddingFailed) as error:
        code, status, message = "embedding_unavailable", 1, str(error)
    except IndexBusy as error:
        code, status, message = "index_busy", 1, str(error)
    except IndexInvalid as error:
        code, status, message = "invalid_index", 1, str(error)
    print(json.dumps({"error": {"code": code, "message": message}}), file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
