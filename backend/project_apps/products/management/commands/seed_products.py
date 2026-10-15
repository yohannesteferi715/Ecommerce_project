"""
Management command: seed_products
==================================
Populates the database with a realistic e-commerce product catalog for
development and demo purposes.

Usage
-----
Local:
    python manage.py seed_products
    python manage.py seed_products --dry-run
    python manage.py seed_products --verbosity 0   # silent
    python manage.py seed_products --verbosity 2   # verbose

Docker:
    docker compose exec web python manage.py seed_products

Safety
------
- Uses get_or_create / update_or_create so the command is fully idempotent.
- Never deletes existing records.
- Wraps all writes in a single atomic transaction (rolled back on --dry-run).
- Never touches users, orders, carts, payments, or any non-product data.
- Never uploads files; image fields are left blank to avoid Cloudinary network
  calls during seeding (the Cloudinary storage backend is active on this project).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from project_apps.products.models import (
    Attribute,
    AttributeValue,
    Category,
    Product,
    ProductVariant,
    ProductVariantAttribute,
    Tag,
)

# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

# --- Categories ------------------------------------------------------------
# Each entry: (name, parent_name_or_None, description, sort_order, featured)
CATEGORIES = [
    # Top-level
    ("Clothing",     None,        "Men's, women's and kids' apparel for every season.",          1,  True),
    ("Electronics",  None,        "Smartphones, laptops, audio gear and accessories.",            2,  True),
    ("Accessories",  None,        "Bags, belts, wallets, jewellery and more.",                    3,  False),
    ("Home & Living",None,        "Furniture, decor, kitchenware and everyday essentials.",       4,  False),
    # Children of Clothing
    ("Men's Clothing",   "Clothing",     "Shirts, trousers, jackets and activewear for men.",    1,  False),
    ("Women's Clothing", "Clothing",     "Dresses, tops, skirts and activewear for women.",      2,  False),
    # Children of Electronics
    ("Smartphones",      "Electronics",  "Latest flagship and mid-range smartphones.",           1,  True),
    ("Audio",            "Electronics",  "Headphones, earbuds, speakers and amplifiers.",        2,  False),
]

# --- Tags ------------------------------------------------------------------
# Each entry: (name, slug)
TAGS = [
    ("New Arrival",   "new-arrival"),
    ("Best Seller",   "best-seller"),
    ("On Sale",       "on-sale"),
    ("Limited Edition","limited-edition"),
    ("Eco Friendly",  "eco-friendly"),
    ("Premium",       "premium"),
    ("Casual",        "casual"),
    ("Formal",        "formal"),
    ("Wireless",      "wireless"),
    ("Waterproof",    "waterproof"),
    ("Unisex",        "unisex"),
    ("Gift Idea",     "gift-idea"),
]

# --- Attributes & their values ---------------------------------------------
# Each entry: (attribute_name, [(value, is_default, sort_order), ...])
ATTRIBUTES = [
    ("Color", [
        ("Black",       True,  1),
        ("White",       False, 2),
        ("Navy Blue",   False, 3),
        ("Grey",        False, 4),
        ("Olive Green", False, 5),
        ("Red",         False, 6),
        ("Beige",       False, 7),
    ]),
    ("Size", [
        ("XS",  False, 1),
        ("S",   True,  2),
        ("M",   False, 3),
        ("L",   False, 4),
        ("XL",  False, 5),
        ("XXL", False, 6),
    ]),
    ("Material", [
        ("Cotton",          True,  1),
        ("Polyester",       False, 2),
        ("Wool",            False, 3),
        ("Denim",           False, 4),
        ("Leather",         False, 5),
        ("Linen",           False, 6),
        ("Nylon",           False, 7),
        ("Merino Wool",     False, 8),
    ]),
    ("Storage", [
        ("64 GB",  False, 1),
        ("128 GB", True,  2),
        ("256 GB", False, 3),
        ("512 GB", False, 4),
        ("1 TB",   False, 5),
    ]),
    ("Connectivity", [
        ("Bluetooth 5.3", True,  1),
        ("USB-C",         False, 2),
        ("Wi-Fi 6",       False, 3),
        ("NFC",           False, 4),
    ]),
    ("Brand", [
        ("SoundWave",  True,  1),
        ("TechPro",    False, 2),
        ("UrbanWear",  False, 3),
        ("EcoThread",  False, 4),
        ("LuxeCraft",  False, 5),
    ]),
]

# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
# Each product entry:
# {
#   "name": str,
#   "category": str,           # category name
#   "description": str,
#   "tags": [str, ...],        # tag names
#   "variants": [
#     {
#       "sku": str,
#       "price": str,          # Decimal-safe string
#       "discount_price": str|None,
#       "stock": int,
#       "weight": str|None,
#       "dimensions": str|None,
#       "attributes": [(attr_name, value_str), ...],
#       "has_discount_window": bool,  # adds a future discount window if True
#     },
#     ...
#   ],
# }

# Discount window helper: 30-day window starting tomorrow
_DISCOUNT_START = timezone.now() + timezone.timedelta(days=1)
_DISCOUNT_END   = timezone.now() + timezone.timedelta(days=31)

PRODUCTS = [
    # ------------------------------------------------------------------ Clothing
    {
        "name": "Classic Oxford Shirt",
        "category": "Men's Clothing",
        "description": (
            "A timeless Oxford weave shirt crafted from 100% premium cotton. "
            "Features a button-down collar, chest pocket and a relaxed modern fit "
            "suitable for both smart-casual and formal occasions."
        ),
        "tags": ["Best Seller", "Formal", "Premium"],
        "variants": [
            {"sku": "OXF-BLK-S",  "price": "49.99", "discount_price": None, "stock": 30,
             "weight": "0.25", "dimensions": "30x20x3 cm",
             "attributes": [("Color", "Black"), ("Size", "S"), ("Material", "Cotton")]},
            {"sku": "OXF-BLK-M",  "price": "49.99", "discount_price": None, "stock": 45,
             "weight": "0.28", "dimensions": "32x22x3 cm",
             "attributes": [("Color", "Black"), ("Size", "M"), ("Material", "Cotton")]},
            {"sku": "OXF-BLK-L",  "price": "49.99", "discount_price": None, "stock": 40,
             "weight": "0.30", "dimensions": "34x24x3 cm",
             "attributes": [("Color", "Black"), ("Size", "L"), ("Material", "Cotton")]},
            {"sku": "OXF-WHT-M",  "price": "49.99", "discount_price": "39.99", "stock": 20,
             "weight": "0.28", "dimensions": "32x22x3 cm",
             "attributes": [("Color", "White"), ("Size", "M"), ("Material", "Cotton")],
             "has_discount_window": True},
            {"sku": "OXF-WHT-L",  "price": "49.99", "discount_price": "39.99", "stock": 18,
             "weight": "0.30", "dimensions": "34x24x3 cm",
             "attributes": [("Color", "White"), ("Size", "L"), ("Material", "Cotton")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "Slim Fit Chino Trousers",
        "category": "Men's Clothing",
        "description": (
            "Slim-fit chino trousers with a comfortable stretch waistband. "
            "Made from a cotton-polyester blend for easy care and all-day comfort."
        ),
        "tags": ["Casual", "Best Seller"],
        "variants": [
            {"sku": "CHN-BEI-S",  "price": "59.99", "discount_price": None, "stock": 25,
             "weight": "0.45", "attributes": [("Color", "Beige"),  ("Size", "S"), ("Material", "Cotton")]},
            {"sku": "CHN-BEI-M",  "price": "59.99", "discount_price": None, "stock": 35,
             "weight": "0.48", "attributes": [("Color", "Beige"),  ("Size", "M"), ("Material", "Cotton")]},
            {"sku": "CHN-NAV-M",  "price": "59.99", "discount_price": None, "stock": 30,
             "weight": "0.48", "attributes": [("Color", "Navy Blue"), ("Size", "M"), ("Material", "Cotton")]},
            {"sku": "CHN-NAV-L",  "price": "59.99", "discount_price": "49.99", "stock": 22,
             "weight": "0.50", "attributes": [("Color", "Navy Blue"), ("Size", "L"), ("Material", "Cotton")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "Merino Wool Crew Neck Sweater",
        "category": "Men's Clothing",
        "description": (
            "Luxuriously soft Merino wool crew-neck sweater. Naturally temperature-regulating, "
            "odour-resistant and machine washable. Perfect for layering year-round."
        ),
        "tags": ["Premium", "New Arrival", "Eco Friendly"],
        "variants": [
            {"sku": "MWS-GRY-S",  "price": "89.99", "discount_price": None, "stock": 15,
             "weight": "0.55", "attributes": [("Color", "Grey"),    ("Size", "S"), ("Material", "Merino Wool")]},
            {"sku": "MWS-GRY-M",  "price": "89.99", "discount_price": None, "stock": 20,
             "weight": "0.60", "attributes": [("Color", "Grey"),    ("Size", "M"), ("Material", "Merino Wool")]},
            {"sku": "MWS-NAV-M",  "price": "89.99", "discount_price": None, "stock": 18,
             "weight": "0.60", "attributes": [("Color", "Navy Blue"), ("Size", "M"), ("Material", "Merino Wool")]},
            {"sku": "MWS-NAV-L",  "price": "89.99", "discount_price": None, "stock": 12,
             "weight": "0.65", "attributes": [("Color", "Navy Blue"), ("Size", "L"), ("Material", "Merino Wool")]},
        ],
    },
    {
        "name": "Relaxed Linen Summer Dress",
        "category": "Women's Clothing",
        "description": (
            "Effortlessly breezy linen dress with a relaxed silhouette and side pockets. "
            "Available in versatile neutral tones, perfect for warm-weather days."
        ),
        "tags": ["New Arrival", "Casual", "Eco Friendly"],
        "variants": [
            {"sku": "LSD-BEI-XS", "price": "74.99", "discount_price": None, "stock": 20,
             "weight": "0.35", "attributes": [("Color", "Beige"),  ("Size", "XS"), ("Material", "Linen")]},
            {"sku": "LSD-BEI-S",  "price": "74.99", "discount_price": None, "stock": 25,
             "weight": "0.37", "attributes": [("Color", "Beige"),  ("Size", "S"),  ("Material", "Linen")]},
            {"sku": "LSD-WHT-S",  "price": "74.99", "discount_price": "59.99", "stock": 18,
             "weight": "0.37", "attributes": [("Color", "White"),  ("Size", "S"),  ("Material", "Linen")],
             "has_discount_window": True},
            {"sku": "LSD-WHT-M",  "price": "74.99", "discount_price": "59.99", "stock": 22,
             "weight": "0.39", "attributes": [("Color", "White"),  ("Size", "M"),  ("Material", "Linen")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "High-Waist Yoga Leggings",
        "category": "Women's Clothing",
        "description": (
            "Four-way stretch high-waist leggings with a non-see-through fabric, "
            "hidden waistband pocket and flatlock seams for a chafe-free workout."
        ),
        "tags": ["Best Seller", "Casual"],
        "variants": [
            {"sku": "YGL-BLK-XS", "price": "44.99", "discount_price": None, "stock": 40,
             "weight": "0.22", "attributes": [("Color", "Black"), ("Size", "XS"), ("Material", "Nylon")]},
            {"sku": "YGL-BLK-S",  "price": "44.99", "discount_price": None, "stock": 50,
             "weight": "0.24", "attributes": [("Color", "Black"), ("Size", "S"),  ("Material", "Nylon")]},
            {"sku": "YGL-BLK-M",  "price": "44.99", "discount_price": None, "stock": 45,
             "weight": "0.26", "attributes": [("Color", "Black"), ("Size", "M"),  ("Material", "Nylon")]},
            {"sku": "YGL-GRY-S",  "price": "44.99", "discount_price": "34.99", "stock": 35,
             "weight": "0.24", "attributes": [("Color", "Grey"),  ("Size", "S"),  ("Material", "Nylon")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "Denim Jacket",
        "category": "Men's Clothing",
        "description": (
            "Classic washed denim jacket with button-front closure, two chest pockets "
            "and side-entry welt pockets. A wardrobe staple for every season."
        ),
        "tags": ["Casual", "Unisex", "Best Seller"],
        "variants": [
            {"sku": "DNM-BLK-S",  "price": "99.99", "discount_price": None, "stock": 20,
             "weight": "0.80", "attributes": [("Color", "Black"),   ("Size", "S"), ("Material", "Denim")]},
            {"sku": "DNM-BLK-M",  "price": "99.99", "discount_price": None, "stock": 25,
             "weight": "0.85", "attributes": [("Color", "Black"),   ("Size", "M"), ("Material", "Denim")]},
            {"sku": "DNM-BLK-L",  "price": "99.99", "discount_price": None, "stock": 20,
             "weight": "0.90", "attributes": [("Color", "Black"),   ("Size", "L"), ("Material", "Denim")]},
            {"sku": "DNM-NAV-M",  "price": "99.99", "discount_price": "79.99", "stock": 15,
             "weight": "0.85", "attributes": [("Color", "Navy Blue"), ("Size", "M"), ("Material", "Denim")],
             "has_discount_window": True},
        ],
    },
    # ------------------------------------------------------------------ Electronics
    {
        "name": "TechPro X12 Smartphone",
        "category": "Smartphones",
        "description": (
            "The TechPro X12 features a 6.7-inch AMOLED display, a triple-lens "
            "50 MP camera system, and a 5000 mAh battery with 65 W fast charging. "
            "Available in two storage configurations."
        ),
        "tags": ["New Arrival", "Premium", "Best Seller"],
        "variants": [
            {"sku": "TPX12-BLK-128", "price": "699.99", "discount_price": None, "stock": 50,
             "weight": "0.19", "dimensions": "16.4x7.5x0.8 cm",
             "attributes": [("Color", "Black"),  ("Storage", "128 GB"), ("Brand", "TechPro")]},
            {"sku": "TPX12-WHT-128", "price": "699.99", "discount_price": None, "stock": 40,
             "weight": "0.19", "dimensions": "16.4x7.5x0.8 cm",
             "attributes": [("Color", "White"),  ("Storage", "128 GB"), ("Brand", "TechPro")]},
            {"sku": "TPX12-BLK-256", "price": "799.99", "discount_price": None, "stock": 35,
             "weight": "0.19", "dimensions": "16.4x7.5x0.8 cm",
             "attributes": [("Color", "Black"),  ("Storage", "256 GB"), ("Brand", "TechPro")]},
            {"sku": "TPX12-WHT-256", "price": "799.99", "discount_price": "749.99", "stock": 25,
             "weight": "0.19", "dimensions": "16.4x7.5x0.8 cm",
             "attributes": [("Color", "White"),  ("Storage", "256 GB"), ("Brand", "TechPro")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "TechPro X12 Pro Smartphone",
        "category": "Smartphones",
        "description": (
            "The flagship X12 Pro raises the bar with a 6.9-inch ProMotion display, "
            "periscope telephoto lens, titanium frame and support for satellite connectivity."
        ),
        "tags": ["New Arrival", "Premium", "Limited Edition"],
        "variants": [
            {"sku": "TPX12P-BLK-256", "price": "999.99",  "discount_price": None, "stock": 30,
             "weight": "0.22", "dimensions": "16.7x7.7x0.9 cm",
             "attributes": [("Color", "Black"),  ("Storage", "256 GB"), ("Brand", "TechPro")]},
            {"sku": "TPX12P-WHT-256", "price": "999.99",  "discount_price": None, "stock": 20,
             "weight": "0.22", "dimensions": "16.7x7.7x0.9 cm",
             "attributes": [("Color", "White"),  ("Storage", "256 GB"), ("Brand", "TechPro")]},
            {"sku": "TPX12P-BLK-512", "price": "1099.99", "discount_price": None, "stock": 15,
             "weight": "0.22", "dimensions": "16.7x7.7x0.9 cm",
             "attributes": [("Color", "Black"),  ("Storage", "512 GB"), ("Brand", "TechPro")]},
            {"sku": "TPX12P-WHT-1TB", "price": "1199.99", "discount_price": None, "stock": 10,
             "weight": "0.22", "dimensions": "16.7x7.7x0.9 cm",
             "attributes": [("Color", "White"),  ("Storage", "1 TB"), ("Brand", "TechPro")]},
        ],
    },
    {
        "name": "SoundWave ANC Headphones",
        "category": "Audio",
        "description": (
            "Over-ear headphones with industry-leading active noise cancellation, "
            "30-hour battery life and multi-point Bluetooth 5.3 pairing. "
            "Foldable design with premium cushioning for all-day comfort."
        ),
        "tags": ["Best Seller", "Premium", "Wireless"],
        "variants": [
            {"sku": "SWANC-BLK", "price": "249.99", "discount_price": "199.99", "stock": 60,
             "weight": "0.25", "dimensions": "19x17x8 cm",
             "attributes": [("Color", "Black"),  ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")],
             "has_discount_window": True},
            {"sku": "SWANC-WHT", "price": "249.99", "discount_price": "199.99", "stock": 45,
             "weight": "0.25", "dimensions": "19x17x8 cm",
             "attributes": [("Color", "White"),  ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")],
             "has_discount_window": True},
            {"sku": "SWANC-NAV", "price": "249.99", "discount_price": None, "stock": 30,
             "weight": "0.25", "dimensions": "19x17x8 cm",
             "attributes": [("Color", "Navy Blue"), ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")]},
        ],
    },
    {
        "name": "SoundWave True Wireless Earbuds",
        "category": "Audio",
        "description": (
            "Compact true-wireless earbuds with 8-hour playback plus 24-hour charging case, "
            "IPX4 sweat resistance and adaptive EQ. Works seamlessly across all devices."
        ),
        "tags": ["New Arrival", "Wireless", "Waterproof"],
        "variants": [
            {"sku": "SWTW-BLK", "price": "129.99", "discount_price": None, "stock": 80,
             "weight": "0.055", "attributes": [("Color", "Black"), ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")]},
            {"sku": "SWTW-WHT", "price": "129.99", "discount_price": None, "stock": 70,
             "weight": "0.055", "attributes": [("Color", "White"), ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")]},
        ],
    },
    {
        "name": "Portable Bluetooth Speaker",
        "category": "Audio",
        "description": (
            "360-degree sound in a rugged, waterproof cylindrical body. "
            "Up to 20-hour battery, built-in microphone for calls and USB-C charging."
        ),
        "tags": ["Best Seller", "Wireless", "Waterproof", "Casual"],
        "variants": [
            {"sku": "PBTS-BLK", "price": "79.99",  "discount_price": "64.99", "stock": 55,
             "weight": "0.60", "dimensions": "7x7x18 cm",
             "attributes": [("Color", "Black"),      ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")],
             "has_discount_window": True},
            {"sku": "PBTS-OLV", "price": "79.99",  "discount_price": None,    "stock": 40,
             "weight": "0.60", "dimensions": "7x7x18 cm",
             "attributes": [("Color", "Olive Green"), ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")]},
            {"sku": "PBTS-RED", "price": "79.99",  "discount_price": None,    "stock": 35,
             "weight": "0.60", "dimensions": "7x7x18 cm",
             "attributes": [("Color", "Red"),        ("Connectivity", "Bluetooth 5.3"), ("Brand", "SoundWave")]},
        ],
    },
    # ------------------------------------------------------------------ Accessories
    {
        "name": "Genuine Leather Bifold Wallet",
        "category": "Accessories",
        "description": (
            "Hand-stitched full-grain leather bifold wallet with RFID-blocking lining, "
            "8 card slots, 2 currency compartments and a slim profile."
        ),
        "tags": ["Premium", "Gift Idea", "Best Seller"],
        "variants": [
            {"sku": "LBW-BLK", "price": "54.99", "discount_price": None, "stock": 60,
             "weight": "0.08", "attributes": [("Color", "Black"),  ("Material", "Leather"), ("Brand", "LuxeCraft")]},
            {"sku": "LBW-BRN", "price": "54.99", "discount_price": None, "stock": 50,
             "weight": "0.08", "attributes": [("Color", "Beige"),  ("Material", "Leather"), ("Brand", "LuxeCraft")]},
        ],
    },
    {
        "name": "Canvas Tote Bag",
        "category": "Accessories",
        "description": (
            "Oversized cotton canvas tote with reinforced handles, an interior zip pocket "
            "and a magnetic snap closure. Perfect for groceries, the gym or the beach."
        ),
        "tags": ["Eco Friendly", "Casual", "Unisex", "New Arrival"],
        "variants": [
            {"sku": "CTB-NAV", "price": "34.99", "discount_price": None, "stock": 70,
             "weight": "0.40", "attributes": [("Color", "Navy Blue"), ("Material", "Cotton"), ("Brand", "EcoThread")]},
            {"sku": "CTB-BEI", "price": "34.99", "discount_price": None, "stock": 65,
             "weight": "0.40", "attributes": [("Color", "Beige"),    ("Material", "Cotton"), ("Brand", "EcoThread")]},
            {"sku": "CTB-BLK", "price": "34.99", "discount_price": "27.99", "stock": 50,
             "weight": "0.40", "attributes": [("Color", "Black"),    ("Material", "Cotton"), ("Brand", "EcoThread")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "Stainless Steel Watch",
        "category": "Accessories",
        "description": (
            "Minimalist stainless steel watch with sapphire crystal glass, 5 ATM water "
            "resistance and a quick-release NATO strap. Battery-free solar movement."
        ),
        "tags": ["Premium", "Gift Idea", "Limited Edition"],
        "variants": [
            {"sku": "SSW-BLK", "price": "199.99", "discount_price": None, "stock": 25,
             "weight": "0.12", "attributes": [("Color", "Black"), ("Brand", "LuxeCraft")]},
            {"sku": "SSW-SLV", "price": "199.99", "discount_price": None, "stock": 20,
             "weight": "0.12", "attributes": [("Color", "Grey"),  ("Brand", "LuxeCraft")]},
        ],
    },
    # ------------------------------------------------------------------ Home & Living
    {
        "name": "Bamboo Cutting Board Set",
        "category": "Home & Living",
        "description": (
            "Set of 3 sustainably sourced bamboo cutting boards in small, medium and large "
            "sizes. Naturally anti-bacterial, knife-friendly and easy to clean."
        ),
        "tags": ["Eco Friendly", "Gift Idea", "New Arrival"],
        "variants": [
            {"sku": "BCB-SET", "price": "39.99", "discount_price": "32.99", "stock": 80,
             "weight": "1.20", "dimensions": "38x28x1.5 cm",
             "attributes": [("Material", "Cotton")],   # closest available; bamboo maps to Eco
             "has_discount_window": True},
        ],
    },
    {
        "name": "Linen Throw Cushion Cover",
        "category": "Home & Living",
        "description": (
            "Stonewashed linen cushion cover with a concealed zip. "
            "Available in a range of muted tones to complement any interior style."
        ),
        "tags": ["Eco Friendly", "Casual", "New Arrival"],
        "variants": [
            {"sku": "LCC-BEI", "price": "19.99", "discount_price": None, "stock": 100,
             "weight": "0.18", "attributes": [("Color", "Beige"),  ("Material", "Linen")]},
            {"sku": "LCC-GRY", "price": "19.99", "discount_price": None, "stock": 90,
             "weight": "0.18", "attributes": [("Color", "Grey"),   ("Material", "Linen")]},
            {"sku": "LCC-OLV", "price": "19.99", "discount_price": None, "stock": 75,
             "weight": "0.18", "attributes": [("Color", "Olive Green"), ("Material", "Linen")]},
        ],
    },
    {
        "name": "Ceramic Pour-Over Coffee Set",
        "category": "Home & Living",
        "description": (
            "Handcrafted ceramic pour-over dripper and matching server with a natural "
            "wood collar and leather tie. Makes 1-4 cups. Includes 40 paper filters."
        ),
        "tags": ["Premium", "Gift Idea", "Limited Edition"],
        "variants": [
            {"sku": "CPOC-WHT", "price": "64.99", "discount_price": None, "stock": 35,
             "weight": "0.95", "dimensions": "14x12x22 cm",
             "attributes": [("Color", "White")]},
            {"sku": "CPOC-BLK", "price": "64.99", "discount_price": None, "stock": 30,
             "weight": "0.95", "dimensions": "14x12x22 cm",
             "attributes": [("Color", "Black")]},
        ],
    },
    {
        "name": "Organic Cotton Bath Towel Set",
        "category": "Home & Living",
        "description": (
            "Set of 4 GOTS-certified organic cotton bath towels (2 bath + 2 hand). "
            "600 GSM, double-loop pile for maximum softness and quick drying."
        ),
        "tags": ["Eco Friendly", "Premium", "Best Seller"],
        "variants": [
            {"sku": "OCT-WHT", "price": "49.99", "discount_price": None, "stock": 60,
             "weight": "1.80", "attributes": [("Color", "White"), ("Material", "Cotton")]},
            {"sku": "OCT-GRY", "price": "49.99", "discount_price": None, "stock": 55,
             "weight": "1.80", "attributes": [("Color", "Grey"),  ("Material", "Cotton")]},
            {"sku": "OCT-BEI", "price": "49.99", "discount_price": "39.99", "stock": 45,
             "weight": "1.80", "attributes": [("Color", "Beige"), ("Material", "Cotton")],
             "has_discount_window": True},
        ],
    },
    {
        "name": "Scented Soy Wax Candle",
        "category": "Home & Living",
        "description": (
            "Hand-poured soy wax candle in a reusable glass jar. "
            "60-hour burn time, lead-free cotton wick and available in three "
            "signature fragrance blends."
        ),
        "tags": ["Gift Idea", "Eco Friendly", "New Arrival"],
        "variants": [
            {"sku": "SWC-CEW", "price": "24.99", "discount_price": None, "stock": 80,
             "weight": "0.30", "attributes": [("Color", "White")]},   # Cedarwood & White Sage
            {"sku": "SWC-VNL", "price": "24.99", "discount_price": None, "stock": 75,
             "weight": "0.30", "attributes": [("Color", "Beige")]},   # Vanilla & Amber
            {"sku": "SWC-LAV", "price": "24.99", "discount_price": "19.99", "stock": 60,
             "weight": "0.30", "attributes": [("Color", "Grey")],
             "has_discount_window": True},                              # Lavender & Chamomile
        ],
    },
    {
        "name": "Wool Blend Throw Blanket",
        "category": "Home & Living",
        "description": (
            "Super-soft wool-blend throw in a classic herringbone weave. "
            "130x180 cm, machine washable at 30°C."
        ),
        "tags": ["Premium", "Gift Idea"],
        "variants": [
            {"sku": "WBT-GRY", "price": "79.99", "discount_price": None, "stock": 40,
             "weight": "1.10", "dimensions": "130x180x0.5 cm",
             "attributes": [("Color", "Grey"),    ("Material", "Wool")]},
            {"sku": "WBT-BEI", "price": "79.99", "discount_price": None, "stock": 35,
             "weight": "1.10", "dimensions": "130x180x0.5 cm",
             "attributes": [("Color", "Beige"),   ("Material", "Wool")]},
            {"sku": "WBT-NAV", "price": "79.99", "discount_price": "64.99", "stock": 28,
             "weight": "1.10", "dimensions": "130x180x0.5 cm",
             "attributes": [("Color", "Navy Blue"), ("Material", "Wool")],
             "has_discount_window": True},
        ],
    },
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Seed the database with realistic product catalog data "
        "(categories, tags, attributes, products, variants). "
        "Safe to run multiple times — uses get_or_create / update_or_create."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Preview the changes without committing them to the database. "
                "All writes are rolled back at the end."
            ),
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        verbosity: int = options["verbosity"]

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY RUN mode — no changes will be saved.\n"
            ))

        counters: dict[str, dict[str, int]] = {
            model: {"created": 0, "updated": 0, "unchanged": 0}
            for model in [
                "Category", "Tag", "Attribute", "AttributeValue",
                "Product", "ProductVariant", "ProductVariantAttribute",
            ]
        }

        try:
            with transaction.atomic():
                self._seed_categories(counters, verbosity)
                self._seed_tags(counters, verbosity)
                self._seed_attributes(counters, verbosity)
                self._seed_products(counters, verbosity)

                if dry_run:
                    # Roll back every write performed inside this block
                    raise _DryRunRollback()

        except _DryRunRollback:
            pass  # expected — transaction was rolled back cleanly

        self._print_summary(counters, dry_run)

    # ------------------------------------------------------------------
    # Seeding helpers
    # ------------------------------------------------------------------

    def _seed_categories(self, counters: dict, verbosity: int) -> None:
        """
        Create/update Category records.
        Parent categories are processed before children by iterating CATEGORIES
        in definition order (parents are listed first).
        """
        cat_cache: dict[str, Category] = {}

        for name, parent_name, description, sort_order, featured in CATEGORIES:
            parent: Category | None = cat_cache.get(parent_name) if parent_name else None

            # Slug is auto-generated by Category.save(), but we look up by slug
            # so that repeated runs resolve to the same object reliably.
            expected_slug = slugify(name)

            obj, created = Category.objects.get_or_create(
                slug=expected_slug,
                defaults={
                    "name":        name,
                    "parent":      parent,
                    "description": description,
                    "sort_order":  sort_order,
                    "featured":    featured,
                    "is_active":   True,
                },
            )

            if created:
                counters["Category"]["created"] += 1
                if verbosity >= 2:
                    self.stdout.write(f"  [CREATE] Category: {name}")
            else:
                # Update mutable fields; never overwrite user-managed content.
                changed = False
                if obj.description != description:
                    obj.description = description
                    changed = True
                if obj.sort_order != sort_order:
                    obj.sort_order = sort_order
                    changed = True
                if obj.featured != featured:
                    obj.featured = featured
                    changed = True
                if obj.parent != parent:
                    obj.parent = parent
                    changed = True
                if changed:
                    obj.save()
                    counters["Category"]["updated"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  [UPDATE] Category: {name}")
                else:
                    counters["Category"]["unchanged"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  [OK]     Category: {name}")

            cat_cache[name] = obj

    def _seed_tags(self, counters: dict, verbosity: int) -> None:
        """Create Tag records. Slug is explicit — Tag has no auto-slug."""
        for name, slug in TAGS:
            obj, created = Tag.objects.get_or_create(
                slug=slug,
                defaults={"name": name},
            )
            if created:
                counters["Tag"]["created"] += 1
                if verbosity >= 2:
                    self.stdout.write(f"  [CREATE] Tag: {name}")
            else:
                counters["Tag"]["unchanged"] += 1
                if verbosity >= 2:
                    self.stdout.write(f"  [OK]     Tag: {name}")

    def _seed_attributes(self, counters: dict, verbosity: int) -> None:
        """Create Attribute and AttributeValue records."""
        for attr_name, values in ATTRIBUTES:
            attr, attr_created = Attribute.objects.get_or_create(name=attr_name)
            if attr_created:
                counters["Attribute"]["created"] += 1
                if verbosity >= 2:
                    self.stdout.write(f"  [CREATE] Attribute: {attr_name}")
            else:
                counters["Attribute"]["unchanged"] += 1
                if verbosity >= 2:
                    self.stdout.write(f"  [OK]     Attribute: {attr_name}")

            for value_str, is_default, sort_order in values:
                # unique_together = (attribute, value)
                val, val_created = AttributeValue.objects.get_or_create(
                    attribute=attr,
                    value=value_str,
                    defaults={
                        "is_default": is_default,
                        "sort_order": sort_order,
                    },
                )
                if val_created:
                    counters["AttributeValue"]["created"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"    [CREATE] AttributeValue: {attr_name} → {value_str}")
                else:
                    counters["AttributeValue"]["unchanged"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"    [OK]     AttributeValue: {attr_name} → {value_str}")

    def _seed_products(self, counters: dict, verbosity: int) -> None:
        """
        Create Product, ProductVariant and ProductVariantAttribute records.
        """
        # Pre-load lookup caches to avoid per-iteration queries
        category_cache:  dict[str, Category]       = {c.name: c for c in Category.objects.all()}
        tag_cache:       dict[str, Tag]             = {t.name: t for t in Tag.objects.all()}
        attr_cache:      dict[str, Attribute]       = {a.name: a for a in Attribute.objects.all()}
        av_cache:        dict[tuple, AttributeValue] = {
            (av.attribute_id, av.value): av
            for av in AttributeValue.objects.select_related("attribute").all()
        }

        for product_data in PRODUCTS:
            product_name  = product_data["name"]
            category_name = product_data["category"]
            description   = product_data["description"]
            tag_names     = product_data.get("tags", [])
            variants_data = product_data.get("variants", [])

            category = category_cache.get(category_name)
            if category is None:
                self.stderr.write(
                    self.style.ERROR(
                        f"Category '{category_name}' not found for product "
                        f"'{product_name}'. Skipping product."
                    )
                )
                continue

            # Product.save() auto-generates slug from name
            product, p_created = Product.objects.get_or_create(
                slug=slugify(product_name),
                defaults={
                    "name":        product_name,
                    "category":    category,
                    "description": description,
                    "is_active":   True,
                },
            )

            if p_created:
                counters["Product"]["created"] += 1
                if verbosity >= 2:
                    self.stdout.write(f"  [CREATE] Product: {product_name}")
            else:
                # Refresh description if it changed in seed data
                changed = False
                if product.description != description:
                    product.description = description
                    changed = True
                if product.category != category:
                    product.category = category
                    changed = True
                if changed:
                    product.save()
                    counters["Product"]["updated"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  [UPDATE] Product: {product_name}")
                else:
                    counters["Product"]["unchanged"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  [OK]     Product: {product_name}")

            # --- M2M Tags ---
            desired_tags = [tag_cache[n] for n in tag_names if n in tag_cache]
            missing_tags = [n for n in tag_names if n not in tag_cache]
            if missing_tags and verbosity >= 1:
                self.stderr.write(
                    self.style.WARNING(
                        f"Tags not found for '{product_name}': {missing_tags}"
                    )
                )
            product.tags.set(desired_tags)

            # --- Variants ---
            for v in variants_data:
                sku             = v["sku"]
                price           = Decimal(v["price"])
                discount_price  = Decimal(v["discount_price"]) if v.get("discount_price") else None
                stock           = v["stock"]
                weight          = Decimal(v["weight"]) if v.get("weight") else None
                dimensions      = v.get("dimensions")
                attr_pairs      = v.get("attributes", [])
                has_window      = v.get("has_discount_window", False)

                discount_start = _DISCOUNT_START if (has_window and discount_price) else None
                discount_end   = _DISCOUNT_END   if (has_window and discount_price) else None

                variant, v_created = ProductVariant.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "product":        product,
                        "price":          price,
                        "discount_price": discount_price,
                        "stock":          stock,
                        "weight":         weight,
                        "dimensions":     dimensions,
                        "is_active":      True,
                        "discount_start": discount_start,
                        "discount_end":   discount_end,
                    },
                )

                if v_created:
                    counters["ProductVariant"]["created"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"    [CREATE] Variant: {sku}")
                else:
                    # Keep prices and stock fresh without touching user edits
                    update_fields = []
                    if variant.price != price:
                        variant.price = price
                        update_fields.append("price")
                    if variant.stock != stock:
                        variant.stock = stock
                        update_fields.append("stock")
                    if update_fields:
                        variant.save(update_fields=update_fields)
                        counters["ProductVariant"]["updated"] += 1
                        if verbosity >= 2:
                            self.stdout.write(
                                f"    [UPDATE] Variant: {sku} ({', '.join(update_fields)})"
                            )
                    else:
                        counters["ProductVariant"]["unchanged"] += 1
                        if verbosity >= 2:
                            self.stdout.write(f"    [OK]     Variant: {sku}")

                # --- Variant Attributes ---
                for attr_name, value_str in attr_pairs:
                    attr = attr_cache.get(attr_name)
                    if attr is None:
                        if verbosity >= 1:
                            self.stderr.write(
                                self.style.WARNING(
                                    f"Attribute '{attr_name}' not found for variant {sku}. Skipping."
                                )
                            )
                        continue

                    av = av_cache.get((attr.pk, value_str))
                    if av is None:
                        if verbosity >= 1:
                            self.stderr.write(
                                self.style.WARNING(
                                    f"AttributeValue '{attr_name}: {value_str}' not found "
                                    f"for variant {sku}. Skipping."
                                )
                            )
                        continue

                    # unique_together = (variant, attribute, value)
                    _, pva_created = ProductVariantAttribute.objects.get_or_create(
                        variant=variant,
                        attribute=attr,
                        value=av,
                    )
                    if pva_created:
                        counters["ProductVariantAttribute"]["created"] += 1
                    else:
                        counters["ProductVariantAttribute"]["unchanged"] += 1

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _print_summary(self, counters: dict, dry_run: bool) -> None:
        self.stdout.write("")
        header = "Seed summary (DRY RUN — no data was saved)" if dry_run else "Seed summary"
        self.stdout.write(self.style.SUCCESS(f"{'─' * 55}"))
        self.stdout.write(self.style.SUCCESS(header))
        self.stdout.write(self.style.SUCCESS(f"{'─' * 55}"))

        col_w = 26
        self.stdout.write(
            f"  {'Model':<{col_w}}  {'Created':>8}  {'Updated':>8}  {'Unchanged':>9}"
        )
        self.stdout.write(f"  {'─' * col_w}  {'─' * 8}  {'─' * 8}  {'─' * 9}")

        for model, stats in counters.items():
            self.stdout.write(
                f"  {model:<{col_w}}  "
                f"{stats['created']:>8}  "
                f"{stats['updated']:>8}  "
                f"{stats['unchanged']:>9}"
            )

        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "  All changes rolled back. Run without --dry-run to persist."
            ))
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("  Done. Product catalog seeded successfully."))


# ---------------------------------------------------------------------------
# Internal sentinel exception used to roll back a dry-run transaction
# ---------------------------------------------------------------------------

class _DryRunRollback(Exception):
    """Raised inside an atomic block to trigger a clean rollback for --dry-run."""
