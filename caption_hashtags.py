"""Optional Malaysian-Malay promotional captions and category-aware hashtags for Klippo."""
import random
import re
import unicodedata

CATEGORY_TERMS = {
    "fashion": ["fesyen", "bajufesyen", "ootd", "gayaharini", "gayawanita", "gayapria", "outfitmalaysia", "fashionmalaysia"],
    "bag": ["beg", "begwanita", "begtangan", "begseharian", "begtravel", "begkerja", "begcantik"],
    "hijab": ["tudung", "hijab", "tudungcantik", "gayatudung", "tudungmalaysia", "hijabstyle"],
    "kids_shoes": ["kasutkanakkanak", "kasutbudak", "kasutcomel", "gayakanakkanak", "baranganak"],
    "kids_clothing": ["bajukanakkanak", "pakaianbudak", "gayakanakkanak", "bajukomel", "fesyenkanakkanak"],
    "shoes": ["kasut", "kasutwanita", "kasutlelaki", "kasutselesa", "kasutkerja", "kasutcantik"],
    "beauty": ["kecantikan", "rutinpenjagaan", "beautymalaysia", "skincare", "makeupmalaysia", "selfcare"],
    "food": ["makanan", "makanansedap", "jommak an".replace(" ", ""), "kudapan", "foodmalaysia", "jommak an".replace(" ", "")],
    "gadget": ["gadget", "aksesorigajet", "teknologimalaysia", "gadgetmalaysia", "gajetharian"],
    "equipment": ["peralatan", "alatberguna", "peralatanpraktikal", "barangberguna", "alatanrumah"],
    "home": ["dekorasirumah", "rumahkemas", "baranganrumah", "hiasanrumah", "rumahcantik", "homefinds"],
    "accessory": ["aksesori", "aksesoricantik", "aksesorigaya", "aksesoriwanita", "aksesori harian".replace(" ", "")],
    "toy": ["mainan", "mainankanak", "aktiviti anak".replace(" ", ""), "mainanpendidikan", "ideakanak"],
    "book_stationery": ["alatulis", "bukumenarik", "alatuliscomel", "belajardirumah", "stationerymalaysia"],
    "sports": ["sukan", "gayahidupaktif", "fitnessmalaysia", "alatan sukan".replace(" ", ""), "aktifsetiaphari"],
    "pet": ["haiwanpeliharaan", "kucingcomel", "anjingcomel", "barangpet", "petmalaysia"],
    "automotive": ["aksesorikereta", "penjagaankereta", "autogear", "keretamalaysia", "barangkereta"],
    "baby": ["baranganbayi", "keperluanbayi", "bayimalaysia", "ibudanbayi", "barangbayi"],
    "travel": ["travelmalaysia", "barangtravel", "tipstravel", "travelessentials", "cuticutimalaysia"],
    "office": ["keperluanpejabat", "mejakerja", "organisasipejabat", "kerjadarirumah", "officefinds"],
    "other": ["produkmenarik", "barangberguna", "jumpaanyangmenarik", "pilihanharian", "produkpilihan"],
}
INTENT_TERMS = [
    "pilihanbijak", "barangberguna", "jumpaanmenarik", "wajibcuba", "ideabeli",
    "inspirasi harian".replace(" ", ""), "pilihanpengguna", "produkpilihan",
    "barangviral", "caribarang", "shoppingmalaysia", "belionline", "promomalaysia",
    "reviewproduk", "produkbest", "barangpraktikal", "pilihanyangbaik",
    "cadanganproduk", "produkharian", "gayahidup", "idea hadiah".replace(" ", ""),
    "hadiahmenarik", "kegunaanharian", "pilihananda", "barangpilihan", "tiktokshop",
    "shopeemalaysia", "racunbelanja", "shoppingfinds", "malaysiadeals",
    "jumpaanyangbest", "produktempatan", "barangberbaloi", "pilihanmenarik",
]
FORMAT_TERMS = [
    "review", "unboxing", "demoproduk", "detailproduk", "productfinds",
    "shoppinghaul", "cadangan", "pilihan", "inspirasi", "promosi",
    "bestfinds", "dailyfinds", "viralfinds", "racunbelanja", "barangbaru",
    "ideabelanja", "productreview", "produkviral", "fypmalaysia", "fyp",
    "tiktokmalaysia", "shopeefinds", "affiliate", "affiliate malaysia".replace(" ", ""),
]
HOOKS = [
    "Sedang cari pilihan yang sesuai untuk kegunaan harian? Jom tengok produk ini.",
    "Kadang-kadang, pilihan yang praktikal boleh memudahkan rutin harian.",
    "Kalau anda sedang membandingkan pilihan, produk ini boleh masuk dalam senarai anda.",
    "Nampak menarik? Jom lihat butiran produk ini dengan lebih dekat.",
    "Satu lagi pilihan untuk anda pertimbangkan sebelum membeli.",
    "Mencari idea baharu? Ini produk yang boleh anda semak mengikut keperluan sendiri.",
]
CTAS = [
    "Tekan pautan produk untuk semak butiran, pilihan dan harga terkini.",
    "Klik pautan produk untuk lihat maklumat lanjut sebelum membuat pilihan.",
    "Semak variasi dan maklumat produk di pautan yang disediakan.",
    "Kalau sesuai dengan keperluan anda, lihat butiran produk melalui pautan.",
]
def _slug(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", value)

def _category_key(value):
    value = str(value or "").lower().strip()
    aliases = {
        "hijab": "hijab", "tudung": "hijab", "fashion": "fashion", "fesyen": "fashion",
        "clothing": "fashion", "pakaian": "fashion", "bag": "bag", "beg": "bag",
        "shoes": "shoes", "kasut": "shoes", "beauty": "beauty", "kecantikan": "beauty",
        "food": "food", "makanan": "food", "gadget": "gadget", "electronics": "gadget",
        "home": "home", "rumah": "home", "accessory": "accessory", "aksesori": "accessory",
        "toy": "toy", "mainan": "toy", "book_stationery": "book_stationery",
        "stationery": "book_stationery", "sports": "sports", "pet": "pet",
        "automotive": "automotive", "baby": "baby", "travel": "travel", "office": "office",
        "equipment": "equipment",
    }
    # Resolve child-specific subcategories before broad parent categories.
    child_terms = ("kanak", "kanakkanak", "budak", "kids", "children", "child", "toddler", "baby")
    if any(term in value for term in child_terms):
        if any(term in value for term in ("shoe", "kasut", "footwear")):
            return "kids_shoes"
        if any(term in value for term in ("cloth", "clothing", "pakaian", "baju", "dress", "apparel")):
            return "kids_clothing"
    for needle, key in aliases.items():
        if needle in value:
            return key
    return "other"

def hashtag_library_size():
    """Return the number of unique, valid tags available from the category-aware generator."""
    tags = set()
    for category, roots in CATEGORY_TERMS.items():
        for root in roots:
            for intent in INTENT_TERMS:
                tags.add("#" + _slug(root) + _slug(intent))
                for fmt in FORMAT_TERMS:
                    tags.add("#" + _slug(root) + _slug(fmt))
    return len(tags)

def _relevant_hashtags(category, product_name, subcategory, limit=12):
    key = _category_key(category + " " + subcategory)
    roots = CATEGORY_TERMS.get(key, CATEGORY_TERMS["other"])
    product_slug = _slug(product_name)
    sub_slug = _slug(subcategory)
    candidates = []
    for tag in roots:
        candidates.append("#" + _slug(tag))
    if sub_slug:
        candidates.extend(["#" + sub_slug, "#" + sub_slug + "Malaysia"])
    if product_slug and len(product_slug) >= 3:
        candidates.append("#" + product_slug[:35])
    candidates.extend("#" + _slug(term) for term in INTENT_TERMS)
    candidates.extend("#" + _slug(term) for term in FORMAT_TERMS)
    candidates.extend("#" + _slug(root) + _slug(term) for root in roots for term in INTENT_TERMS)
    # Keep category-specific tags first, then a small set of general discovery tags.
    unique = []
    seen = set()
    for tag in candidates:
        if tag.lower() not in seen and 2 <= len(tag) <= 65:
            unique.append(tag)
            seen.add(tag.lower())
    # Deterministic rotation per product avoids identical tag blocks across products.
    seed = sum(ord(ch) for ch in (product_name + subcategory + key))
    specific = unique[:max(4, min(7, len(roots)))]
    general = unique[max(4, min(7, len(roots))):]
    if general:
        offset = seed % len(general)
        general = general[offset:] + general[:offset]
    return (specific + general)[:limit]

def generate_caption(product_name, category="other", subcategory="", platform="Shopee"):
    """Return only a short product caption and relevant hashtags, without UI instructions."""
    name = str(product_name or "").strip()[:180]
    sub = str(subcategory or "").strip()[:80]
    if not name:
        name = "produk pilihan"
    key = _category_key(str(category) + " " + sub + " " + name)
    # Short, category-aware Malaysian Malay copy; avoid unsupported product claims.
    captions = {
        "kids_shoes": f"Lengkapkan gaya si kecil dengan {name} 👟",
        "kids_clothing": f"Pilihan comel untuk gaya si kecil: {name} 🧸",
        "shoes": f"Sedang mencari kasut? Jom lihat {name} 👟",
        "fashion": f"Serlahkan gaya anda dengan {name} ✨",
        "bag": f"Lengkapkan gaya harian anda dengan {name} 👜",
        "hijab": f"Idea gaya tudung untuk dipadankan dengan {name} ✨",
        "beauty": f"Tambahkan {name} dalam senarai pilihan kecantikan anda ✨",
        "food": f"Teringin mencuba sesuatu? Lihat {name} 🍽️",
        "gadget": f"Sedang mencari gajet? Kenali {name} 📱",
        "home": f"Ilham untuk ruang kediaman anda: {name} 🏡",
        "toy": f"Idea untuk waktu bermain si kecil: {name} 🧸",
        "baby": f"Pilihan untuk melengkapi keperluan si kecil: {name} 🍼",
        "other": f"Jom lihat {name} dan semak sama ada sesuai dengan keperluan anda ✨",
    }
    caption = captions.get(key, f"Jom lihat {name} dan semak sama ada sesuai dengan keperluan anda ✨")
    hashtags = _relevant_hashtags(key, name, sub)
    return caption + "\n\n" + " ".join(hashtags)

def get_caption(product_name, category="other", subcategory="", platform="Shopee"):
    return generate_caption(product_name, category, subcategory, platform)
