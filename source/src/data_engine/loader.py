import json
import os
from typing import List, Dict

class DataLoader:
    def __init__(self, data_path: str = "data/raw/sample_papers.json"):
        self.data_path = data_path

    def load_local_data(self) -> List[Dict]:
        """
        Loads papers from a local JSON file.
        """
        if not os.path.exists(self.data_path):
            print(f"File not found: {self.data_path}")
            return []
            
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"Error loading data: {e}")
            return []
            
    def save_local_data(self, data: List[Dict]):
        """
        Saves data to a local JSON file.
        """
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Saved {len(data)} papers to {self.data_path}")
