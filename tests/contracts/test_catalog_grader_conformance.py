from __future__ import annotations

from conformance import catalog_conformance, grader_conformance

from agentkit.catalog import LocalCatalog, SkillsCatalog
from agentkit.evals import Case
from agentkit.graders import (
    ContainsGrader,
    ExactMatchGrader,
    LLMJudgeGrader,
    SchemaGrader,
    TraceGrader,
)


async def test_local_catalog_conforms(tmp_path):
    await catalog_conformance(LocalCatalog(tmp_path))


async def test_skills_catalog_conforms(tmp_path):
    await catalog_conformance(SkillsCatalog(tmp_path))


async def test_reference_graders_conform():
    case = Case(name="c", input="2+2", expect="4")
    await grader_conformance(ExactMatchGrader(), case, "4")
    await grader_conformance(ContainsGrader(), case, "the answer is 4")
    await grader_conformance(SchemaGrader(), case, '{"a": 1}')
    await grader_conformance(TraceGrader(), case, [{"kind": "tool", "tool": "t"}])
    await grader_conformance(LLMJudgeGrader(criteria="be brief"), case, "4")
