import sqlite3

def run():
    conn = sqlite3.connect('manat_ads.db')
    cursor = conn.cursor()
    
    # 1. Add welcome_bonus_claimed column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN welcome_bonus_claimed BOOLEAN DEFAULT 0;")
        print("Added welcome_bonus_claimed column.")
    except Exception as e:
        print("Column welcome_bonus_claimed might already exist:", e)

    # 2. Fix Unit Collision (The 100% Bug)
    cursor.execute("SELECT id, balance_mc, total_earned_mc FROM users WHERE balance_mc > 50;")
    users = cursor.fetchall()
    for u in users:
        new_balance = round(u[1] / 140000.0, 6)
        new_total = round(u[2] / 140000.0, 6)
        cursor.execute("UPDATE users SET balance_mc = ?, total_earned_mc = ? WHERE id = ?", (new_balance, new_total, u[0]))
        print(f"Fixed unit collision for user {u[0]}: {u[1]} -> {new_balance}")

    # 3. Welcome Bonus Leak Fix
    # Legacy users (created before 12 hours ago) who were updated recently
    cursor.execute("""
        UPDATE users 
        SET balance_mc = balance_mc - 4.0 
        WHERE created_at < datetime('now', '-12 hours') 
        AND updated_at > datetime('now', '-12 hours')
        AND balance_mc >= 4.0;
    """)
    print(f"Subtracted 4.0 from legacy users erroneously granted the bonus. Rows affected: {cursor.rowcount}")

    # 4. Freeze Malicious Withdrawals
    # As there is no Withdrawals table (it's handled via Telegram messages to admins),
    # we log this so the user knows.
    print("NOTE: Withdrawal requests are sent directly to Admins via Telegram.")
    print("There is no Withdrawals table to query. Admins must manually ignore malicious Telegram requests from the last 6 hours.")

    conn.commit()
    conn.close()
    print("Emergency patch completed successfully.")

if __name__ == '__main__':
    run()
