from src.data_engine.storage import KnowledgeBase


def test_kb_ingest_and_search_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("MUJICA_FAKE_EMBEDDINGS", "1")
    monkeypatch.setenv("MUJICA_FAKE_EMBEDDING_DIM", "64")

    kb = KnowledgeBase(db_path=str(tmp_path / "lancedb_kb"))
    kb.initialize_db()

    kb.ingest_data(
        [
            {
                "id": "p1",
                "title": "Deep Learning for Alignment",
                "abstract": "We explore RLHF and DPO for aligning LLMs.",
                "content": "Full text about alignment...",
                "authors": ["Alice", "Bob"],
                "year": 2024,
                "rating": 8.5,
            },
            {
                "id": "p2",
                "title": "Graph Neural Networks for Chemistry",
                "abstract": "Using GNNs to predict molecular properties.",
                "content": "Full text about GNNs...",
                "authors": ["Charlie"],
                "year": 2023,
                "rating": 7.0,
            },
        ]
    )

    df = kb.search_structured()
    assert len(df) == 2
    assert set(df["id"].tolist()) == {"p1", "p2"}

    hits = kb.search_semantic("alignment", limit=1)
    assert len(hits) == 1
    assert "id" in hits[0] and "best_chunk" in hits[0]


