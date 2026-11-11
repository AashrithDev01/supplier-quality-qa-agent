import sqlite3

conn = sqlite3.connect('data/quality.db')
c = conn.cursor()

# Check currency in defects
c.execute("SELECT DISTINCT cost_currency FROM defects")
currencies = c.fetchall()
print(f"Currencies in defects: {[cu[0] for cu in currencies]}")

# Check severity distribution
c.execute("SELECT severity, COUNT(*) FROM defects GROUP BY severity ORDER BY severity")
sev = c.fetchall()
print(f"Severity distribution: {sev}")

# Check defect types
c.execute("SELECT defect_type, COUNT(*) FROM defects GROUP BY defect_type ORDER BY COUNT(*) DESC")
dtypes = c.fetchall()
print(f"Defect types: {dtypes}")

# Check date ranges
c.execute("SELECT MIN(received_date), MAX(received_date) FROM lots")
dates = c.fetchone()
print(f"Lot received_date range: {dates}")

c.execute("SELECT MIN(detected_at), MAX(detected_at) FROM defects")
dates = c.fetchone()
print(f"Defect detected_at range: {dates}")

# Check date format inconsistencies
c.execute("SELECT lot_id, received_date FROM lots LIMIT 20")
rows = c.fetchall()
print(f"\nDate format samples from lots:")
for r in rows:
    print(f"  {r[0]}: '{r[1]}'")

# Check suppliers
c.execute("SELECT * FROM suppliers")
suppliers = c.fetchall()
print(f"\nAll suppliers ({len(suppliers)}):")
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

# LOT-0042
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

# Customer return - check if any column references it
c.execute("PRAGMA table_info(defects)")
defect_cols = [col[1] for col in c.fetchall()]
print(f"\nDefect columns: {defect_cols}")

c.execute("PRAGMA table_info(lots)")
lot_cols = [col[1] for col in c.fetchall()]
print(f"Lot columns: {lot_cols}")

# Deviation analysis (for dimensional defects)
c.execute("SELECT deviation_value, deviation_unit FROM defects WHERE defect_type='dimensional' AND deviation_value IS NOT NULL")
devs = c.fetchall()
print(f"\nDimensional deviations ({len(devs)} records):")
units = set([d[1] for d in devs])
print(f"  Units: {units}")
values = [d[0] for d in devs]
if values:
    print(f"  Min: {min(values)}, Max: {max(values)}, Avg: {sum(values)/len(values):.4f}")

# Check for mixed units
c.execute("SELECT DISTINCT deviation_unit FROM defects WHERE deviation_value IS NOT NULL")
all_units = c.fetchall()
print(f"  All deviation units with values: {[u[0] for u in all_units]}")

# Check lots blocking criteria per PROC-02
# Blocking: severity 4 or 5, OR defect rate > 2%
c.execute("""
SELECT l.lot_id, l.supplier_id, l.qty_received,
       MAX(d.severity) as max_severity,
       SUM(d.qty_defective) as total_defective,
       CAST(SUM(d.qty_defective) AS REAL) / l.qty_received * 100 as defect_rate_pct
FROM lots l
JOIN defects d ON l.lot_id = d.lot_id
GROUP BY l.lot_id
HAVING max_severity >= 4 OR defect_rate_pct > 2.0
""")
blocked = c.fetchall()
print(f"\nLots meeting blocking criteria: {len(blocked)}")
for b in blocked[:10]:
    print(f"  {b}")

# Check for 'reception_date' vs 'received_date' column naming
# The README says 'suppliers, lots, defects'  
# Question 1: "How many lots were received in 2025?" 
# Need to parse dates properly

# Count lots by year using various date parsing
c.execute("SELECT received_date FROM lots")
all_dates = c.fetchall()
from_2025 = 0
date_formats_seen = set()
for d in all_dates:
    dt = d[0]
    if '2025' in dt:
        from_2025 += 1
    # Check format
    if '/' in dt:
        date_formats_seen.add('DD/MM/YYYY')
    elif '-' in dt:
        date_formats_seen.add('YYYY-MM-DD')

print(f"\nDate formats in lots.received_date: {date_formats_seen}")
print(f"Lots containing '2025' in date: {from_2025}")

# Kraftteile GmbH Q2 2025 cost
c.execute("""
SELECT d.*, l.supplier_id, s.name
FROM defects d
JOIN lots l ON d.lot_id = l.lot_id
JOIN suppliers s ON l.supplier_id = s.supplier_id
WHERE s.name = 'Kraftteile GmbH'
""")
kt_defects = c.fetchall()
print(f"\nKraftteile GmbH total defects: {len(kt_defects)}")
for kd in kt_defects[:5]:
    print(f"  {kd}")

conn.close()
