"""3-node sequential chain: identify -> gather -> answer.

The three node schemas are now injected as a parameter, so the same topology
runs against any registered schema tier (medium, medium_v2, future high, etc.).
"""

import uuid
from typing import Callable, Optional

from schemaeval.schemas import get_schemas


# A paradigm function: (prompt, schema, model, max_retries) -> (validated_or_None, metrics)
ParadigmFn = Callable[..., tuple[Optional[object], dict]]


def run_sequential_graph(
    question: str,
    paradigm_fn: ParadigmFn,
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
    schemas: Optional[tuple] = None,
) -> dict:
    """Run the 3-node chain end to end. Returns per-run + per-node metrics.

    Args:
        schemas: tuple of (IdentifyOutput, GatherOutput, AnswerOutput) Pydantic
                 classes. If None, defaults to the 'medium' tier for backward
                 compatibility with the pilot.
    """
    if schemas is None:
        schemas = get_schemas("medium")
    IdentifyOutput, GatherOutput, AnswerOutput = schemas

    run_id = str(uuid.uuid4())
    per_node: dict[str, dict] = {}

    # ---- Node 1: identify ----
    prompt1 = (
        f"Identify the key entities and question type in this question:\n"
        f"{question}\n\n"
        "For each entity, provide a canonical_id in lowercase snake_case "
        "(e.g. 'manchester_united', 'kansas_university')."
    )
    identify_out, m1 = paradigm_fn(
        prompt1, IdentifyOutput, model=model, max_retries=max_retries
    )
    per_node["identify"] = m1
    if identify_out is None:
        return _package(run_id, question, per_node, final_answer=None)

    # ---- Node 2: gather ----
    entities_str = "\n".join(
        f"- name='{e.name}' type={e.entity_type} canonical_id={e.canonical_id}"
        for e in identify_out.entities
    )
    prompt2 = (
        f"Question: {question}\n\n"
        f"Entities to research:\n{entities_str}\n\n"
        "For each entity, provide 1-3 facts relevant to answering the question. "
        "Use the exact canonical_id values shown above when referencing entities."
    )
    gather_out, m2 = paradigm_fn(
        prompt2, GatherOutput, model=model, max_retries=max_retries
    )
    per_node["gather"] = m2
    if gather_out is None:
        return _package(run_id, question, per_node, final_answer=None)

    # ---- Node 3: answer ----
    facts_str = "\n".join(
        f"- entity_id={f.entity_id}: {f.fact}" for f in gather_out.facts
    )
    prompt3 = (
        f"Question: {question}\n\n"
        f"Known facts:\n{facts_str}\n\n"
        "Synthesize a final answer. In supporting_entity_ids, list the "
        "canonical_id values (snake_case) of the entities that support your answer."
    )
    answer_out, m3 = paradigm_fn(
        prompt3, AnswerOutput, model=model, max_retries=max_retries
    )
    per_node["answer"] = m3
    final_answer = answer_out.answer if answer_out else None

    return _package(run_id, question, per_node, final_answer)


def _package(
    run_id: str, question: str, per_node: dict, final_answer: Optional[str]
) -> dict:
    total_input = sum(m["total_input_tokens"] for m in per_node.values())
    total_output = sum(m["total_output_tokens"] for m in per_node.values())
    total_repairs = sum(m["num_repairs"] for m in per_node.values())
    total_latency = sum(m["latency_sec"] for m in per_node.values())
    graph_success = (
        len(per_node) == 3 and all(m["success"] for m in per_node.values())
    )

    return {
        "run_id": run_id,
        "question": question,
        "final_answer": final_answer,
        "graph_success": graph_success,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_repairs": total_repairs,
        "total_latency_sec": round(total_latency, 3),
        "per_node": per_node,
    }