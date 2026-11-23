import sqlite3

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Set final_price = 63312.92 (the open of cycle 1795442700 / close of 1795442400)
cursor.execute("""
    UPDATE cycles
    SET final_price = 63312.92
    WHERE cycle_id = 1795442400
""")
conn.commit()
print("Updated final_price for cycle 1795442400 to 63312.92!")
conn.close()
