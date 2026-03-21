from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_key_change_in_prod")
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "crm.db")


# ── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id         INTEGER  PRIMARY KEY AUTOINCREMENT,
                name       TEXT     NOT NULL,
                email      TEXT     NOT NULL UNIQUE,
                phone      TEXT     DEFAULT '',
                status     TEXT     NOT NULL DEFAULT 'new'
                               CHECK(status IN ('new','contacted','converted')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def row_to_dict(row):
    return dict(row)


# ── API ROUTES ────────────────────────────────────────────────────────────────

@app.route("/api/customers", methods=["GET"])
def list_customers():
    status = request.args.get("status", "").strip()
    q      = request.args.get("q", "").strip()

    sql, params = "SELECT * FROM customers WHERE 1=1", []

    if status and status != "all":
        sql += " AND status = ?"
        params.append(status)

    if q:
        sql += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]

    sql += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/customers", methods=["POST"])
def create_customer():
    data   = request.get_json(force=True)
    name   = (data.get("name")   or "").strip()
    email  = (data.get("email")  or "").strip()
    phone  = (data.get("phone")  or "").strip()
    status = (data.get("status") or "new").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required"}), 400
    if status not in ("new", "contacted", "converted"):
        status = "new"

    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO customers (name, email, phone, status) VALUES (?,?,?,?)",
                (name, email, phone, status),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return jsonify(row_to_dict(row)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409


@app.route("/api/customers/<int:cid>", methods=["GET"])
def get_customer(cid):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (cid,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/customers/<int:cid>", methods=["PUT"])
def update_customer(cid):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (cid,)
        ).fetchone()
        if not existing:
            return jsonify({"error": "Not found"}), 404

        data   = request.get_json(force=True)
        name   = (data.get("name")   or existing["name"]).strip()
        email  = (data.get("email")  or existing["email"]).strip()
        phone  = data.get("phone",   existing["phone"])
        status = (data.get("status") or existing["status"]).strip()

        if not name:
            return jsonify({"error": "Name is required"}), 400
        if "@" not in email:
            return jsonify({"error": "Valid email is required"}), 400
        if status not in ("new", "contacted", "converted"):
            return jsonify({"error": "Invalid status"}), 400

        try:
            conn.execute(
                "UPDATE customers SET name=?, email=?, phone=?, status=? WHERE id=?",
                (name, email, phone, status, cid),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?", (cid,)
            ).fetchone()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Email already exists"}), 409

    return jsonify(row_to_dict(row))


@app.route("/api/customers/<int:cid>", methods=["DELETE"])
def delete_customer(cid):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM customers WHERE id = ?", (cid,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM customers WHERE id = ?", (cid,))
        conn.commit()
    return jsonify({"deleted": cid})


@app.route("/api/stats", methods=["GET"])
def stats():
    with get_db() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        new_c     = conn.execute("SELECT COUNT(*) FROM customers WHERE status='new'").fetchone()[0]
        contacted = conn.execute("SELECT COUNT(*) FROM customers WHERE status='contacted'").fetchone()[0]
        converted = conn.execute("SELECT COUNT(*) FROM customers WHERE status='converted'").fetchone()[0]
    return jsonify({
        "total":     total,
        "new":       new_c,
        "contacted": contacted,
        "converted": converted,
    })


# ── FRONTEND ──────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)