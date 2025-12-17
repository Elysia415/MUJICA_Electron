import json

from src.data_engine.storage import KnowledgeBase
from src.planner.agent import PlannerAgent
from src.researcher.agent import ResearcherAgent
from src.writer.agent import WriterAgent
from src.verifier.agent import VerifierAgent


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResp:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class FakeLLM:
    """
    测试用：最小可用的 OpenAI-compatible client stub。
    仅覆盖本项目会调用到的：llm.chat.completions.create(...)
    """

    class chat:
        class completions:
            @staticmethod
            def create(*, model: str, messages, **kwargs):  # noqa: ANN001
                user_content = ""
                if messages and isinstance(messages, list):
                    user_content = (messages[-1] or {}).get("content", "") or ""

                # Planner
                if "User Query:" in user_content and "Database Stats:" in user_content:
                    plan = {
                        "title": "Offline Test Report",
                        "global_filters": {},
                        "sections": [
                            {
                                "name": "Method Comparison",
                                "search_query": "RLHF DPO alignment preference optimization",
                                "filters": {},
                                "top_k_papers": 2,
                                "top_k_chunks": 30,
                            }
                        ],
                        "estimated_papers": 2,
                    }
                    return _FakeResp(json.dumps(plan, ensure_ascii=False))

                # Researcher (expects JSON)
                if "Evidence Snippets" in user_content and "key_points" in user_content:
                    # 尝试从 Evidence 中提取一个可用 citation
                    paper_id = "p_rlhf"
                    chunk_id = "p_rlhf::title_abstract::0"
                    for line in user_content.splitlines():
                        if line.strip().startswith("[Paper ID:") and "Chunk:" in line:
                            # [Paper ID: xxx | Chunk: yyy | Source: zzz]
                            try:
                                seg = line.strip().strip("[]")
                                # Paper ID: xxx | Chunk: yyy | Source: ...
                                parts = [p.strip() for p in seg.split("|")]
                                paper_id = parts[0].split(":", 1)[1].strip()
                                chunk_id = parts[1].split(":", 1)[1].strip()
                                break
                            except Exception:
                                pass

                    out = {
                        "summary": "离线测试研究笔记：基于入库样本文本，提取 RLHF 与 DPO 的对比要点。",
                        "key_points": [
                            {
                                "point": "RLHF 与 DPO 都用于对齐/偏好优化，但路径与训练信号不同。",
                                "citations": [{"paper_id": paper_id, "chunk_id": chunk_id}],
                            }
                        ],
                    }
                    return _FakeResp(json.dumps(out, ensure_ascii=False))

                # Verifier (NLI)
                if '"label": "entailed|contradicted|unknown"' in user_content or "label" in user_content and "Evidence:" in user_content:
                    out = {"label": "entailed", "score": 1.0, "reason": "evidence supports claim (offline stub)"}
                    return _FakeResp(json.dumps(out, ensure_ascii=False))

                # Writer (Markdown)
                if "Sections (JSON):" in user_content:
                    try:
                        payload = user_content.split("Sections (JSON):", 1)[1]
                        payload = payload.split("请生成完整 Markdown 报告。", 1)[0].strip()
                        sections = json.loads(payload)
                    except Exception:
                        sections = []

                    lines = ["# Offline Test Report"]
                    for s in sections or []:
                        sec_name = s.get("section") or "Section"
                        lines.append(f"## {sec_name}")
                        # 用 key_points 生成最小报告
                        kps = s.get("key_points") or []
                        if kps:
                            for kp in kps:
                                point = kp.get("point", "")
                                refs = kp.get("refs") or []
                                if refs:
                                    rid = refs[0]
                                else:
                                    rid = (s.get("allowed_refs") or ["R1"])[0]
                                lines.append(f"- {point} [{rid}]")
                        else:
                            lines.append(s.get("summary") or "证据不足。")
                    return _FakeResp("\n".join(lines))

                return _FakeResp("")


def test_full_chain_offline(tmp_path, monkeypatch):
    # 离线 embedding：让 KB 入库/检索在无 API Key 环境下也能跑通
    monkeypatch.setenv("MUJICA_FAKE_EMBEDDINGS", "1")
    monkeypatch.setenv("MUJICA_FAKE_EMBEDDING_DIM", "64")

    kb = KnowledgeBase(db_path=str(tmp_path / "lancedb_test"))
    kb.initialize_db()

    sample_papers = [
        {
            "id": "p_rlhf",
            "title": "Alignment via RLHF",
            "abstract": "We improve LLM alignment using Reinforcement Learning from Human Feedback.",
            "content": "RLHF is great.",
            "authors": ["Alice"],
            "year": 2024,
            "rating": 9.0,
        },
        {
            "id": "p_dpo",
            "title": "Direct Preference Optimization",
            "abstract": "We show DPO is stable and effective for alignment.",
            "content": "DPO is simpler than PPO.",
            "authors": ["Bob"],
            "year": 2024,
            "rating": 9.5,
        },
    ]
    kb.ingest_data(sample_papers)

    llm = FakeLLM()

    planner = PlannerAgent(llm)
    plan = planner.generate_plan("Compare RLHF and DPO for alignment", {"count": 2})
    assert plan.get("sections"), "Planner should return sections"

    researcher = ResearcherAgent(kb, llm)
    notes = researcher.execute_research(plan)
    assert notes and notes[0].get("evidence"), "Researcher should output evidence snippets"

    writer = WriterAgent(llm)
    report, ref_ctx = writer.write_report(plan, notes)
    assert "[R" in report and "]" in report, "Report should contain ref-style citations like [R1]"

    chunk_map = {}
    for n in notes:
        for e in (n.get("evidence") or []):
            if e.get("chunk_id") and e.get("text"):
                chunk_map[e["chunk_id"]] = e["text"]

    verifier = VerifierAgent(llm)
    verification = verifier.verify_report(
        report,
        {"chunks": chunk_map, "ref_map": (ref_ctx or {}).get("ref_map") or {}, "max_claims": 5},
    )
    assert verification["is_valid"] is True
