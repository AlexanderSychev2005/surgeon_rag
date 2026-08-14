from typing import List

def chunk_text(text: str, max_chars: int = 1200) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(p) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            sentences = p.split(". ")
            piece = ""
            for s in sentences:
                if len(piece) + len(s) > max_chars and piece:
                    chunks.append(piece)
                    piece = ""
                piece += s + ". "
            if piece:
                chunks.append(piece.strip())
            continue
        if len(current) + len(p) > max_chars:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


def demo() -> None:
    text = ("Intro paragraph. " * 20 + "\n") + ("Methods paragraph. " * 100) + "\n" + "Short tail."
    chunks = chunk_text(text, max_chars=300)
    assert chunks and all(len(c) <= 400 for c in chunks)  # a little slack for sentence overshoot
    assert "".join(chunks).replace("\n", "").strip() != ""
    print(f"OK: {len(chunks)} chunks, sizes={[len(c) for c in chunks]}")


if __name__ == "__main__":
    demo()
