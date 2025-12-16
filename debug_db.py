
import os
import sqlite3
import lancedb

def check_db():
    print(f"CWD: {os.getcwd()}")
    
    db_path = os.path.join("data", "lancedb")
    meta_path = os.path.join(db_path, "mujica_meta.db")
    
    print(f"Meta DB Path: {os.path.abspath(meta_path)}")
    print(f"Exists: {os.path.exists(meta_path)}")
    
    if os.path.exists(meta_path):
        try:
            conn = sqlite3.connect(meta_path)
            cursor = conn.cursor()
            
            # List tables
            tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            print(f"Tables: {tables}")
            
            # Count
            if any(t[0] == 'papers' for t in tables):
                c = cursor.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
                print(f"Papers count: {c}")
            
            if any(t[0] == 'reviews' for t in tables):
                c = cursor.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
                print(f"Reviews count: {c}")
                
            conn.close()
        except Exception as e:
            print(f"SQLite Error: {e}")

    # Check LanceDB
    print(f"LanceDB Path: {os.path.abspath(db_path)}")
    try:
        ldb = lancedb.connect(db_path)
        print(f"LanceDB Tables: {ldb.table_names()}")
        if "chunks" in ldb.table_names():
            print(f"Chunks count: {ldb.open_table('chunks').count_rows()}")
    except Exception as e:
        print(f"LanceDB Error: {e}")

if __name__ == "__main__":
    check_db()
