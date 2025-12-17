from src.data_engine.storage import KnowledgeBase
from src.data_engine.loader import DataLoader
import os

def test_data_layer():
    print("Testing Data Layer...")
    
    # 1. Create Sample Data
    sample_papers = [
        {
            "id": "p1",
            "title": "Deep Learning for Alignment",
            "abstract": "We explore RLHF and DPO for aligning LLMs.",
            "content": "Full text about alignment...",
            "authors": ["Alice", "Bob"],
            "year": 2024,
            "rating": 8.5
        },
        {
            "id": "p2",
            "title": "Graph Neural Networks for Chemistry",
            "abstract": "Using GNNs to predict molecular properties.",
            "content": "Full text about GNNs...",
            "authors": ["Charlie"],
            "year": 2023,
            "rating": 7.0
        }
    ]
    
    loader = DataLoader("data/raw/test_samples.json")
    loader.save_local_data(sample_papers)
    
    # 2. Ingest Data
    # Use a temp db path for testing
    kb = KnowledgeBase(db_path="data/lancedb_test")
    kb.initialize_db()
    kb.ingest_data(sample_papers)
    
    # 3. Test Semantic Search
    results = kb.search_semantic("alignment", limit=1)
    print("\nSearch Results for 'alignment':")
    for r in results:
        print(f"- {r['title']} (Score: {r.get('_distance', 'N/A')})") # LanceDB returns distance usually
        
    if len(results) > 0 and "Alignment" in results[0]['title']:
        print("\nSUCCESS: Semantic search working.")
    else:
        print("\nFAILURE: Semantic search did not return expected result.")

    # Cleanup
    # import shutil
    # shutil.rmtree("data/lancedb_test")

if __name__ == "__main__":
    test_data_layer()
