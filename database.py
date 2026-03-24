import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DATABASE', 'beatbrain')
    )
    return conn


def init_db():
    try:
        # need to connect without db first to create it
        conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', '')
        )
        cursor = conn.cursor()

        db_name = os.getenv('MYSQL_DATABASE', 'beatbrain')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")

        # create history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                song_name VARCHAR(255) NOT NULL,
                artist VARCHAR(255),
                album VARCHAR(255),
                mood VARCHAR(100),
                identified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("database ready!")

    except Exception as e:
        print(f"db init error: {e}")
        print("is mysql running?")


def save_to_history(song_name, artist, album, mood=None):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO history (song_name, artist, album, mood) VALUES (%s, %s, %s, %s)",
            (song_name, artist, album, mood)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"couldn't save to history: {e}")


def get_history():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM history ORDER BY identified_at DESC LIMIT 50")
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # datetime objects cant be sent as json so convert to string
        for row in results:
            if row.get('identified_at'):
                row['identified_at'] = str(row['identified_at'])

        return results
    except Exception as e:
        print(f"error getting history: {e}")
        return []


if __name__ == "__main__":
    init_db()
