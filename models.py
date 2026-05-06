"""Database models for Surface حديثة."""
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# ── Roles ─────────────────────────────────────────────────────────────────────
ROLE_MERCHANT   = "merchant"
ROLE_CUSTOMER   = "customer"
ROLE_TECHNICIAN = "technician"
ROLE_DELIVERY   = "delivery"
ROLE_ADMIN      = "admin"

VALID_ROLES = (ROLE_CUSTOMER, ROLE_MERCHANT, ROLE_TECHNICIAN, ROLE_DELIVERY)
ALL_ROLES   = VALID_ROLES + (ROLE_ADMIN,)

# ── Subscriptions ──────────────────────────────────────────────────────────────
PLAN_FREE = "free"
PLAN_PLUS = "plus"
PLAN_VIP  = "vip"
PLANS = (PLAN_FREE, PLAN_PLUS, PLAN_VIP)
PLAN_PRICES = {PLAN_FREE: 0, PLAN_PLUS: 5_000, PLAN_VIP: 15_000}
PLAN_LABELS = {PLAN_FREE: "مجاني", PLAN_PLUS: "Plus", PLAN_VIP: "VIP"}

# ── Commissions ────────────────────────────────────────────────────────────────
DELIVERY_COMMISSION    = 500       # IQD per delivery
MERCHANT_COMMISSION    = 500       # IQD per 20,000 IQD sales
MERCHANT_SALES_UNIT    = 20_000    # sales threshold

# ── Shop & restaurant ──────────────────────────────────────────────────────────
SHOP_CATEGORIES = (
    "إلكترونيات",
    "ملابس رجالية",
    "ملابس أطفال",
    "أحذية وحقائب",
    "أدوية",
    "مواد غذائية",
    "مخضر",
    "مواد إنشائية",
    "كماليات",
)

RESTAURANT_CATEGORIES = (
    "وجبات رئيسية",
    "مشاوي وكباب",
    "برغر وساندويشات",
    "بيتزا",
    "مشروبات",
    "حلويات",
    "وجبات خفيفة",
    "إفطار",
)

CRAFTS = (
    "كهربائي", "سباك", "بناء", "صباغ",
    "لحام", "نجار", "فني تكييف", "مكاني",
    "حدّاد", "بلاط",
)

VEHICLES = ("سيارة", "دراجة نارية", "بيك آب", "تكسي", "ماشي")


