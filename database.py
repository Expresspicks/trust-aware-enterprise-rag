import mysql.connector
from config import DB_CONFIG


def get_connection():
    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )


def execute_query(query, params=None):
    try:
        query_start = query.strip().lower()

        allowed_starts = ["select", "show", "describe"]

        if not any(query_start.startswith(word) for word in allowed_starts):
            return {
                "error": "Blocked unsafe SQL operation. Only SELECT, SHOW, and DESCRIBE queries are allowed."
            }

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        result = cursor.fetchall()

        cursor.close()
        conn.close()

        return result

    except Exception as e:
        return {"error": str(e)}
