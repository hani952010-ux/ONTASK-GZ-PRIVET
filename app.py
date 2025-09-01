\
    import os, sqlite3
    from datetime import datetime
    from flask import Flask, render_template, request, redirect, url_for, flash, session, g
    from flask_babel import Babel, gettext as _
    from dotenv import load_dotenv

    load_dotenv()

    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(APP_DIR, "data.sqlite")

    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
    babel = Babel(app)

    @babel.localeselector
    def get_locale():
        return request.args.get("lang") or "ar"

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS shipments (
            tracking TEXT PRIMARY KEY,
            customer TEXT,
            carrier TEXT,
            origin TEXT,
            destination TEXT,
            status TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking TEXT,
            status TEXT,
            location TEXT,
            note TEXT,
            ts TEXT,
            FOREIGN KEY(tracking) REFERENCES shipments(tracking)
        );
        """)
        cur = db.execute("SELECT COUNT(*) AS c FROM shipments")
        if cur.fetchone()["c"] == 0:
            seed_demo(db)
        db.commit()

    def seed_demo(db):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
        demo = [
            ("TRK123456789", "Belal Arfi", "SF Express", "Guangzhou, CN", "Dubai, AE", "In Transit", now),
            ("CN2025-0001", "Ismael Hadjaj", "DHL", "Shenzhen, CN", "Paris, FR", "Label Created", now)
        ]
        db.executemany("""INSERT INTO shipments
            (tracking, customer, carrier, origin, destination, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", demo)

        events = [
            ("TRK123456789", "Picked Up", "Guangzhou Hub", "Shipment received", "2025-08-25 09:10:00Z"),
            ("TRK123456789", "In Transit", "Shenzhen Sorting", "Departed facility", "2025-08-26 14:40:00Z"),
            ("TRK123456789", "In Transit", "Hong Kong", "Flight departed", "2025-08-27 21:10:00Z"),
            ("CN2025-0001", "Label Created", "Shenzhen", "Awaiting pickup", "2025-08-30 08:00:00Z"),
        ]
        db.executemany("""INSERT INTO events (tracking, status, location, note, ts)
                          VALUES (?, ?, ?, ?, ?)""", events)

    def is_logged_in():
        return session.get("is_admin") is True

    def require_admin():
        if not is_logged_in():
            flash(_("الرجاء إدخال كلمة المرور للدخول للوحة الإدارة") + " / " + _("Please enter the admin password"))
            return redirect(url_for("admin_login"))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            password = request.form.get("password", "")
            if password == os.environ.get("ADMIN_PASSWORD", "changeme"):
                session["is_admin"] = True
                flash(_("تم تسجيل الدخول") + " / " + _("Logged in"))
                return redirect(url_for("admin"))
            flash(_("كلمة المرور غير صحيحة") + " / " + _("Incorrect password"))
        return render_template("admin.html", view="login")

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        flash(_("تم تسجيل الخروج") + " / " + _("Logged out"))
        return redirect(url_for("index"))

    @app.route("/")
    def index():
        init_db()
        q = request.args.get("q", "").strip()
        shipment = None
        events = []
        if q:
            db = get_db()
            shipment = db.execute("SELECT * FROM shipments WHERE tracking = ?", (q,)).fetchone()
            if shipment:
                events = db.execute("SELECT * FROM events WHERE tracking=? ORDER BY ts ASC", (q,)).fetchall()
            else:
                flash(_("لم يتم العثور على الشحنة") + " / " + _("Shipment not found"))
        return render_template("index.html", shipment=shipment, events=events, q=q)

    @app.route("/track/<tracking>")
    def track(tracking):
        init_db()
        db = get_db()
        shipment = db.execute("SELECT * FROM shipments WHERE tracking = ?", (tracking,)).fetchone()
        if not shipment:
            flash(_("لم يتم العثور على الشحنة") + " / " + _("Shipment not found"))
            return redirect(url_for("index"))
        events = db.execute("SELECT * FROM events WHERE tracking=? ORDER BY ts ASC", (tracking,)).fetchall()
        return render_template("track.html", shipment=shipment, events=events)

    @app.route("/admin", methods=["GET", "POST"])
    def admin():
        init_db()
        if not is_logged_in():
            return require_admin()
        db = get_db()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "create_or_update":
                tracking = request.form["tracking"].strip()
                if not tracking:
                    flash(_("رقم التتبع مطلوب") + " / " + _("Tracking number is required"))
                    return redirect(url_for("admin"))
                data = {
                    "customer": request.form.get("customer", "").strip(),
                    "carrier": request.form.get("carrier", "").strip(),
                    "origin": request.form.get("origin", "").strip(),
                    "destination": request.form.get("destination", "").strip(),
                    "status": request.form.get("status", "").strip(),
                    "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
                }
                cur = db.execute("SELECT tracking FROM shipments WHERE tracking=?", (tracking,))
                if cur.fetchone():
                    db.execute("""UPDATE shipments SET customer=?, carrier=?,
                                  origin=?, destination=?, status=?, updated_at=?
                                  WHERE tracking=?""",
                               (data["customer"], data["carrier"], data["origin"], data["destination"], data["status"], data["updated_at"], tracking))
                    flash(_("تم تحديث الشحنة") + " / " + _("Shipment updated"))
                else:
                    db.execute("""INSERT INTO shipments (tracking, customer, carrier, origin, destination, status, updated_at)
                                  VALUES (?, ?, ?, ?, ?, ?, ?)""",
                               (tracking, data["customer"], data["carrier"], data["origin"], data["destination"], data["status"], data["updated_at"]))
                    flash(_("تم إنشاء الشحنة") + " / " + _("Shipment created"))
                db.commit()
            elif action == "add_event":
                tracking = request.form.get("tracking_e")
                status = request.form.get("status_e")
                location = request.form.get("location_e")
                note = request.form.get("note_e")
                ts = request.form.get("ts_e") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
                db.execute("""INSERT INTO events (tracking, status, location, note, ts)
                              VALUES (?, ?, ?, ?, ?)""", (tracking, status, location, note, ts))
                db.commit()
                flash(_("تمت إضافة الحدث") + " / " + _("Event added"))

        shipments = db.execute("SELECT * FROM shipments ORDER BY updated_at DESC").fetchall()
        return render_template("admin.html", view="panel", shipments=shipments)

    @app.route("/api/track/<tracking>")
    def api_track(tracking):
        init_db()
        db = get_db()
        s = db.execute("SELECT * FROM shipments WHERE tracking = ?", (tracking,)).fetchone()
        if not s:
            return {"ok": False, "error": "not_found"}, 404
        events = db.execute("SELECT * FROM events WHERE tracking=? ORDER BY ts ASC", (tracking,)).fetchall()
        return {"ok": True, "shipment": dict(s), "events": [dict(e) for e in events]}

    if __name__ == "__main__":
        init_db()
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
