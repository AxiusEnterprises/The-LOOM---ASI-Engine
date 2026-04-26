"""
LOOM Core — central orchestration layer for the ASI Engine.
"""


def weave(threads: list[dict]) -> dict:
    """Merge a list of reasoning threads into a unified response."""
    if not threads:
        return {"result": None, "confidence": 0.0}

    combined = " ".join(t.get("text", "") for t in threads)
    confidence = sum(t.get("weight", 1.0) for t in threads) / len(threads)
    return {"result": combined, "confidence": min(confidence, 1.0)}


if __name__ == "__main__":
    sample = [
        {"text": "The sky is blue", "weight": 0.9},
        {"text": "because of Rayleigh scattering", "weight": 0.85},
    ]
    output = weave(sample)
    print(output)