# ══════════════════════════════════════════════════════════════════════════════
#  User
# ══════════════════════════════════════════════════════════════════════════════
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(80), nullable=False)
    phone         = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.String(20), nullable=False, default=ROLE_CUSTOMER)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Profile fields
    craft            = db.Column(db.String(40), nullable=True)
    bio              = db.Column(db.Text, nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    photos_csv       = db.Column(db.Text, nullable=True)
    vehicle          = db.Column(db.String(40), nullable=True)
    area             = db.Column(db.String(80), nullable=True)

    # Subscription
    subscription_plan = db.Column(db.String(10), nullable=False, default=PLAN_FREE)

    # Sales tracking (for merchant commission)
    total_sales       = db.Column(db.Float, nullable=False, default=0.0)
    commission_paid   = db.Column(db.Float, nullable=False, default=0.0)

    # Delivery: total deliveries done
    total_deliveries  = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    posts         = db.relationship("Post",       backref="merchant", lazy=True, cascade="all, delete-orphan")
    wallet        = db.relationship("Wallet",     backref="user",     uselist=False, cascade="all, delete-orphan")
    cart_items    = db.relationship("CartItem",   backref="user",     lazy=True, cascade="all, delete-orphan")
    restaurants   = db.relationship("Restaurant", backref="owner",    lazy=True, cascade="all, delete-orphan")

    # ── helpers ──────────────────────────────────────────────────────────────
    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    def get_or_create_wallet(self) -> "Wallet":
        if not self.wallet:
            w = Wallet(user_id=self.id)
            db.session.add(w)
            db.session.flush()
            self.wallet = w
        return self.wallet

    @property
    def is_merchant(self)   -> bool: return self.role in (ROLE_MERCHANT, ROLE_ADMIN)
    @property
    def is_technician(self) -> bool: return self.role == ROLE_TECHNICIAN
    @property
    def is_delivery(self)   -> bool: return self.role == ROLE_DELIVERY
    @property
    def is_customer(self)   -> bool: return self.role == ROLE_CUSTOMER
    @property
    def is_admin(self)      -> bool: return self.role == ROLE_ADMIN

    @property
    def photos(self) -> list:
        if not self.photos_csv:
            return []
        return [p.strip() for p in self.photos_csv.split(",") if p.strip()]

    @property
    def plan_label(self) -> str:
        return PLAN_LABELS.get(self.subscription_plan, "مجاني")

    @property
    def role_label(self) -> str:
        return {
            ROLE_ADMIN:      "مدير النظام",
            ROLE_MERCHANT:   "تاجر",
            ROLE_TECHNICIAN: "فني",
            ROLE_DELIVERY:   "مندوب توصيل",
            ROLE_CUSTOMER:   "زبون",
        }.get(self.role, self.role)

    @property
    def wallet_balance(self) -> float:
        return self.wallet.balance if self.wallet else 0.0

    @property
    def cart_count(self) -> int:
        return sum(item.qty for item in self.cart_items)


# ══════════════════════════════════════════════════════════════════════════════
#  Wallet & Transactions
# ══════════════════════════════════════════════════════════════════════════════
class Wallet(db.Model):
    __tablename__ = "wallets"

    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    balance = db.Column(db.Float, nullable=False, default=0.0)

    transactions = db.relationship("Transaction", backref="wallet", lazy=True,
                                   order_by="Transaction.created_at.desc()",
                                   cascade="all, delete-orphan")

    def credit(self, amount: float, type_: str, note: str = "") -> None:
        self.balance += amount
        db.session.add(Transaction(wallet_id=self.id, amount=amount, type=type_, note=note))

    def debit(self, amount: float, type_: str, note: str = "") -> bool:
        if self.balance < amount:
            return False
        self.balance -= amount
        db.session.add(Transaction(wallet_id=self.id, amount=-amount, type=type_, note=note))
        return True


class Transaction(db.Model):
    __tablename__ = "transactions"

    id         = db.Column(db.Integer, primary_key=True)
    wallet_id  = db.Column(db.Integer, db.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    type       = db.Column(db.String(30), nullable=False)
    note       = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
#  Subscription
# ══════════════════════════════════════════════════════════════════════════════
class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan       = db.Column(db.String(10), nullable=False)
    price_paid = db.Column(db.Float, nullable=False, default=0.0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("subscriptions", lazy=True))


# ══════════════════════════════════════════════════════════════════════════════
#  Post  (shop items — needs admin approval)
# ══════════════════════════════════════════════════════════════════════════════
class Post(db.Model):
    __tablename__ = "posts"

    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    price       = db.Column(db.Float, nullable=False, default=0.0)
    category    = db.Column(db.String(40), nullable=False, default="عام")
    section     = db.Column(db.String(20), nullable=False, default="shop")
    image_url   = db.Column(db.String(500), nullable=True)
    approved    = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    merchant_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    cart_items  = db.relationship("CartItem", backref="post", lazy=True, cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════════════════
#  Restaurant & Menu
# ══════════════════════════════════════════════════════════════════════════════
class Restaurant(db.Model):
    __tablename__ = "restaurants"

    id          = db.Column(db.Integer, primary_key=True)
    owner_id    = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    logo_url    = db.Column(db.String(500), nullable=True)
    phone       = db.Column(db.String(20), nullable=True)
    area        = db.Column(db.String(80), nullable=True)
    is_open     = db.Column(db.Boolean, nullable=False, default=True)
    approved    = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    menu_items = db.relationship("MenuItem", backref="restaurant", lazy=True, cascade="all, delete-orphan")
    orders     = db.relationship("Order",    backref="restaurant", lazy=True)


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id            = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    name          = db.Column(db.String(100), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    price         = db.Column(db.Float, nullable=False, default=0.0)
    image_url     = db.Column(db.String(500), nullable=True)
    category      = db.Column(db.String(40), nullable=True)
    is_available  = db.Column(db.Boolean, nullable=False, default=True)

    cart_items = db.relationship("CartItem", backref="menu_item", lazy=True, cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════════════════
#  Cart
# ══════════════════════════════════════════════════════════════════════════════
class CartItem(db.Model):
    __tablename__ = "cart_items"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id",       ondelete="CASCADE"), nullable=False)
    menu_item_id  = db.Column(db.Integer, db.ForeignKey("menu_items.id",  ondelete="CASCADE"), nullable=True)
    post_id       = db.Column(db.Integer, db.ForeignKey("posts.id",       ondelete="CASCADE"), nullable=True)
    restaurant_id = db.Column(db.Integer, nullable=True)
    name          = db.Column(db.String(100), nullable=False)
    price         = db.Column(db.Float, nullable=False)
    qty           = db.Column(db.Integer, nullable=False, default=1)
    added_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def subtotal(self) -> float:
        return self.price * self.qty


# ══════════════════════════════════════════════════════════════════════════════
#  Orders
# ══════════════════════════════════════════════════════════════════════════════
ORDER_STATUS = {
    "pending":    "بانتظار الموافقة",
    "confirmed":  "مؤكد",
    "delivering": "في الطريق",
    "done":       "مكتمل",
    "cancelled":  "ملغي",
}


class Order(db.Model):
    __tablename__ = "orders"

    id            = db.Column(db.Integer, primary_key=True)
    customer_id   = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),   nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id", ondelete="SET NULL"), nullable=True)
    delivery_id   = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"),  nullable=True)
    status        = db.Column(db.String(20), nullable=False, default="pending")
    total         = db.Column(db.Float, nullable=False, default=0.0)
    address       = db.Column(db.String(200), nullable=True)
    note          = db.Column(db.String(300), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    customer  = db.relationship("User", foreign_keys=[customer_id],  backref="orders_made")
    delivery  = db.relationship("User", foreign_keys=[delivery_id],  backref="orders_delivered")
    items     = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")

    @property
    def status_label(self) -> str:
        return ORDER_STATUS.get(self.status, self.status)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id        = db.Column(db.Integer, primary_key=True)
    order_id  = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    item_name = db.Column(db.String(100), nullable=False)
    price     = db.Column(db.Float, nullable=False)
    qty       = db.Column(db.Integer, nullable=False, default=1)

    @property
    def subtotal(self) -> float:
        return self.price * self.qty

