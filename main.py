"""Surface حديثة — entry point."""
import io
import logging
import os
import base64

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for, flash
from flask_login import LoginManager, current_user, login_required
from sqlalchemy import text
from werkzeug.utils import secure_filename

from auth import auth_bp
from models import (
    CartItem, MenuItem, Order, OrderItem, Post, Restaurant,
    ROLE_ADMIN, ROLE_DELIVERY, ROLE_MERCHANT, ROLE_TECHNICIAN,
    RESTAURANT_CATEGORIES, SHOP_CATEGORIES, User, Wallet, db,
    DELIVERY_COMMISSION, MERCHANT_COMMISSION, MERCHANT_SALES_UNIT,
)

PRIMARY_ADMIN_PHONE = "07822856782"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("surface-haditha")


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///surface.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "سجّل دخول حتى تكدر توصل لهالصفحة"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(auth_bp)

    # ── Image upload & compress ───────────────────────────────────────────────
    @app.route("/upload", methods=["POST"])
    @login_required
    def upload_image():
        if "file" not in request.files:
            return jsonify({"error": "لا يوجد ملف"}), 400
        f = request.files["file"]
        if not f or not _allowed(f.filename):
            return jsonify({"error": "نوع الملف غير مدعوم"}), 400
        try:
            from PIL import Image
            img = Image.open(f.stream)
            img = img.convert("RGB")
            # Resize if larger than 1200px
            max_dim = 1200
            if img.width > max_dim or img.height > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75, optimize=True)
            buf.seek(0)
            fname = secure_filename(f.filename)
            fname = f"{current_user.id}_{int(__import__('time').time())}_{fname}"
            if not fname.lower().endswith((".jpg", ".jpeg")):
                fname = fname.rsplit(".", 1)[0] + ".jpg"
            save_path = os.path.join(UPLOAD_FOLDER, fname)
            with open(save_path, "wb") as out:
                out.write(buf.read())
            url = url_for("static", filename=f"uploads/{fname}")
            return jsonify({"url": url})
        except Exception as exc:
            logger.error("Image upload error: %s", exc)
            return jsonify({"error": "خطأ في معالجة الصورة"}), 500

    # ── Public pages ─────────────────────────────────────────────────────────
    @app.route("/")
    def home():
        latest_posts = (Post.query.filter_by(approved=True)
                        .order_by(Post.created_at.desc()).limit(6).all())
        open_restaurants = (Restaurant.query.filter_by(approved=True, is_open=True)
                            .order_by(Restaurant.created_at.desc()).limit(4).all())
        return render_template("index.html", latest_posts=latest_posts,
                               open_restaurants=open_restaurants)

    @app.route("/technicians")
    def technicians():
        techs = (User.query.filter_by(role=ROLE_TECHNICIAN)
                 .order_by(User.created_at.desc()).all())
        return render_template("technicians.html", techs=techs)

    @app.route("/shop")
    def shop():
        return render_template("shop.html", categories=SHOP_CATEGORIES)

    @app.route("/shop/<path:category>")
    def shop_category(category):
        if category not in SHOP_CATEGORIES:
            abort(404)
        products = (Post.query.filter_by(section="shop", category=category, approved=True)
                    .order_by(Post.created_at.desc()).all())
        return render_template("shop_category.html", category=category, products=products)

    @app.route("/delivery")
    def delivery():
        agents = (User.query.filter_by(role=ROLE_DELIVERY)
                  .order_by(User.created_at.desc()).all())
        return render_template("delivery.html", agents=agents)

    # ── Restaurants ───────────────────────────────────────────────────────────
    @app.route("/restaurants")
    def restaurants():
        rlist = (Restaurant.query.filter_by(approved=True)
                 .order_by(Restaurant.created_at.desc()).all())
        return render_template("restaurants.html", restaurants=rlist)

    @app.route("/restaurants/<int:rid>")
    def restaurant_detail(rid):
        r = Restaurant.query.get_or_404(rid)
        if not r.approved and not (current_user.is_authenticated and
                                   (current_user.is_admin or current_user.id == r.owner_id)):
            abort(404)
        menu = {}
        for item in r.menu_items:
            if item.is_available:
                cat = item.category or "أخرى"
                menu.setdefault(cat, []).append(item)
        return render_template("restaurant_detail.html", r=r, menu=menu)

    # ── Cart ──────────────────────────────────────────────────────────────────
    @app.route("/cart")
    @login_required
    def cart():
        items = CartItem.query.filter_by(user_id=current_user.id).all()
        total = sum(i.subtotal for i in items)
        return render_template("cart.html", items=items, total=total)

    @app.route("/cart/add", methods=["POST"])
    @login_required
    def cart_add():
        menu_item_id = request.form.get("menu_item_id", type=int)
        post_id      = request.form.get("post_id", type=int)
        qty          = max(1, request.form.get("qty", 1, type=int))

        if menu_item_id:
            mi = MenuItem.query.get_or_404(menu_item_id)
            existing = CartItem.query.filter_by(
                user_id=current_user.id, menu_item_id=menu_item_id).first()
            if existing:
                existing.qty += qty
            else:
                db.session.add(CartItem(
                    user_id=current_user.id, menu_item_id=mi.id,
                    restaurant_id=mi.restaurant_id,
                    name=mi.name, price=mi.price, qty=qty))
            flash("تمت الإضافة للسلة", "success")
        elif post_id:
            p = Post.query.get_or_404(post_id)
            existing = CartItem.query.filter_by(
                user_id=current_user.id, post_id=post_id).first()
            if existing:
                existing.qty += qty
            else:
                db.session.add(CartItem(
                    user_id=current_user.id, post_id=p.id,
                    name=p.title, price=p.price, qty=qty))
            flash("تمت الإضافة للسلة", "success")

        db.session.commit()
        return redirect(request.referrer or url_for("cart"))

    @app.route("/cart/remove/<int:item_id>", methods=["POST"])
    @login_required
    def cart_remove(item_id):
        item = CartItem.query.get_or_404(item_id)
        if item.user_id == current_user.id:
            db.session.delete(item)
            db.session.commit()
        return redirect(url_for("cart"))

    @app.route("/cart/checkout", methods=["POST"])
    @login_required
    def cart_checkout():
        items = CartItem.query.filter_by(user_id=current_user.id).all()
        if not items:
            flash("السلة فارغة", "error")
            return redirect(url_for("cart"))

        address = (request.form.get("address") or "").strip()
        note    = (request.form.get("note") or "").strip()
        total   = sum(i.subtotal for i in items)

        # Group by restaurant (first restaurant_id found)
        rest_id = next((i.restaurant_id for i in items if i.restaurant_id), None)

        order = Order(
            customer_id=current_user.id,
            restaurant_id=rest_id,
            total=total,
            address=address,
            note=note,
        )
        db.session.add(order)
        db.session.flush()

        for ci in items:
            db.session.add(OrderItem(
                order_id=order.id,
                item_name=ci.name,
                price=ci.price,
                qty=ci.qty,
            ))
            db.session.delete(ci)

        # Merchant commission: 500 per 20,000 sales
        if rest_id:
            rest = Restaurant.query.get(rest_id)
            if rest:
                merchant = User.query.get(rest.owner_id)
                if merchant:
                    merchant.total_sales += total
                    units = int(merchant.total_sales // MERCHANT_SALES_UNIT) - \
                            int(merchant.commission_paid // MERCHANT_COMMISSION)
                    if units > 0:
                        owed = units * MERCHANT_COMMISSION
                        merchant.commission_paid += owed
                        w = merchant.get_or_create_wallet()
                        w.credit(owed, "sale_commission",
                                 f"عمولة مبيعات — طلب #{order.id}")

        db.session.commit()
        flash(f"تم إرسال طلبك! رقم الطلب: #{order.id}", "success")
        return redirect(url_for("home"))

    # ── Health ────────────────────────────────────────────────────────────────
    @app.route("/health")
    def health():
        return {"status": "ok", "service": "Surface Haditha"}

    @app.route("/ping")
    def ping():
        return {"alive": True}

    with app.app_context():
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        db.create_all()
        _migrate_schema()
        _bootstrap_admin(app)

    return app


# ── Schema migration ──────────────────────────────────────────────────────────
def _migrate_schema() -> None:
    with db.engine.connect() as conn:
        # users
        user_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(users)"))}
        for col, ddl in {
            "craft": "TEXT", "bio": "TEXT", "experience_years": "INTEGER",
            "photos_csv": "TEXT", "vehicle": "TEXT", "area": "TEXT",
            "subscription_plan": "TEXT DEFAULT 'free'",
            "total_sales": "REAL DEFAULT 0",
            "commission_paid": "REAL DEFAULT 0",
            "total_deliveries": "INTEGER DEFAULT 0",
        }.items():
            if col not in user_cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
                logger.info("DB: added users.%s", col)

        # posts
        post_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(posts)"))}
        for col, ddl in {
            "section": "TEXT DEFAULT 'shop'",
            "image_url": "TEXT",
            "approved": "INTEGER DEFAULT 0",
        }.items():
            if col not in post_cols:
                conn.execute(text(f"ALTER TABLE posts ADD COLUMN {col} {ddl}"))
                logger.info("DB: added posts.%s", col)

        conn.commit()


# ── Bootstrap admin ───────────────────────────────────────────────────────────
def _bootstrap_admin(app: Flask) -> None:
    u = User.query.filter_by(phone=PRIMARY_ADMIN_PHONE).first()
    if u and u.role != ROLE_ADMIN:
        u.role = ROLE_ADMIN
        db.session.commit()
        app.logger.info("Promoted %s to admin.", u.name)
    elif u:
        # Auto-approve admin posts
        Post.query.filter_by(merchant_id=u.id, approved=False).update({"approved": True})
        db.session.commit()
    else:
        app.logger.info("Admin phone %s not registered yet.", PRIMARY_ADMIN_PHONE)


app = create_app()

if __name__ == "__main__":
  
    import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

