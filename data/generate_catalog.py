#!/usr/bin/env python3
"""Generate a synthetic beauty-store catalog for the eval.

- Deterministic: the same SEED always produces the same catalog.json.
- Every brand, product and shade name is fictional.
- Products you write by hand for specific tasks (planted near-misses, edge
  cases) go in hand_crafted.json; they are appended after generation, so they
  never change the seeded part of the catalog.

Usage:
    python generate_catalog.py          # writes catalog.json and prints a summary
    python generate_catalog.py --check  # validates an existing catalog.json only
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

SEED = 20261101
CURRENCY = "USD"
HERE = Path(__file__).resolve().parent
OUT = HERE / "catalog.json"
HAND_CRAFTED = HERE / "hand_crafted.json"

BRANDS = ["Aurevia", "Moss & Mineral", "Kaelo", "Solenne Lab",
          "Velmora", "Tidepool Skin", "Orrin", "Halcyon Beauty"]

DEPTHS = ["fair", "light", "medium", "tan", "deep"]
UNDERTONES = {"cool": "C", "neutral": "N", "warm": "W", "olive": "O"}
SKIN_TYPES = ["dry", "oily", "combination", "normal", "sensitive"]

DEPTH_NAMES = {
    "fair": ["Porcelain", "Ivory", "Shell", "Alabaster"],
    "light": ["Linen", "Sand", "Buff", "Bisque"],
    "medium": ["Honey", "Almond", "Beige", "Wheat"],
    "tan": ["Amber", "Toffee", "Golden", "Cinnamon"],
    "deep": ["Espresso", "Mahogany", "Cocoa", "Walnut"],
}

COLOR_FAMILIES = {
    "nude": ["Bare", "Latte", "Skin Deep", "Biscuit"],
    "pink": ["Peony", "Candy", "Blossom"],
    "rose": ["Dusty Rose", "Petal", "Mauve"],
    "red": ["Cherry", "Ruby", "Flame", "Poppy"],
    "berry": ["Plum", "Mulberry", "Fig"],
    "coral": ["Papaya", "Sunset", "Melon"],
    "brown": ["Mocha", "Cedar", "Chestnut"],
}

INGREDIENT_POOLS = {
    "cleanser": ["salicylic acid", "glycolic acid", "ceramides", "hyaluronic acid", "centella asiatica"],
    "toner": ["glycolic acid", "salicylic acid", "niacinamide", "hyaluronic acid", "centella asiatica"],
    "serum": ["niacinamide", "hyaluronic acid", "vitamin C", "retinol", "salicylic acid",
              "glycolic acid", "peptides", "squalane", "centella asiatica"],
    "moisturizer": ["ceramides", "peptides", "squalane", "hyaluronic acid", "niacinamide", "retinol"],
    "sunscreen": ["hyaluronic acid", "niacinamide", "ceramides", "squalane", "centella asiatica"],
}
MAKEUP_INGREDIENTS = ["hyaluronic acid", "squalane", "vitamin E"]

NAME_PREFIXES = ["Velvet", "Silk", "Daylight", "Cloud", "Barely There", "Luminous",
                 "Soft Focus", "True", "Weightless", "Glass", "Pure", "Calm",
                 "Bright", "Daily", "Deep", "Gentle", "Hydra", "Clear", "Glow", "Bare"]

# Per category: product count, shade style, number of shades, full-size price
# range (whole dollars), sizes (last one = full size), unit, finishes, SPF choices.
CATEGORIES = {
    "foundation":  dict(code="FDN", n=14, noun="Foundation",  shades="complexion", shade_range=(8, 14), price=(24, 58), sizes=[30],      unit="ml", finishes=["matte", "satin", "dewy"],  spf=[0, 0, 15, 30],    face=True,  skincare=False),
    "concealer":   dict(code="CNC", n=12, noun="Concealer",   shades="complexion", shade_range=(6, 12), price=(16, 34), sizes=[6],       unit="ml", finishes=["matte", "satin"],          spf=[0],               face=True,  skincare=False),
    "lipstick":    dict(code="LIP", n=14, noun="Lip Color",   shades="color",      shade_range=(4, 8),  price=(14, 38), sizes=[3.5],     unit="g",  finishes=["matte", "satin", "gloss"], spf=[0],               face=False, skincare=False),
    "blush":       dict(code="BLS", n=10, noun="Blush",       shades="color",      shade_range=(3, 6),  price=(18, 36), sizes=[4.5],     unit="g",  finishes=["matte", "shimmer"],        spf=[0],               face=True,  skincare=False),
    "mascara":     dict(code="MSC", n=10, noun="Mascara",     shades="mascara",    shade_range=(1, 2),  price=(14, 30), sizes=[8],       unit="ml", finishes=[None],                      spf=[0],               face=False, skincare=False),
    "cleanser":    dict(code="CLN", n=12, noun="Cleanser",    shades=None,         shade_range=None,    price=(12, 34), sizes=[50, 150], unit="ml", finishes=[None],                      spf=[0],               face=True,  skincare=True),
    "toner":       dict(code="TNR", n=10, noun="Toner",       shades=None,         shade_range=None,    price=(14, 32), sizes=[200],     unit="ml", finishes=[None],                      spf=[0],               face=True,  skincare=True),
    "serum":       dict(code="SRM", n=14, noun="Serum",       shades=None,         shade_range=None,    price=(28, 78), sizes=[15, 30],  unit="ml", finishes=[None],                      spf=[0],               face=True,  skincare=True),
    "moisturizer": dict(code="MST", n=14, noun="Moisturizer", shades=None,         shade_range=None,    price=(22, 64), sizes=[15, 50],  unit="ml", finishes=[None],                      spf=[0, 0, 0, 15, 30], face=True,  skincare=True),
    "sunscreen":   dict(code="SUN", n=10, noun="Sunscreen",   shades=None,         shade_range=None,    price=(16, 42), sizes=[50],      unit="ml", finishes=[None],                      spf=[30, 50],          face=True,  skincare=True),
}
SHADE_CATEGORIES = [c for c, s in CATEGORIES.items() if s["shades"]]
SPF_CATEGORIES = ["foundation", "moisturizer", "sunscreen"]
SHADE_KEYS = ("name", "depth", "undertone", "color_family")


def make_stock(rng: random.Random) -> int:
    r = rng.random()
    if r < 0.12:
        return 0                      # out of stock
    if r < 0.20:
        return rng.randint(1, 2)      # low stock, useful for quantity constraints
    return rng.randint(3, 40)


def pick_skin_types(rng: random.Random) -> list[str]:
    chosen = rng.sample(SKIN_TYPES, rng.randint(2, len(SKIN_TYPES)))
    return [s for s in SKIN_TYPES if s in chosen]


def complexion_shades(rng: random.Random, lo: int, hi: int) -> list[dict]:
    # ~30% of complexion products have a limited range with no deep (or tan) shades.
    depths = DEPTHS if rng.random() > 0.3 else DEPTHS[: rng.choice([3, 4])]
    n = max(rng.randint(lo, hi), len(depths))
    per_depth = {d: 0 for d in depths}
    shades = []
    for i in range(n):
        depth = depths[i] if i < len(depths) else rng.choice(depths)
        undertone = rng.choice(list(UNDERTONES))
        k = per_depth[depth]
        per_depth[depth] += 1
        code = f"{DEPTHS.index(depth) + 1}{k + 1:02d}{UNDERTONES[undertone]}"
        names = DEPTH_NAMES[depth]
        shades.append({"code": code, "name": f"{names[k % len(names)]} {code}",
                       "depth": depth, "undertone": undertone, "color_family": None})
    return sorted(shades, key=lambda s: s["code"])


def color_shades(rng: random.Random, lo: int, hi: int) -> list[dict]:
    n = rng.randint(lo, hi)
    families = list(COLOR_FAMILIES)
    used: list[str] = []
    shades: list[dict] = []
    for _ in range(100):
        if len(shades) == n:
            break
        family = rng.choice(families)
        options = [x for x in COLOR_FAMILIES[family] if x not in used]
        if not options:
            continue
        name = rng.choice(options)
        used.append(name)
        shades.append({"code": f"{len(shades) + 1:02d}", "name": name, "depth": None,
                       "undertone": rng.choice(["cool", "neutral", "warm"]), "color_family": family})
    return shades


def mascara_shades(rng: random.Random, lo: int, hi: int) -> list[dict]:
    colors = ["black", "brown"][: rng.randint(lo, hi)]
    return [{"code": c[:3].upper(), "name": c.title(), "depth": None,
             "undertone": None, "color_family": c} for c in colors]


SHADE_MAKERS = {"complexion": complexion_shades, "color": color_shades, "mascara": mascara_shades}


def make_product(rng: random.Random, category: str, spec: dict, index: int,
                 taken_names: list[tuple[str, str]]) -> dict:
    sku = f"{spec['code']}-{index:03d}"
    brand = rng.choice(BRANDS)

    if spec["skincare"]:
        pool = INGREDIENT_POOLS[category]
        key_ingredients = rng.sample(pool, 1 if category == "serum" else rng.randint(1, 3))
        if category == "sunscreen" and rng.random() < 0.5:
            key_ingredients.append("zinc oxide")   # mineral filter
    else:
        key_ingredients = [rng.choice(MAKEUP_INGREDIENTS)] if rng.random() < 0.3 else []

    for _ in range(200):
        prefix = rng.choice(NAME_PREFIXES)
        if category == "serum":
            name = f"{prefix} {key_ingredients[0].title()} Serum"
        else:
            name = f"{prefix} {spec['noun']}"
        if (brand, name) not in taken_names:
            break
    else:
        raise RuntimeError(f"could not find a unique name for {sku}")
    taken_names.append((brand, name))

    full_price = float(rng.randint(*spec["price"]))
    full_size = spec["sizes"][-1]
    variants = []
    if spec["shades"]:
        for shade in SHADE_MAKERS[spec["shades"]](rng, *spec["shade_range"]):
            variants.append({
                "variant_id": f"{sku}-{shade['code']}",
                "shade": {k: shade[k] for k in SHADE_KEYS},
                "size": full_size, "unit": spec["unit"],
                "price": full_price, "stock": make_stock(rng),
            })
    else:
        sizes = [s for s in spec["sizes"][:-1] if rng.random() < 0.5] + [full_size]
        for size in sizes:
            price = full_price if size == full_size else float(int(full_price * size / full_size * 1.35 + 0.5))
            variants.append({
                "variant_id": f"{sku}-{size:g}{spec['unit']}",
                "shade": None,
                "size": size, "unit": spec["unit"],
                "price": price, "stock": make_stock(rng),
            })

    return {
        "sku": sku,
        "name": name,
        "brand": brand,
        "category": category,
        "finish": rng.choice(spec["finishes"]),
        "spf": rng.choice(spec["spf"]),
        "suitable_skin_types": pick_skin_types(rng)
        if spec["skincare"] or category in ("foundation", "concealer") else None,
        "key_ingredients": key_ingredients,
        "fragrance_free": rng.random() < 0.45,
        "vegan": rng.random() < 0.40,
        "cruelty_free": rng.random() < 0.75,
        "non_comedogenic": (rng.random() < 0.5) if spec["face"] else None,
        "alcohol_free": (rng.random() < 0.6) if spec["skincare"] else None,
        "water_resistant": (rng.random() < 0.4) if category in ("mascara", "sunscreen") else False,
        "is_new": rng.random() < 0.12,
        "final_sale": rng.random() < 0.08,
        "max_per_order": rng.choice([1, 2, 3]) if rng.random() < 0.10 else None,
        "variants": variants,
    }


def generate() -> dict:
    rng = random.Random(SEED)
    products: list[dict] = []
    taken: list[tuple[str, str]] = []
    for category, spec in CATEGORIES.items():
        for i in range(1, spec["n"] + 1):
            products.append(make_product(rng, category, spec, i, taken))
    if HAND_CRAFTED.exists():
        products.extend(json.loads(HAND_CRAFTED.read_text(encoding="utf-8")))
    products.sort(key=lambda p: p["sku"])
    return {"currency": CURRENCY, "seed": SEED, "products": products}


def validate(catalog: dict) -> list[str]:
    errors: list[str] = []
    products = catalog["products"]
    if len(products) < 100:
        errors.append(f"only {len(products)} products (need at least 100)")

    for label, items in (
        ("SKU", [p["sku"] for p in products]),
        ("variant_id", [v["variant_id"] for p in products for v in p["variants"]]),
        ("brand+name", [f"{p['brand']} | {p['name']}" for p in products]),
    ):
        dups = [x for x, c in Counter(items).items() if c > 1]
        if dups:
            errors.append(f"duplicate {label}: {dups}")

    for p in products:
        sku, cat, vs = p["sku"], p["category"], p["variants"]
        if not vs:
            errors.append(f"{sku}: no variants")
            continue
        for v in vs:
            if v["price"] <= 0 or round(v["price"], 2) != v["price"]:
                errors.append(f"{v['variant_id']}: bad price {v['price']}")
            if not isinstance(v["stock"], int) or v["stock"] < 0:
                errors.append(f"{v['variant_id']}: bad stock {v['stock']}")
        has_shade = [v["shade"] is not None for v in vs]
        if cat in SHADE_CATEGORIES and not all(has_shade):
            errors.append(f"{sku}: shade category with a variant missing its shade")
        if cat not in SHADE_CATEGORIES and any(has_shade):
            errors.append(f"{sku}: non-shade category with shade variants")
        if cat in SHADE_CATEGORIES and len({v["price"] for v in vs}) > 1:
            errors.append(f"{sku}: shades of one product should share a price")
        by_size = sorted(vs, key=lambda v: v["size"])
        if any(a["price"] >= b["price"] for a, b in zip(by_size, by_size[1:]) if a["size"] < b["size"]):
            errors.append(f"{sku}: a smaller size is not cheaper than a larger one")
        if p["spf"] and cat not in SPF_CATEGORIES:
            errors.append(f"{sku}: SPF on a {cat}")
        if cat == "sunscreen" and p["spf"] < 30:
            errors.append(f"{sku}: sunscreen below SPF 30")

    variants = [v for p in products for v in p["variants"]]
    oos_rate = sum(v["stock"] == 0 for v in variants) / max(len(variants), 1)
    if not 0.05 <= oos_rate <= 0.25:
        errors.append(f"out-of-stock rate {oos_rate:.0%} outside 5-25%")
    return errors


def summarize(catalog: dict) -> None:
    products = catalog["products"]
    variants = [v for p in products for v in p["variants"]]
    print(f"{len(products)} products, {len(variants)} variants")
    for cat, n in Counter(p["category"] for p in products).items():
        print(f"  {cat:<12} {n}")
    oos = sum(v["stock"] == 0 for v in variants)
    print(f"out-of-stock variants: {oos} ({oos / len(variants):.0%})")
    for flag in ("fragrance_free", "vegan", "cruelty_free", "is_new", "final_sale"):
        print(f"  {flag:<15} {sum(1 for p in products if p[flag])} products")
    limited = sum(
        1 for p in products
        if p["category"] in ("foundation", "concealer")
        and not any(v["shade"]["depth"] == "deep" for v in p["variants"])
    )
    print(f"complexion products with no deep shades: {limited}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic beauty catalog generator")
    parser.add_argument("--check", action="store_true",
                        help="validate the existing catalog.json without regenerating it")
    args = parser.parse_args()

    catalog = json.loads(OUT.read_text(encoding="utf-8")) if args.check else generate()
    errors = validate(catalog)
    if errors:
        print("INVALID catalog:")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    if not args.check:
        OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summarize(catalog)


if __name__ == "__main__":
    main()
