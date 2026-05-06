"""Authentication, profiles, dashboard, wallet, subscriptions, admin panel."""
from datetime import datetime, timedelta
from functools import wraps

from flask import (Blueprint, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from models import (
    CRAFTS, MenuItem, Order, Post, Restaurant,
    ROLE_ADMIN, ROLE_CUSTOMER, ROLE_DELIVERY,
    ROLE_MERCHANT, ROLE_TECHNICIAN,
    PLAN_FREE, PLAN_PLUS, PLAN_VIP, PLAN_LABELS, PLAN_PRICES,
    RESTAURANT_CATEGORIES, SHOP_CATEGORIES,
    Subscription, Transaction, User, VALID_ROLES, VEHICLES, Wallet, db,
    DELIVERY_COMMISSION,
)

auth_bp = Blueprint("auth", __name__)


# ── decorators ────────────────────────────────────────────────────────────────
def _role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("سجّل دخول أول", "error")
                return redirect(url_for("auth.login"))
            if current_user.role not in roles and not current_user.is_admin:
                flash("ما عندك صلاحية لهالصفحة", "error")
                return redirect(url_for("home"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("سجّل دخول أول", "error")
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            flash("هذي الصفحة للمدير بس", "error")
            return redirect(url_for("home"))
        return fn(*args, **kwargs)
    return wrapper


merchant_required  = _role_required(ROLE_MERCHANT)
technician_required = _role_required(ROLE_TECHNICIAN)
delivery_required  = _role_required(ROLE_DELIVERY)


# ── Signup / Login / Logout ───────────────────────────────────────────────────
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        name     = (request.form.get("name") or "").strip()
        phone    = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        role     = (request.form.get("role") or ROLE_CUSTOMER).strip()

        if not name or not phone or not password:
            flash("كل الحقول مطلوبة", "error")
            return render_template("signup.html", form=request.form)
        if len(password) < 6:
            flash("الباسورد لازم 6 أحرف على الأقل", "error")
            return render_template("signup.html", form=request.form)
        if role not in VALID_ROLES:
            role = ROLE_CUSTOMER
        if User.query.filter_by(phone=phone).first():
            flash("الرقم مسجّل من قبل، سجّل دخول", "error")
            return render_template("signup.html", form=request.form)

        user = User(name=name, phone=phone, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        # Create wallet
        db.session.add(Wallet(user_id=user.id, balance=0.0))
        db.session.commit()
        login_user(user)
        flash("أهلاً بيك بـ Surface حديثة", "success")
        if role in (ROLE_TECHNICIAN, ROLE_DELIVERY):
            return redirect(url_for("auth.edit_profile"))
        return redirect(url_for("home"))
    return render_template("signup.html", form={})


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        phone    = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(phone=phone).first()
        if not user or not user.check_password(password):
            flash("رقم أو باسورد غلط", "error")
            return render_template("login.html", form=request.form)
        login_user(user)
        return redirect(url_for("home"))
    return render_template("login.html", form={})


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("سلامتك، شفناك بخير", "success")
    return redirect(url_for("home"))


@auth_bp.route("/account")
@login_required
def account():
    return render_template("account.html")


# ── Profile edit ──────────────────────────────────────────────────────────────
@auth_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        current_user.bio  = (request.form.get("bio") or "").strip() or None
        current_user.area = (request.form.get("area") or "").strip() or None
        try:
            current_user.experience_years = int(request.form.get("experience_years") or 0)
        except ValueError:
            current_user.experience_years = 0
        current_user.photos_csv = (request.form.get("photos_csv") or "").strip() or None
        if current_user.is_technician:
            craft = (request.form.get("craft") or "").strip()
            current_user.craft = craft if craft in CRAFTS else None
        if current_user.is_delivery:
            vehicle = (request.form.get("vehicle") or "").strip()
            current_user.vehicle = vehicle if vehicle in VEHICLES else None
        db.session.commit()
        flash("تم تحديث ملفك", "success")
        return redirect(url_for("auth.account"))
    return render_template("edit_profile.html", crafts=CRAFTS, vehicles=VEHICLES, user=current_user)


# ── Wallet ────────────────────────────────────────────────────────────────────
@auth_bp.route("/wallet")
@login_required
def wallet():
    w = current_user.wallet
    txs = w.transactions[:30] if w else []
    return render_template("wallet.html", wallet=w, transactions=txs)


# ── Subscriptions ─────────────────────────────────────────────────────────────
@auth_bp.route("/subscription")
@login_required
def subscription():
    return render_template("subscription.html",
                           plans=PLAN_LABELS, prices=PLAN_PRICES,
                           current_plan=current_user.subscription_plan)


@auth_bp.route("/subscription/upgrade", methods=["POST"])
@login_required
def subscription_upgrade():
    plan = (request.form.get("plan") or "").strip()
    if plan not in (PLAN_PLUS, PLAN_VIP):
        flash("خطة غير صحيحة", "error")
        return redirect(url_for("auth.subscription"))

    price = PLAN_PRICES[plan]
    w = current_user.get_or_create_wallet()
    if w.balance < price:
        flash(f"رصيدك غير كافٍ، تحتاج {price:,.0f} د.ع", "error")
        return redirect(url_for("auth.subscription"))

    w.debit(price, "subscription", f"اشتراك {PLAN_LABELS[plan]}")
    current_user.subscription_plan = plan
    expires = datetime.utcnow() + timedelta(days=30)
    db.session.add(Subscription(
        user_id=current_user.id, plan=plan,
        price_paid=price, expires_at=expires
    ))
    db.session.commit()
    flash(f"تم الترقية لـ {PLAN_LABELS[plan]} حتى {expires.strftime('%Y/%m/%d')}", "success")
    return redirect(url_for("auth.account"))


# ── Merchant dashboard ────────────────────────────────────────────────────────
@auth_bp.route("/dashboard")
@merchant_required
def dashboard():
    posts = (Post.query.filter_by(merchant_id=current_user.id)
             .order_by(Post.created_at.desc()).all())
    my_restaurants = Restaurant.query.filter_by(owner_id=current_user.id).all()
    return render_template("dashboard.html", posts=posts, restaurants=my_restaurants)


@auth_bp.route("/dashboard/new", methods=["GET", "POST"])
@merchant_required
def new_post():
    if request.method == "POST":
        title       = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        category    = (request.form.get("category") or "كماليات").strip()
        image_url   = (request.form.get("image_url") or "").strip() or None
        try:
            price = float(request.form.get("price") or 0)
        except ValueError:
            price = 0.0
        if not title:
            flash("عنوان المنشور مطلوب", "error")
            return render_template("new_post.html", form=request.form, categories=SHOP_CATEGORIES)
        post = Post(
            title=title, description=description, price=price,
            category=category if category in SHOP_CATEGORIES else "كماليات",
            section="shop", image_url=image_url,
            merchant_id=current_user.id,
            approved=current_user.is_admin,  # admin posts auto-approved
        )
        db.session.add(post)
        db.session.commit()
        if current_user.is_admin:
            flash("تم نشر المنتج", "success")
        else:
            flash("تم إرسال المنشور — بانتظار موافقة المدير", "success")
        return redirect(url_for("auth.dashboard"))
    return render_template("new_post.html", form={}, categories=SHOP_CATEGORIES)


@auth_bp.route("/dashboard/edit/<int:post_id>", methods=["GET", "POST"])
@merchant_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.merchant_id != current_user.id and not current_user.is_admin:
        flash("ما تكدر تعدل هذا المنشور", "error")
        return redirect(url_for("auth.dashboard"))
    if request.method == "POST":
        post.title       = (request.form.get("title") or post.title).strip()
        post.description = (request.form.get("description") or "").strip()
        cat = (request.form.get("category") or post.category).strip()
        post.category  = cat if cat in SHOP_CATEGORIES else post.category
        post.image_url = (request.form.get("image_url") or "").strip() or None
        post.approved  = False if not current_user.is_admin else post.approved
        try:
            post.price = float(request.form.get("price") or 0)
        except ValueError:
            pass
        db.session.commit()
        flash("تم تحديث المنشور", "success")
        return redirect(url_for("auth.dashboard"))
    return render_template("new_post.html", form=post.__dict__, edit=True,
                           post=post, categories=SHOP_CATEGORIES)


@auth_bp.route("/dashboard/delete/<int:post_id>", methods=["POST"])
@merchant_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.merchant_id == current_user.id or current_user.is_admin:
        db.session.delete(post)
        db.session.commit()
        flash("تم حذف المنشور", "success")
    return redirect(url_for("auth.dashboard"))


# ── Restaurant management (merchant) ─────────────────────────────────────────
@auth_bp.route("/dashboard/restaurant/new", methods=["GET", "POST"])
@merchant_required
def new_restaurant():
    if request.method == "POST":
        name  = (request.form.get("name") or "").strip()
        if not name:
            flash("اسم المطعم مطلوب", "error")
            return render_template("new_restaurant.html", form=request.form)
        r = Restaurant(
            owner_id=current_user.id,
            name=name,
            description=(request.form.get("description") or "").strip() or None,
            logo_url=(request.form.get("logo_url") or "").strip() or None,
            phone=(request.form.get("phone") or "").strip() or None,
            area=(request.form.get("area") or "").strip() or None,
            approved=current_user.is_admin,
        )
        db.session.add(r)
        db.session.commit()
        flash("تم إضافة المطعم — بانتظار موافقة المدير" if not current_user.is_admin
              else "تم إضافة المطعم", "success")
        return redirect(url_for("auth.dashboard"))
    return render_template("new_restaurant.html", form={})


@auth_bp.route("/dashboard/restaurant/<int:rid>/menu/add", methods=["GET", "POST"])
@merchant_required
def add_menu_item(rid):
    r = Restaurant.query.get_or_404(rid)
    if r.owner_id != current_user.id and not current_user.is_admin:
        abort(403)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("اسم الصنف مطلوب", "error")
            return render_template("new_menu_item.html", restaurant=r,
                                   categories=RESTAURANT_CATEGORIES, form=request.form)
        try:
            price = float(request.form.get("price") or 0)
        except ValueError:
            price = 0.0
        item = MenuItem(
            restaurant_id=r.id, name=name, price=price,
            description=(request.form.get("description") or "").strip() or None,
            image_url=(request.form.get("image_url") or "").strip() or None,
            category=(request.form.get("category") or "وجبات رئيسية").strip(),
        )
        db.session.add(item)
        db.session.commit()
        flash("تم إضافة الصنف للمنيو", "success")
        return redirect(url_for("restaurant_detail", rid=r.id))
    return render_template("new_menu_item.html", restaurant=r,
                           categories=RESTAURANT_CATEGORIES, form={})


# ── Delivery dashboard ────────────────────────────────────────────────────────
@auth_bp.route("/delivery/orders")
@delivery_required
def delivery_orders():
    pending  = Order.query.filter_by(status="confirmed", delivery_id=None).all()
    my_orders = Order.query.filter_by(delivery_id=current_user.id).order_by(
        Order.created_at.desc()).limit(20).all()
    return render_template("delivery_orders.html", pending=pending, my_orders=my_orders)


@auth_bp.route("/delivery/orders/<int:oid>/take", methods=["POST"])
@delivery_required
def delivery_take(oid):
    order = Order.query.get_or_404(oid)
    if order.delivery_id:
        flash("هذا الطلب مأخوذ من مندوب آخر", "error")
        return redirect(url_for("auth.delivery_orders"))
    order.delivery_id = current_user.id
    order.status = "delivering"
    db.session.commit()
    flash(f"أخذت الطلب #{oid} — وصّله بأسرع وقت!", "success")
    return redirect(url_for("auth.delivery_orders"))


@auth_bp.route("/delivery/orders/<int:oid>/done", methods=["POST"])
@delivery_required
def delivery_done(oid):
    order = Order.query.get_or_404(oid)
    if order.delivery_id != current_user.id:
        abort(403)
    order.status = "done"
    current_user.total_deliveries += 1
    # Credit delivery commission
    w = current_user.get_or_create_wallet()
    w.credit(DELIVERY_COMMISSION, "delivery_commission",
              f"عمولة توصيل — طلب #{oid}")
    db.session.commit()
    flash(f"تم تسليم الطلب #{oid} — ربحت 500 د.ع عمولة!", "success")
    return redirect(url_for("auth.delivery_orders"))


# ── Admin panel ───────────────────────────────────────────────────────────────
@auth_bp.route("/admin")
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    posts = Post.query.order_by(Post.created_at.desc()).all()
    stats = {
        "total_users":  len(users),
        "merchants":    sum(1 for u in users if u.role == ROLE_MERCHANT),
        "customers":    sum(1 for u in users if u.role == ROLE_CUSTOMER),
        "technicians":  sum(1 for u in users if u.role == ROLE_TECHNICIAN),
        "delivery":     sum(1 for u in users if u.role == ROLE_DELIVERY),
        "admins":       sum(1 for u in users if u.role == ROLE_ADMIN),
        "total_posts":  len(posts),
        "pending_posts": sum(1 for p in posts if not p.approved),
        "total_orders": Order.query.count(),
    }
    return render_template("admin.html", users=users, posts=posts, stats=stats)


@auth_bp.route("/admin/posts")
@admin_required
def admin_posts():
    pending = Post.query.filter_by(approved=False).order_by(Post.created_at.desc()).all()
    rest_pending = Restaurant.query.filter_by(approved=False).all()
    return render_template("admin_posts.html", pending=pending, rest_pending=rest_pending)


@auth_bp.route("/admin/posts/<int:post_id>/approve", methods=["POST"])
@admin_required
def admin_approve_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.approved = True
    db.session.commit()
    flash(f"تمت الموافقة على '{post.title}'", "success")
    return redirect(url_for("auth.admin_posts"))


@auth_bp.route("/admin/posts/<int:post_id>/reject", methods=["POST"])
@admin_required
def admin_reject_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash("تم رفض المنشور وحذفه", "success")
    return redirect(url_for("auth.admin_posts"))


@auth_bp.route("/admin/restaurants/<int:rid>/approve", methods=["POST"])
@admin_required
def admin_approve_restaurant(rid):
    r = Restaurant.query.get_or_404(rid)
    r.approved = True
    db.session.commit()
    flash(f"تمت الموافقة على مطعم '{r.name}'", "success")
    return redirect(url_for("auth.admin_posts"))


@auth_bp.route("/admin/promote/<int:user_id>", methods=["POST"])
@admin_required
def admin_promote(user_id):
    new_role = (request.form.get("role") or "").strip()
    if new_role not in (ROLE_MERCHANT, ROLE_CUSTOMER, ROLE_TECHNICIAN, ROLE_DELIVERY, ROLE_ADMIN):
        flash("نوع حساب غير صحيح", "error")
        return redirect(url_for("auth.admin_panel"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id and new_role != ROLE_ADMIN:
        flash("ما تكدر تنزّل صلاحياتك بنفسك", "error")
        return redirect(url_for("auth.admin_panel"))
    user.role = new_role
    db.session.commit()
    flash(f"تم تحديث صلاحية {user.name}", "success")
    return redirect(url_for("auth.admin_panel"))


@auth_bp.route("/admin/delete-user/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("ما تكدر تحذف نفسك", "error")
        return redirect(url_for("auth.admin_panel"))
    db.session.delete(user)
    db.session.commit()
    flash("تم حذف الحساب", "success")
    return redirect(url_for("auth.admin_panel"))


@auth_bp.route("/admin/delete-post/<int:post_id>", methods=["POST"])
@admin_required
def admin_delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash("تم حذف المنشور", "success")
    return redirect(url_for("auth.admin_panel"))
