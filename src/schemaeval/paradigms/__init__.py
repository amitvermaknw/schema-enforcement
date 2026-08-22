"""Enforcement paradigms — the paper's core independent variable."""

from schemaeval.paradigms.strict_repair import call_llm_strict_repair

# Later paradigms will land here as separate modules:
# from schemaeval.paradigms.free_form import call_llm_free_form
# from schemaeval.paradigms.constrained import call_llm_constrained
# from schemaeval.paradigms.hybrid import call_llm_hybrid

__all__ = ["call_llm_strict_repair"]
