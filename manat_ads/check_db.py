import sqlite3

def check():
    conn = sqlite3.connect('manat_ads.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    for table in tables:
        t_name = table[0]
        cursor.execute(f"PRAGMA table_info({t_name});")
        print(f"Table {t_name} schema:", cursor.fetchall())

if __name__ == '__main__':
    check()
