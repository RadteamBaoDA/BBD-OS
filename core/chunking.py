import codecs
from bisect import bisect_right
from dataclasses import dataclass

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class ChunkDraft:
    """Immutable text chunk plus its tokenizer count and source-position metadata."""
    content: str
    token_count: int
    metadata: dict[str, object]


def chunk_text(text: str, target_tokens: int = 750, overlap_ratio: float = 0.12) -> list[ChunkDraft]:
    """Split text into UTF-8-safe token chunks, retaining the configured overlap and each chunk start offset. Reject invalid settings; empty text returns no chunks."""
    if target_tokens < 1 or not 0 <= overlap_ratio < 1:
        raise ValueError("Invalid chunking settings")
    tokens = ENCODING.encode(text, disallowed_special=())
    if not tokens:
        return []
    token_bytes = [ENCODING.decode_single_token_bytes(token) for token in tokens]
    boundaries = [0]
    # Token boundaries can split one UTF-8 character; retain only offsets where decoding has no pending bytes.
    decoder = codecs.getincrementaldecoder("utf-8")()
    for index, token in enumerate(token_bytes, start=1):
        decoder.decode(token)
        if not decoder.getstate()[0]:
            boundaries.append(index)
    overlap = min(target_tokens - 1, int(target_tokens * overlap_ratio))
    chunks = []
    start = 0
    while start < len(tokens):
        desired_end = min(start + target_tokens, len(tokens))
        # Snap chunk ends and overlap starts to valid text boundaries; nominal token sizes can shift slightly.
        end_pos = bisect_right(boundaries, desired_end) - 1
        end = boundaries[end_pos] if end_pos >= 0 and boundaries[end_pos] > start else boundaries[bisect_right(boundaries, start)]
        content = b"".join(token_bytes[start:end]).decode("utf-8")
        chunks.append(ChunkDraft(content, end - start, {"start_token": start}))
        if end == len(tokens):
            break
        next_start = start + 1
        overlap_boundary = end - overlap
        overlap_pos = bisect_right(boundaries, overlap_boundary) - 1
        start = boundaries[overlap_pos] if overlap_pos >= 0 and boundaries[overlap_pos] >= next_start else end
    return chunks
