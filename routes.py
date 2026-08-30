from flask import Blueprint, render_template, request, redirect, session, url_for
from database import execute_query


def register_routes(app, agent):

    @app.route("/")
    def home():
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None

        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            query = """
            SELECT 
                u.user_id,
                u.username,
                u.password,
                u.role_id,
                u.region,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.username = %s AND u.password = %s
            """

            result = execute_query(query, (username, password))

            if result and not isinstance(result, dict):
                user = result[0]

                session["user_id"] = user["user_id"]
                session["username"] = user["username"]
                session["role_id"] = user["role_id"]
                session["role_name"] = user["role_name"]
                session["region"] = user["region"]

                return redirect(url_for("dashboard"))

            return render_template("login.html", error="Invalid username or password")

        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error = None

        if request.method == "POST":
            username = request.form.get("username").strip()
            password = request.form.get("password").strip()
            role_id = request.form.get("role_id")
            region = request.form.get("region").strip()

            check_query = "SELECT user_id FROM users WHERE username = %s"
            existing = execute_query(check_query, (username,))

            if existing:
                error = "Username already exists"
            else:
                insert_query = """
                INSERT INTO users (username, password, role_id, region)
                VALUES (%s, %s, %s, %s)
                """
                execute_query(insert_query, (username, password, role_id, region))
                return redirect(url_for("login"))

        return render_template("register.html", error=error)

    @app.route("/dashboard")
    def dashboard():
        if "user_id" not in session:
            return redirect(url_for("login"))

        return render_template(
            "dashboard.html", chat_history=session.get("chat_history", [])
        )

    @app.route("/clear_chat")
    def clear_chat():
        session.pop("chat_history", None)
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
