import sqlite3

#Ce fichier python crée deux fichier database, un user location et un task completed.
#Dedans un tableau est crée en SQLite, user location enregistre la localisation tapé par l'utilisateur, et task completed ajoute une ligne à chaque fois un utilisateur marque une tâche comme "complété".
class UserLocation:
    def __init__(self, db_name='users_location.db'):
        self.db_name = db_name
        self.create_table()

    def create_table(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_locations (
        username TEXT NOT NULL,
        user_id INTEGER PRIMARY KEY,
        location TEXT NOT NULL
        )
        ''')
        conn.commit()
        conn.close()

    def set_user_location(self, username:str, user_id: int, location: str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO user_locations (username, user_id, location) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET location=excluded.location''', (username, user_id, location))
        conn.commit()
        conn.close()

    def get_user_location(self, user_id: int) -> str:
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT location FROM user_locations WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

class TaskCompleted:
    def __init__(self, db_name='tasks_completed.db'):
        self.db_name = db_name
        self.create_table()
    
    def create_table(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.execute('''
        CREATE TABLE IF NOT EXISTS task_completed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        task TEXT NOT NULL,
        time TEXT NOT NULL
        )''')
        conn.commit()
        conn.close()
    
    def set_info(self, user_id:int, username: str, task: str, time: str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO task_completed (user_id, username, task, time) VALUES (?, ?, ?, ?)''', (user_id, username, task, time))
        conn.commit()
        conn.close()