"""FinanceBench loader.

FinanceBench (Islam et al., 2023) is a benchmark of financial questions
grounded in SEC filings. The open subset contains 150 questions with
evidence text extracted from 10-K, 10-Q, and 8-K filings.

We use it as the second task domain in the crux experiment to test whether
per-model failure signatures observed on HotpotQA generalize to a very
different task type (financial extraction vs multi-hop QA over Wikipedia).

Access:
    Requires accepting the license on HuggingFace at:
    https://huggingface.co/datasets/PatronusAI/financebench

    On first call, this loader will attempt to download from HuggingFace.
    You may need to run `huggingface-cli login` first.
"""

from typing import Optional


# Max characters of evidence text to include per question. SEC filings can be
# thousands of pages; we truncate to keep prompts manageable and comparable to
# HotpotQA input sizes.
MAX_EVIDENCE_CHARS = 2000


def load_financebench(n: int = 30, split: str = "train") -> list[str]:
    """Load n questions from FinanceBench as combined question+context strings.

    Args:
        n: number of samples to return
        split: HuggingFace split name (FinanceBench primarily uses 'train')

    Returns:
        list of strings, each formatted as "Question: ...\\n\\nContext: ..."
    """
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError(
            "The `datasets` package is required. Run: pip install datasets"
        ) from e

    try:
        ds = load_dataset("PatronusAI/financebench", split=split)
    except Exception as e:
        raise RuntimeError(
            f"Failed to load FinanceBench from HuggingFace: {e}\n\n"
            "Fixes:\n"
            "  1. Visit https://huggingface.co/datasets/PatronusAI/financebench "
            "and accept the license.\n"
            "  2. Run `huggingface-cli login` and paste an access token.\n"
            "  3. Verify with: `python -c \"from datasets import load_dataset; "
            "print(load_dataset('PatronusAI/financebench', split='train')[0])\"`"
        ) from e

    n = min(n, len(ds))
    questions = []
    for i in range(n):
        item = ds[i]
        q = item.get("question", "")
        evidence = _extract_evidence(item)
        combined = _format_input(q, evidence)
        questions.append(combined)
    return questions


def _extract_evidence(item: dict) -> str:
    """Pull evidence text from a FinanceBench record, handling schema variants."""
    # FinanceBench records have evolved; try several field shapes.
    ev = item.get("evidence")
    if isinstance(ev, list) and ev:
        first = ev[0]
        if isinstance(first, dict):
            return first.get("evidence_text", "") or first.get("text", "")
        if isinstance(first, str):
            return first
    if isinstance(ev, str):
        return ev
    # Fallbacks
    return (
        item.get("evidence_text", "")
        or item.get("context", "")
        or item.get("answer_context", "")
        or ""
    )


def _format_input(question: str, evidence: str) -> str:
    """Combine question + evidence into a single input string for the graph."""
    if evidence and len(evidence) > MAX_EVIDENCE_CHARS:
        evidence = evidence[:MAX_EVIDENCE_CHARS] + " [...evidence truncated]"
    if evidence:
        return (
            f"Question: {question}\n\n"
            f"Context from financial filing:\n{evidence}"
        )
    return f"Question: {question}"