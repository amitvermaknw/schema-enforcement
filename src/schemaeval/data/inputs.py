"""Input samples. Pilot uses hardcoded questions; full runs use HotpotQA."""

PILOT_SAMPLES = [
    "Which magazine was started first, Arthur's Magazine or First for Women?",
    "The Oberoi family is part of a hotel company that has a head office in what city?",
    "In what year was Manchester United football club founded, and who founded it?",
    "What is the name of the fight song of the university whose main campus is in Lawrence, Kansas?",
    "Are Random House Tower and 888 7th Avenue both used for real estate?",
]


def load_hotpotqa(n: int = 30, split: str = "validation") -> list[str]:
    """Load n questions from HotpotQA (distractor setting).

    Requires: pip install datasets
    Downloads on first call (cached to ~/.cache/huggingface).
    """
    from datasets import load_dataset

    ds = load_dataset("hotpot_qa", "distractor", split=split)
    return [ds[i]["question"] for i in range(n)]
