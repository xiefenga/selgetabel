import subprocess
import sys
from pathlib import Path

REV = sys.argv[1]
PREV = sys.argv[2]

out_dir = Path("migrations_sql")
out_dir.mkdir(exist_ok=True)

upgrade_sql = out_dir / f"{REV}_upgrade.sql"
downgrade_sql = out_dir / f"{REV}_downgrade.sql"

subprocess.run(
    ["alembic", "upgrade", f"{PREV}:{REV}", "--sql"],
    stdout=open(upgrade_sql, "w"),
    check=True,
)

subprocess.run(
    ["alembic", "downgrade", f"{REV}:{PREV}", "--sql"],
    stdout=open(downgrade_sql, "w"),
    check=True,
)

print(f"✅ SQL 导出完成：\n- {upgrade_sql}\n- {downgrade_sql}")
