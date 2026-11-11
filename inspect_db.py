import sqlite3

conn = sqlite3.connect('data/quality.db')
c = conn.cursor()

# List all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables:", [t[0] for t in tables])

for t in tables:
    tname = t[0]
    print(f"\n{'='*60}")
    print(f"TABLE: {tname}")
    print(f"{'='*60}")
    
    # Schema
    c.execute(f"PRAGMA table_info({tname})")
    cols = c.fetchall()
    print("Columns:")
    for col in cols:
        print(f"  {col[1]:25s} {col[2]:15s} nullable={not col[3]}  default={col[4]}  pk={col[5]}")
    
    # Row count
    c.execute(f"SELECT COUNT(*) FROM {tname}")
    print(f"Row count: {c.fetchone()[0]}")
    
    # Sample rows
    c.execute(f"SELECT * FROM {tname} LIMIT 5")
    rows = c.fetchall()
    col_names = [col[1] for col in cols]
    print(f"Sample rows ({len(rows)}):")
    print(f"  {col_names}")
    for r in rows:
        print(f"  {list(r)}")

# Check for data quality issues
print(f"\n{'='*60}")
print("DATA QUALITY CHECKS")
print(f"{'='*60}")

# Check for NULL values in key columns
for t in tables:
    tname = t[0]
    c.execute(f"PRAGMA table_info({tname})")
    cols = c.fetchall()
    for col in cols:
        cname = col[1]
        c.execute(f"SELECT COUNT(*) FROM {tname} WHERE {cname} IS NULL")
        null_count = c.fetchone()[0]
        if null_count > 0:
            print(f"  {tname}.{cname}: {null_count} NULL values")

# Check currency in defects
c.execute("SELECT DISTINCT currency FROM defects")
currencies = c.fetchall()
print(f"\nCurrencies in defects: {[cu[0] for cu in currencies]}")

# Check severity distribution
c.execute("SELECT severity, COUNT(*) FROM defects GROUP BY severity ORDER BY severity")
sev = c.fetchall()
print(f"Severity distribution: {sev}")

# Check defect types
c.execute("SELECT defect_type, COUNT(*) FROM defects GROUP BY defect_type ORDER BY COUNT(*) DESC")
dtypes = c.fetchall()
print(f"Defect types: {dtypes}")

# Check date ranges
c.execute("SELECT MIN(reception_date), MAX(reception_date) FROM lots")
dates = c.fetchone()
print(f"Lot date range: {dates}")

c.execute("SELECT MIN(detection_date), MAX(detection_date) FROM defects")
dates = c.fetchone()
print(f"Defect detection date range: {dates}")

# Check suppliers
c.execute("SELECT * FROM suppliers")
suppliers = c.fetchall()
print(f"\nAll suppliers:")
for s in suppliers:
    print(f"  {s}")

# Check for orphan records
c.execute("""SELECT COUNT(*) FROM lots l 
             LEFT JOIN suppliers s ON l.supplier_id = s.supplier_id 
             WHERE s.supplier_id IS NULL""")
print(f"\nOrphan lots (no matching supplier): {c.fetchone()[0]}")

c.execute("""SELECT COUNT(*) FROM defects d 
             LEFT JOIN lots l ON d.lot_id = l.lot_id 
             WHERE l.lot_id IS NULL""")
print(f"Orphan defects (no matching lot): {c.fetchone()[0]}")

# Check for the specific lot LOT-0042
c.execute("SELECT * FROM lots WHERE lot_id = 'LOT-0042'")
lot42 = c.fetchall()
print(f"\nLOT-0042 exists: {len(lot42) > 0}")
if lot42:
    print(f"  {lot42}")

c.execute("SELECT * FROM defects WHERE lot_id = 'LOT-0042'")
def42 = c.fetchall()
print(f"Defects for LOT-0042: {len(def42)}")
for d in def42:
    print(f"  {d}")

# Check for 'customer_return' or similar columns
c.execute("PRAGMA table_info(defects)")
defect_cols = [col[1] for col in c.fetchall()]
print(f"\nDefect columns: {defect_cols}")

c.execute("PRAGMA table_info(lots)")
lot_cols = [col[1] for col in c.fetchall()]
print(f"Lot columns: {lot_cols}")

conn.close()
