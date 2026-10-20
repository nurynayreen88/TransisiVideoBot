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
    child_terms = ("kanak", "kanakkanak", "budak", "kids", "children", "child", "toddler")
    if any(term in value for term in child_terms):
        if any(term in value for term in ("shoe", "kasut", "footwear")):
            return "kids_shoes"
        if "fashion_kids" in value or any(term in value for term in ("cloth", "clothing", "pakaian", "baju", "dress", "apparel", "shirt", "tee", "skort", "shorts", "romper", "kidswear")):
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
    """Return a useful Malaysian Malay caption and relevant hashtags only."""
    name = str(product_name or "").strip()[:180] or "produk pilihan"
    sub = str(subcategory or "").strip()[:80]
    key = _category_key(str(category) + " " + sub + " " + name)

    captions = {
        "kids_shoes": (
            f"Sedang cari kasut untuk si kecil? 👟\n"
            f"{name} boleh jadi pilihan untuk melengkapkan gaya anak ketika keluar bersama keluarga atau menjalani aktiviti harian. "
            ""
        ),
        "kids_clothing": (
            f"Nak gayakan si kecil dengan penampilan yang comel? 🧸\n"
            f"{name} boleh dipertimbangkan untuk melengkapkan koleksi pakaian anak. "
            ""
        ),
        "shoes": (
            f"Sedang mencari kasut untuk melengkapkan gaya harian? 👟\n"
            f"{name} boleh anda pertimbangkan mengikut gaya dan kegunaan yang diperlukan. "
            ""
        ),
        "fashion": (
            f"Sedang mencari idea untuk gaya seterusnya? ✨\n"
            f"{name} boleh dijadikan pilihan untuk dipadankan dengan koleksi pakaian anda. "
            ""
        ),
        "bag": (
            f"Mencari beg untuk melengkapi rutin harian? 👜\n"
            f"{name} boleh anda pertimbangkan mengikut gaya dan barang yang biasa dibawa. "
            ""
        ),
        "hijab": (
            f"Jom cari inspirasi gaya tudung yang sesuai dengan anda ✨\n"
            f"{name} boleh dipadankan mengikut pilihan gaya dan warna kegemaran. "
            ""
        ),
        "beauty": (
            f"Sedang menambah pilihan dalam rutin kecantikan? ✨\n"
            f"Lihat {name} dan teliti maklumat produk sebelum membuat pilihan. "
            ""
        ),
        "food": (
            f"Nampak menarik untuk dicuba? 🍽️\n"
            f"{name} boleh anda semak jika sedang mencari pilihan makanan atau kudapan. "
            ""
        ),
        "gadget": (
            f"Sedang mencari gajet atau aksesori teknologi? 📱\n"
            f"{name} boleh anda pertimbangkan berdasarkan kegunaan yang diperlukan. "
            ""
        ),
        "home": (
            f"Ada idea untuk menceriakan ruang rumah? 🏡\n"
            f"{name} boleh anda lihat sebagai salah satu pilihan untuk kediaman. "
            ""
        ),
        "toy": (
            f"Sedang mencari idea untuk waktu bermain si kecil? 🧸\n"
            f"{name} boleh anda pertimbangkan mengikut minat dan peringkat umur anak. "
            ""
        ),
        "baby": (
            f"Sedang menyenaraikan keperluan si kecil? 🍼\n"
            f"{name} boleh anda semak sebagai salah satu pilihan. "
            ""
        ),
        "other": (
            f"Jom lihat produk ini dengan lebih dekat ✨\n"
            f"{name} mungkin sesuai untuk dipertimbangkan berdasarkan keperluan anda. "
            ""
        ),
    }
    caption = captions.get(key, captions["other"])
    hashtags = _relevant_hashtags(key, name, sub)
    return caption + "\n\n" + " ".join(hashtags)

def get_caption(product_name, category="other", subcategory="", platform="Shopee"):
    return generate_caption(product_name, category, subcategory, platform)
