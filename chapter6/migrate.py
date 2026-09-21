# Listing 6.5 -- migrate.py: schema changes as versioned, ordered, recorded
# steps. Twenty lines, and the whole idea: the schema_version table
# remembers what has been applied, so migration is idempotent per step
# and every environment converges on the same schema by the same path.
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "encore.db")
db.execute("CREATE TABLE IF NOT EXISTS schema_version "
           "(version INTEGER PRIMARY KEY, "
           " applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
applied = {v for (v,) in db.execute("SELECT version FROM schema_version")}

for path in sorted(Path("migrations").glob("*.sql")):
    version = int(path.name.split("_")[0])
    if version in applied:
        print(f"  {path.name}: already applied, skipping")
        continue
    db.executescript(path.read_text())
    db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    db.commit()
    print(f"  {path.name}: applied")
