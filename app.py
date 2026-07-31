import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import random
import time
import json
from urllib.parse import urljoin, urlparse
import pandas as pd
from io import BytesIO, StringIO
import zipfile
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFilter

# ============================================================
# SESSION STATE INIT
# ============================================================
if 'is_ready' not in st.session_state:
    st.session_state.is_ready = False
if 'csv_data' not in st.session_state:
    st.session_state.csv_data = None
if 'zip_data' not in st.session_state:
    st.session_state.zip_data = None
if 'df_preview' not in st.session_state:
    st.session_state.df_preview = None
if 'failed_urls' not in st.session_state:
    st.session_state.failed_urls = []
if 'total_rows' not in st.session_state:
    st.session_state.total_rows = 0
if 'has_zip' not in st.session_state:
    st.session_state.has_zip = False

# Batch Processing State
if 'batch_index' not in st.session_state:
    st.session_state.batch_index = 0
if 'all_final_rows' not in st.session_state:
    st.session_state.all_final_rows = []
if 'all_image_data' not in st.session_state:
    st.session_state.all_image_data = {}
if 'all_failed' not in st.session_state:
    st.session_state.all_failed = []
if 'total_urls' not in st.session_state:
    st.session_state.total_urls = 0
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False
if 'all_urls' not in st.session_state:
    st.session_state.all_urls = []

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Universal E-commerce Extractor + Branding Studio", page_icon="🛒")
st.title("🛒 UNIVERSAL E-COMMERCE CSV + BRANDING STUDIO V4.0")
st.markdown("**Works with WooCommerce, Shopify, Magento, custom stores & most other platforms** — fetches full gallery images (data-src, lazy-src, zoom, srcset) and writes a Shopify-format import CSV.")
st.caption("⚠️ Note: sites built as a heavy JavaScript app (e.g. many Wix stores, some custom React storefronts) may only expose meta-tag/JSON-LD data to a static scraper — full gallery scraping works best on WooCommerce, Shopify, Magento, and most server-rendered custom sites.")

st.components.v1.html("""
<script>
    setInterval(function() {
        console.log("🛡️ Keep-Alive Ping");
    }, 2000);
</script>
""", height=0)

# ============================================================
# BRANDING STUDIO UI
# ============================================================
st.subheader("🎨 Branding Studio (Optional)")
with st.expander("⚙️ Configure Image Branding", expanded=True):
    col_a, col_b = st.columns(2)
    with col_a:
        st.checkbox("🖼️ Add Corner Logo (Top-Left)", key="enable_logo", value=False)
        if st.session_state.get("enable_logo", False):
            st.file_uploader("Upload Corner Logo", type=['png', 'jpg', 'jpeg'], key="logo_uploader")
        
        st.checkbox("🔤 Add Center Watermark", key="enable_watermark", value=False)
        if st.session_state.get("enable_watermark", False):
            st.radio("Watermark Type", ["Text", "Image Logo"], key="watermark_type", horizontal=True)
            st.slider("Watermark Size (%)", 5, 50, 15, key="watermark_size")
            st.slider("Watermark Opacity (%)", 10, 80, 20, key="watermark_opacity")
            if st.session_state.get("watermark_type") == "Text":
                st.text_input("Watermark Text", "YourBrand.com", key="watermark_text")
            else:
                st.file_uploader("Upload Watermark Logo (PNG)", type=['png', 'jpg', 'jpeg'], key="watermark_logo_uploader")
        
        st.checkbox("🌑 Drop Shadow", key="enable_shadow", value=False)
        st.checkbox("🔄 Rounded Corners", key="enable_rounded", value=False)
        st.checkbox("🔄 Mirror Flip (Anti-Duplicate)", key="enable_flip", value=True)

    with col_b:
        st.checkbox("🖼️ Add Border", key="enable_border", value=False)
        if st.session_state.get("enable_border", False):
            st.color_picker("Border Color", "#000000", key="border_color")
        
        st.checkbox("🌈 Add Gradient Frame", key="enable_gradient", value=False)
        if st.session_state.get("enable_gradient", False):
            st.color_picker("Gradient Color 1", "#FF5733", key="grad_color_1")
            st.color_picker("Gradient Color 2", "#33FF57", key="grad_color_2")
        
        st.checkbox("✨ Brightness/Contrast Tweak", key="enable_enhance", value=True)

# ============================================================
# DESCRIPTION & SEO SETTINGS (100% local — no API key needed)
# ============================================================
st.subheader("📝 Description & SEO Settings")
with st.expander("⚙️ Configure Product Descriptions", expanded=True):
    col_ai1, col_ai2 = st.columns(2)
    with col_ai1:
        st.text_area("🏪 Store / Niche Context (optional)", key="ai_store_context",
                      placeholder="e.g. Premium leather jackets store, target audience: men & women 20-45, focus on quality + comfort",
                      height=100,
                      help="Optional — mention your niche and it'll be woven into the generated wording.")
    with col_ai2:
        st.slider("🖼️ Max Gallery Images per Product", 3, 20, 10, key="max_gallery_images",
                   help="Ab sirf 5 tak limited nahi — gallery, zoom aur lazy-load images sab combine karke ye limit tak fetch honge.")
    st.caption("💡 Descriptions, SEO title aur meta description sab locally generate hote hain — koi API key ya internet-based AI call nahi lagti. Har product ke liye templates aur phrase-pools se unique, SEO-optimized, sales-focused copy banti hai.")

# ============================================================
# MAIN INPUTS
# ============================================================
st.subheader("📥 Input & Controls")
edit_images = st.checkbox("🖌️ Enable Image Editing (Master Switch)", value=True)

col_inp1, col_inp2 = st.columns([3, 1])
with col_inp1:
    urls_input = st.text_area("🔗 Paste Product URLs (One per line):", height=150)
with col_inp2:
    base_url = st.text_input("🌐 Base URL:", placeholder="https://domain.com/wp-content/uploads/")

BATCH_SIZE = 30

# ============================================================
# HELPER: GET BRANDING CONFIG
# ============================================================
def get_branding_config():
    corner_logo_bytes = None
    if st.session_state.get("enable_logo", False):
        uploaded = st.session_state.get("logo_uploader", None)
        if uploaded is not None:
            corner_logo_bytes = uploaded.getvalue()
    
    watermark_logo_bytes = None
    if st.session_state.get("enable_watermark", False) and st.session_state.get("watermark_type") == "Image Logo":
        uploaded = st.session_state.get("watermark_logo_uploader", None)
        if uploaded is not None:
            watermark_logo_bytes = uploaded.getvalue()
    
    return {
        'edit_images': edit_images,
        'enable_flip': st.session_state.get("enable_flip", True),
        'enable_enhance': st.session_state.get("enable_enhance", True),
        'enable_logo': st.session_state.get("enable_logo", False),
        'corner_logo_bytes': corner_logo_bytes,
        'enable_watermark': st.session_state.get("enable_watermark", False),
        'watermark_type': st.session_state.get("watermark_type", "Text"),
        'watermark_text': st.session_state.get("watermark_text", "YourBrand.com"),
        'watermark_logo_bytes': watermark_logo_bytes,
        'watermark_size': st.session_state.get("watermark_size", 15),
        'watermark_opacity': st.session_state.get("watermark_opacity", 20),
        'enable_border': st.session_state.get("enable_border", False),
        'border_color': st.session_state.get("border_color", "#000000"),
        'enable_gradient': st.session_state.get("enable_gradient", False),
        'grad_color_1': st.session_state.get("grad_color_1", "#FF5733"),
        'grad_color_2': st.session_state.get("grad_color_2", "#33FF57"),
        'enable_shadow': st.session_state.get("enable_shadow", False),
        'enable_rounded': st.session_state.get("enable_rounded", False),
        'max_gallery_images': st.session_state.get("max_gallery_images", 10),
        'store_context': st.session_state.get("ai_store_context", "")
    }

# ============================================================
# REWRITER + EXTRACTORS (100% local — no API key or internet AI call needed)
# ============================================================
class SmartRewriter:
    def __init__(self):
        self.synonyms = {
            'great': 'exceptional', 'good': 'superior', 'best': 'top-tier',
            'durable': 'long-lasting', 'strong': 'robust', 'quality': 'premium',
            'amazing': 'remarkable', 'perfect': 'ideal', 'easy': 'effortless',
            'simple': 'straightforward', 'modern': 'contemporary', 'classic': 'timeless',
            'beautiful': 'exquisite', 'nice': 'fantastic', 'cool': 'stylish',
            'high-quality': 'superior-grade', 'comfortable': 'ultra-comfortable',
            'soft': 'plush', 'lightweight': 'featherlight', 'stylish': 'fashion-forward',
            'reliable': 'dependable', 'affordable': 'budget-friendly', 'unique': 'one-of-a-kind'
        }
        self.protected = {
            'leather', 'jacket', 'biker', 'motorcycle', 'hide', 'zip', 'pocket',
            'collar', 'sleeve', 'fit', 'style', 'men', 'women', 'unisex', 'black',
            'brown', 'tan', 'maroon', 'red', 'blue', 'green', 'grey', 'white',
            'divi', 'engine', 'woocommerce', 'wordpress', 'hoodie', 'shirt', 'tee'
        }
        self.stopwords = {
            'the', 'a', 'an', 'for', 'with', 'and', 'of', 'in', 'to', 'is', 'are',
            'this', 'that', 'your', 'our', 'from', 'on', 'by', 'or', 'it', 'its',
            'be', 'as', 'at', 'new', 'pcs', 'set'
        }
        self.hooks = [
            "Meet the {title} — ", "Say hello to the {title}, ", "Introducing the {title}, ",
            "Looking for something special? The {title} ", "Here's a piece you'll reach for again and again: the {title}, ",
            "The {title} is here, and ", "Get to know the {title} — "
        ]
        self.benefit_templates = [
            "designed with your comfort in mind from the very first wear",
            "built to handle everyday life without losing its shape or charm",
            "crafted with an eye for both style and lasting quality",
            "made to feel just as good as it looks",
            "put together with genuine care for fit, feel, and finish",
            "a favorite for anyone who wants quality without the fuss",
        ]
        self.feature_pool = [
            "Premium materials chosen for comfort and long-lasting wear",
            "Thoughtful construction that holds its shape use after use",
            "A comfortable, true-to-size fit made for all-day wear",
            "Versatile enough to dress up or down for any occasion",
            "Carefully finished details for a polished, put-together look",
            "Easy to care for so it stays looking great with minimal effort",
            "A timeless design that won't feel out of place next season",
            "Reinforced stitching and finishing where it matters most",
            "Breathable, comfortable feel that fits real, everyday life",
            "Color and finish that stay true wash after wash",
        ]
        self.care_cta_pool = [
            "If you've been searching for something reliable and good-looking, this is worth adding to your cart.",
            "We think you'll love how it feels the moment you try it — go ahead and make it yours.",
            "A simple, no-guesswork way to upgrade your everyday look.",
            "Treat yourself to something that's built to last and easy to love.",
            "Add it to your collection today — we're confident it'll become a regular favorite.",
            "Still deciding? Our team is always happy to help you pick the right fit before you order.",
        ]

    # ---------- shared helpers ----------
    def _clean_text(self, text):
        text = re.sub(r'<[^<]+?>', ' ', text or '')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _synonym_pass(self, text):
        sentences = re.split(r'(?<=[.!?]) +', text)
        new_sentences = []
        for sent in sentences:
            words = sent.split()
            new_words = []
            for word in words:
                lower_word = word.lower().strip('.,!?')
                if lower_word in self.synonyms and lower_word not in self.protected:
                    replacement = self.synonyms[lower_word]
                    if word[:1].isupper():
                        replacement = replacement.capitalize()
                    if word.endswith('.'):
                        replacement += '.'
                    new_words.append(replacement)
                else:
                    new_words.append(word)
            new_sentences.append(' '.join(new_words))
        return ' '.join(new_sentences).strip()

    def _fit_length(self, text, min_len, max_len, filler_phrases, max_fillers=2):
        text = text.strip()
        if len(text) > max_len:
            trimmed = text[:max_len].rsplit(' ', 1)[0]
            return trimmed if trimmed else text[:max_len]
        fillers = list(filler_phrases)
        random.shuffle(fillers)
        used = 0
        for filler in fillers:
            if len(text) >= min_len or used >= max_fillers:
                break
            sep = '' if text.endswith(('.', '!', '?')) else ' '
            candidate = f"{text}{sep}{filler}"
            if len(candidate) <= max_len:
                text = candidate
                used += 1
        return text

    # ---------- backward-compatible simple rewrite (kept for internal reuse) ----------
    def enhance_description(self, text, title=""):
        if not text or len(text) < 5:
            return f"Discover the perfect blend of style and durability with this premium {title}. Crafted for the modern individual, it offers unmatched comfort and timeless appeal."
        return self._synonym_pass(text)

    # ---------- main entry point: fully local, detailed, SEO-ready content ----------
    def generate_seo_content(self, title, raw_desc, category=None, store_context=None):
        clean_source = self._clean_text(raw_desc)
        source_is_useful = len(clean_source) > 15 and clean_source.lower() != title.lower()
        rewritten_source = self._synonym_pass(clean_source) if source_is_useful else ''

        hook = random.choice(self.hooks).format(title=title)
        benefit = random.choice(self.benefit_templates)
        niche_line = f" Perfect for shoppers who care about {store_context.strip().rstrip('.')}." if store_context else ""
        intro = f"{hook}{benefit}.{niche_line}"

        para2 = ''
        if rewritten_source:
            sentences = re.split(r'(?<=[.!?]) +', rewritten_source)
            para2 = ' '.join(sentences[:2]).strip()

        features = random.sample(self.feature_pool, k=min(4, len(self.feature_pool)))
        if category:
            features.append(f"Thoughtfully categorized under {category.split('>')[-1].strip()} so it's easy to find and pair with what you already own")
        feature_html = ''.join(f"<li>{f}</li>" for f in features)

        cta = random.choice(self.care_cta_pool)

        parts = [f"<p>{intro}</p>"]
        if para2:
            parts.append(f"<p>{para2}</p>")
        parts.append(f"<ul>{feature_html}</ul>")
        parts.append(f"<p>{cta}</p>")
        description_html = ''.join(parts)

        seo_title = self._fit_length(
            f"{title} - Premium Quality", 55, 60,
            ["Shop Now", "Buy Today", "New Arrival", "Top Pick", "Order Now", "Shop"],
            max_fillers=1
        )
        plain_intro = re.sub(r'<[^<]+?>', ' ', intro)
        plain_intro = re.sub(r'\s+', ' ', plain_intro).strip()
        seo_description = self._fit_length(
            f"{plain_intro} Shop the {title} today.", 155, 160,
            ["Order now.", "Free shipping available.", "Limited stock.", "Shop the collection.", "See more details inside."]
        )

        return {
            'description_html': description_html,
            'seo_title': seo_title,
            'seo_description': seo_description
        }

def safe_get_offer_price(offers):
    if isinstance(offers, dict): return offers.get('price', '')
    elif isinstance(offers, list) and len(offers) > 0:
        first = offers[0]
        if isinstance(first, dict): return first.get('price', '')
    return ''

def safe_get_sku(sku_data):
    if isinstance(sku_data, str): return sku_data
    elif isinstance(sku_data, list) and len(sku_data) > 0: return str(sku_data[0])
    return ''

def safe_get_brand(brand_data):
    """JSON-LD 'brand' can be a plain string or a schema.org Brand/Organization object."""
    if isinstance(brand_data, str):
        return brand_data
    if isinstance(brand_data, dict):
        return brand_data.get('name', '')
    if isinstance(brand_data, list) and brand_data:
        return safe_get_brand(brand_data[0])
    return ''

def format_category(soup, default="Apparel & Accessories > Clothing > Tops"):
    """Covers WooCommerce (.woocommerce-breadcrumb), Magento (.breadcrumbs),
    schema.org BreadcrumbList, and generic nav[aria-label=breadcrumb]/ol.breadcrumb markup."""
    # 1. schema.org BreadcrumbList (works across almost every modern platform incl. Wix/Magento)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            candidates = data if isinstance(data, list) else [data]
            for entry in candidates:
                if isinstance(entry, dict) and entry.get('@type') == 'BreadcrumbList':
                    items = sorted(entry.get('itemListElement', []), key=lambda x: x.get('position', 0))
                    names = [it.get('name') or (it.get('item', {}).get('name') if isinstance(it.get('item'), dict) else None)
                             for it in items]
                    names = [n for n in names if n]
                    if len(names) > 1:
                        return ' > '.join(names[1:])
        except Exception:
            pass

    # 2. Common HTML breadcrumb containers (ul/nav/ol, class or aria-label based)
    bread = (soup.find(['ul', 'nav', 'ol'], {'class': re.compile(r'breadcrumb', re.I)})
             or soup.find(attrs={'aria-label': re.compile(r'breadcrumb', re.I)}))
    if bread:
        links = bread.find_all('a')
        if len(links) > 1:
            categories = [link.get_text(strip=True) for link in links[1:]]
            if categories:
                return ' > '.join(categories)
    return default

def generate_handle(title):
    handle = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    if len(handle) > 200:
        handle = handle[:200].rsplit('-', 1)[0]
    return handle

def extract_title(soup, product_data, url):
    """Platform-agnostic title extraction: JSON-LD -> itemprop -> h1 (WooCommerce/Magento
    both use h1.product_title / .page-title) -> og:title -> <title> -> URL slug."""
    title = product_data.get('name')
    if not title:
        itemprop = soup.find(attrs={'itemprop': 'name'})
        if itemprop:
            title = itemprop.get_text(strip=True)
    if not title and soup.find('h1'):
        title = soup.find('h1').get_text(strip=True)
    if not title:
        og_title = soup.find('meta', property='og:title')
        title = og_title.get('content') if og_title else None
    if not title and soup.find('title'):
        title = soup.find('title').get_text(strip=True)
    if not title:
        title = url.split('/')[-1].replace('-', ' ').replace('_', ' ')
    return title.strip()

def extract_raw_description(soup, product_data):
    """Platform-agnostic description text used as source facts for the AI/rewriter.
    Covers WooCommerce short description, Magento product description, generic
    itemprop=description, and standard meta tags."""
    raw_desc = product_data.get('description') or ''
    if not raw_desc:
        itemprop = soup.find(attrs={'itemprop': 'description'})
        if itemprop:
            raw_desc = itemprop.get_text(strip=True)
    if not raw_desc:
        woo = soup.find('div', {'class': re.compile(r'woocommerce-product-details__short-description')})
        if woo:
            raw_desc = woo.get_text(' ', strip=True)
    if not raw_desc:
        magento = soup.find('div', {'class': re.compile(r'product.*description|description.*value', re.I)})
        if magento:
            raw_desc = magento.get_text(' ', strip=True)
    if not raw_desc:
        desc_meta = soup.find('meta', attrs={'name': 'description'})
        raw_desc = desc_meta.get('content') if desc_meta else ''
    if not raw_desc or len(raw_desc) < 20:
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            raw_desc = og_desc.get('content')
    return raw_desc

def extract_price(soup, product_data):
    price = safe_get_offer_price(product_data.get('offers'))
    if price:
        return price
    # itemprop / meta based price (schema.org + Open Graph product price, common across platforms)
    price_tag = (soup.find(attrs={'itemprop': 'price'})
                 or soup.find('meta', property='product:price:amount')
                 or soup.find('meta', attrs={'property': 'og:price:amount'}))
    if price_tag:
        val = price_tag.get('content') or price_tag.get_text(strip=True)
        match = re.search(r'[\d,]+\.?\d*', val or '')
        if match:
            return match.group()
    # Class-based fallback: covers WooCommerce (.price .amount), Magento
    # (.price-wrapper, .special-price), and most custom theme naming conventions.
    price_span = soup.find(['span', 'div', 'ins'], {'class': re.compile(
        r'price|amount|sale-price|regular-price|product-price|current-price', re.I)})
    if price_span:
        match = re.search(r'[\d,]+\.?\d*', price_span.get_text())
        if match:
            return match.group()
    return '0'

def extract_sku(soup, product_data):
    sku_raw = safe_get_sku(product_data.get('sku'))
    if sku_raw:
        return sku_raw
    itemprop = soup.find(attrs={'itemprop': 'sku'})
    if itemprop:
        return itemprop.get_text(strip=True) or itemprop.get('content', '')
    # WooCommerce: <span class="sku">..</span>, Magento: [data-product-sku], generic .sku/.model/.id
    sku_span = (soup.find(attrs={'data-product-sku': True})
                or soup.find(['span', 'div'], {'class': re.compile(r'\bsku\b|model|product-id', re.I)}))
    if sku_span:
        text = sku_span.get('data-product-sku') or sku_span.get_text(strip=True)
        if text:
            return text
    return f"OLD-{random.randint(1000,9999)}"

def extract_vendor(soup, product_data, default="Imported Vendor"):
    brand = safe_get_brand(product_data.get('brand'))
    if brand:
        return brand
    itemprop = soup.find(attrs={'itemprop': 'brand'})
    if itemprop:
        text = itemprop.get_text(strip=True)
        if text:
            return text
    meta_brand = soup.find('meta', property='product:brand') or soup.find('meta', attrs={'name': 'author'})
    if meta_brand and meta_brand.get('content'):
        return meta_brand.get('content')
    return default

# ============================================================
# GALLERY IMAGE HELPERS (fixes "gallery images missing")
# ============================================================
def strip_size_suffix(url):
    """Convert thumbnail/resized URLs (e.g. product_300x300.jpg, product_600x.jpg@2x)
    into the full-resolution original where possible."""
    try:
        clean = url.split('?')[0]
        query = url[len(clean):]
        clean = re.sub(r'(_\d{2,4}x\d{0,4})(@\d+x)?(\.[a-zA-Z]{3,4})$', r'\3', clean)
        clean = re.sub(r'(_(?:small|medium|large|thumb|thumbnail|grande|compact))(\.[a-zA-Z]{3,4})$', r'\2', clean, flags=re.I)
        return clean + query
    except Exception:
        return url

def try_get_shopify_json_images(url, session, headers):
    """Most themes expose the full product JSON (with every gallery image, no cap)
    at <product-url>.json — this is the most reliable source when available."""
    urls = []
    try:
        clean_url = url.split('?')[0].rstrip('/')
        if clean_url.endswith('.json'):
            json_url = clean_url
        else:
            json_url = clean_url + '.json'
        r = session.get(json_url, headers=headers, timeout=15)
        if r.status_code == 200 and 'json' in r.headers.get('Content-Type', ''):
            data = r.json()
            product = data.get('product', {})
            for img in product.get('images', []) or []:
                src = img.get('src')
                if src:
                    urls.append(src)
    except Exception:
        pass
    return urls

def extract_gallery_images_html(soup, base_url_domain):
    """Pull every candidate image from <img>/<source>/<a> tags, checking lazy-load,
    zoom, and srcset attributes (not just src) so gallery thumbnails aren't missed.
    Prioritizes known gallery containers (WooCommerce, Magento/Fotorama, generic
    slider/swiper markup) before falling back to a full-page scan, so unrelated
    'related products' or header/footer images don't crowd out the real gallery."""
    skip_words = ['logo', 'icon-', 'sprite', 'placeholder', 'payment', 'visa',
                  'mastercard', 'paypal', 'apple-pay', 'google-pay', 'flag-',
                  'loading.gif', 'spinner', 'avatar', 'favicon']
    attrs_to_check = ['data-zoom-image', 'data-zoom', 'data-large_image', 'data-large',
                       'data-original', 'data-lazy-src', 'data-lazy', 'data-src',
                       'data-srcset', 'srcset', 'src', 'href']

    def collect_from(tags):
        found = []
        for tag in tags:
            for attr in attrs_to_check:
                val = tag.get(attr)
                if not val:
                    continue
                if attr in ('srcset', 'data-srcset'):
                    candidates = [p.strip().split(' ')[0] for p in val.split(',') if p.strip()]
                    val = candidates[-1] if candidates else None
                if not val:
                    continue
                if attr == 'href' and not re.search(r'\.(jpg|jpeg|png|webp)(\?|$)', val, re.I):
                    continue
                if val.startswith('//'):
                    val = 'https:' + val
                full = urljoin(base_url_domain, val)
                if not full.startswith('http') or full.lower().endswith('.svg'):
                    continue
                lower = full.lower()
                if any(word in lower for word in skip_words):
                    continue
                full = strip_size_suffix(full)
                if full not in found:
                    found.append(full)
        return found

    # 1. Known gallery containers first — WooCommerce (.woocommerce-product-gallery,
    # .flex-control-thumbs), Magento (.fotorama, .gallery-placeholder, [data-gallery-role]),
    # and generic slider/swiper/carousel markup used by most custom themes.
    gallery_selectors = [
        {'class': re.compile(r'woocommerce-product-gallery', re.I)},
        {'class': re.compile(r'flex-control-thumbs', re.I)},
        {'class': re.compile(r'fotorama', re.I)},
        {'class': re.compile(r'gallery-placeholder', re.I)},
        {'data-gallery-role': True},
        {'class': re.compile(r'product[-_]?(gallery|images|media|slider|carousel)', re.I)},
        {'class': re.compile(r'swiper-wrapper|slick-track|splide__track', re.I)},
    ]
    gallery_urls = []
    for sel in gallery_selectors:
        containers = soup.find_all(['div', 'ul', 'section'], sel)
        for container in containers:
            gallery_urls.extend(collect_from(container.find_all(['img', 'source', 'a'])))

    # 2. Full-page fallback so nothing is missed on themes with non-standard markup
    page_urls = collect_from(soup.find_all(['img', 'source', 'a']))

    combined = []
    for url in gallery_urls + page_urls:
        if url not in combined:
            combined.append(url)
    return combined

def extract_gallery_images_from_scripts(soup, base_url_domain, exclude_urls=None):
    """Last-resort fallback: many Magento themes and JS-rendered custom/Wix-style
    storefronts embed the gallery as a JSON blob inside a <script> tag rather than
    plain <img> tags. Scan script text for image-looking URLs as a safety net."""
    exclude_urls = exclude_urls or set()
    found = []
    media_hint = re.compile(r'(wp-content/uploads|media/catalog/product|cdn|assets|products|images)', re.I)
    url_pattern = re.compile(r'(https?:)?//[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s"\'<>]*)?', re.I)
    for script in soup.find_all('script'):
        text = script.string or script.get_text() or ''
        if not text or len(text) > 200000:
            continue
        for match in url_pattern.finditer(text):
            val = match.group(0)
            if val.startswith('//'):
                val = 'https:' + val
            full = urljoin(base_url_domain, val)
            if not media_hint.search(full):
                continue
            full = strip_size_suffix(full)
            if full in exclude_urls or full in found:
                continue
            found.append(full)
    return found

def collect_gallery_images(url, soup, base_url_domain, session, headers, product_data, max_images):
    """Combine JSON-LD, Shopify's product.json endpoint (if present), og:image,
    known gallery-container HTML, a full-page HTML fallback, and (if still short
    on images) a script-embedded-JSON fallback for Magento/JS-heavy sites.
    De-duplicated and capped at the user-configured max (default 10, up to 20)."""
    combined = []

    if product_data.get('image'):
        img_field = product_data['image']
        combined.extend(img_field if isinstance(img_field, list) else [img_field])

    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        combined.append(og_img.get('content'))

    combined.extend(try_get_shopify_json_images(url, session, headers))
    combined.extend(extract_gallery_images_html(soup, base_url_domain))

    seen = set()
    final = []
    for img in combined:
        if not img or not img.startswith('http'):
            continue
        cleaned = strip_size_suffix(img)
        key = cleaned.split('?')[0]
        if key not in seen:
            seen.add(key)
            final.append(cleaned)
        if len(final) >= max_images:
            break

    # Only reach for the noisier script-tag fallback if the above genuinely came up short
    if len(final) < 2:
        for img in extract_gallery_images_from_scripts(soup, base_url_domain, exclude_urls=seen):
            key = img.split('?')[0]
            if key not in seen:
                seen.add(key)
                final.append(img)
            if len(final) >= max_images:
                break

    return final

# ============================================================
# IMAGE EDITOR
# ============================================================
def edit_image(img_data, filename, config):
    try:
        img = Image.open(BytesIO(img_data))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        width, height = img.size
        final_img = img

        if config.get('enable_flip', True):
            final_img = final_img.transpose(Image.FLIP_LEFT_RIGHT)
        
        if config.get('enable_enhance', True):
            enhancer = ImageEnhance.Brightness(final_img)
            final_img = enhancer.enhance(random.uniform(0.92, 1.08))
            enhancer = ImageEnhance.Contrast(final_img)
            final_img = enhancer.enhance(random.uniform(0.95, 1.05))
        
        if config.get('enable_rounded', False):
            mask = Image.new('L', final_img.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width, height), radius=30, fill=255)
            final_img.putalpha(mask)
            bg = Image.new('RGB', final_img.size, (255, 255, 255))
            bg.paste(final_img, mask=final_img.split()[-1])
            final_img = bg
        
        if config.get('enable_shadow', False):
            shadow_offset = 10
            shadow_blur = 15
            shadow = Image.new('RGBA', (width + shadow_offset*2, height + shadow_offset*2), (0,0,0,0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rectangle((shadow_offset, shadow_offset, width + shadow_offset, height + shadow_offset), fill=(0,0,0,30))
            shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))
            bg = Image.new('RGBA', (width + shadow_offset*2, height + shadow_offset*2), (255,255,255,0))
            bg.paste(shadow, (0,0), shadow)
            bg.paste(final_img, (shadow_offset, shadow_offset))
            final_img = bg.convert('RGB')
        
        if config.get('enable_logo', False):
            logo_bytes = config.get('corner_logo_bytes')
            if logo_bytes:
                try:
                    logo = Image.open(BytesIO(logo_bytes))
                    logo_size = (int(width * 0.15), int(height * 0.15))
                    logo.thumbnail(logo_size, Image.LANCZOS)
                    if logo.mode == 'RGBA':
                        final_img.paste(logo, (20, 20), logo)
                    else:
                        final_img.paste(logo, (20, 20))
                except:
                    pass

        if config.get('enable_watermark', False):
            opacity = config.get('watermark_opacity', 20) / 100
            wm_type = config.get('watermark_type', 'Text')
            wm_size_percent = config.get('watermark_size', 15)
            
            if final_img.mode != 'RGBA':
                final_img = final_img.convert('RGBA')
            
            watermark_layer = Image.new('RGBA', final_img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(watermark_layer)
            
            if wm_type == 'Text':
                txt = config.get('watermark_text', 'Brand')
                font_size = int(min(width, height) * (wm_size_percent / 100))
                try:
                    from PIL import ImageFont
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), txt, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                position = ((width - text_width) // 2, (height - text_height) // 2)
                draw.text(position, txt, font=font, fill=(255, 255, 255, int(255 * opacity)))
            else:
                wm_logo_bytes = config.get('watermark_logo_bytes')
                if wm_logo_bytes:
                    try:
                        wm_logo = Image.open(BytesIO(wm_logo_bytes))
                        target_width = int(width * (wm_size_percent / 100))
                        target_height = int(wm_logo.height * (target_width / wm_logo.width))
                        wm_logo = wm_logo.resize((target_width, target_height), Image.LANCZOS)
                        if wm_logo.mode != 'RGBA':
                            wm_logo = wm_logo.convert('RGBA')
                        alpha = wm_logo.split()[3]
                        alpha = alpha.point(lambda p: int(p * opacity))
                        wm_logo.putalpha(alpha)
                        x = (width - target_width) // 2
                        y = (height - target_height) // 2
                        watermark_layer.paste(wm_logo, (x, y), wm_logo)
                    except:
                        pass
            
            final_img = Image.alpha_composite(final_img, watermark_layer)
            final_img = final_img.convert('RGB')

        if config.get('enable_border', False):
            border_size = 10
            color = config.get('border_color', '#000000')
            final_img = ImageOps.expand(final_img, border=border_size, fill=color)
            width, height = final_img.size
        
        if config.get('enable_gradient', False):
            c1 = config.get('grad_color_1', '#FF5733')
            c2 = config.get('grad_color_2', '#33FF57')
            c1_rgb = tuple(int(c1[i:i+2], 16) for i in (1, 3, 5))
            c2_rgb = tuple(int(c2[i:i+2], 16) for i in (1, 3, 5))
            frame_height = int(height * 0.1)
            strip = Image.new('RGB', (width, frame_height))
            for x in range(width):
                ratio = x / width
                r = int(c1_rgb[0] + (c2_rgb[0] - c1_rgb[0]) * ratio)
                g = int(c1_rgb[1] + (c2_rgb[1] - c1_rgb[1]) * ratio)
                b = int(c1_rgb[2] + (c2_rgb[2] - c1_rgb[2]) * ratio)
                for y in range(frame_height):
                    strip.putpixel((x, y), (r, g, b))
            final_img.paste(strip, (0, height - frame_height))
        
        new_filename = f"branded_{int(time.time())}_{random.randint(1000,9999)}_{filename.split('/')[-1].split('?')[0]}"
        if not new_filename.lower().endswith(('.jpg', '.jpeg')):
            new_filename = new_filename.rsplit('.', 1)[0] + '.jpg'
        
        buffer = BytesIO()
        final_img.save(buffer, format='JPEG', quality=70, optimize=True)
        buffer.seek(0)
        return new_filename, buffer.getvalue()
    except Exception as e:
        try:
            new_filename = f"branded_{int(time.time())}_{random.randint(1000,9999)}_{filename.split('/')[-1].split('?')[0]}"
            if not new_filename.lower().endswith(('.jpg', '.jpeg')):
                new_filename = new_filename.rsplit('.', 1)[0] + '.jpg'
            return new_filename, img_data
        except:
            return None, None

# ============================================================
# SHOPIFY SCRAPER (FIXED: Lazy Load Images + 5 Images Limit)
# ============================================================
def scrape_product(url, session, config):
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    for attempt in range(2):
        try:
            resp = session.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            break
        except:
            if attempt == 0: time.sleep(5)
            else: return None, None, f"Failed"

    soup = BeautifulSoup(resp.text, 'lxml')
    base_url_domain = f"{resp.url.split('/')[0]}//{resp.url.split('/')[2]}"
    product_data = {}

    def is_product_type(data_type):
        if isinstance(data_type, str):
            return data_type == 'Product'
        if isinstance(data_type, list):
            return 'Product' in data_type
        return False

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
        except Exception:
            continue
        # Plain single-object JSON-LD (Shopify, Magento, most custom themes)
        if isinstance(data, dict) and is_product_type(data.get('@type')):
            product_data = data
            break
        # WooCommerce (Yoast/RankMath) commonly wraps everything in "@graph": [...]
        graph = data.get('@graph') if isinstance(data, dict) else None
        if isinstance(graph, list):
            for entry in graph:
                if isinstance(entry, dict) and is_product_type(entry.get('@type')):
                    product_data = entry
                    break
        if product_data:
            break
        # Some sites emit a top-level list of JSON-LD objects instead of @graph
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and is_product_type(entry.get('@type')):
                    product_data = entry
                    break
        if product_data:
            break

    title = extract_title(soup, product_data, url)
    raw_desc = extract_raw_description(soup, product_data) or title

    category_str_early = format_category(soup)

    rewriter = SmartRewriter()
    seo_content = rewriter.generate_seo_content(
        title, raw_desc, category_str_early, config.get('store_context')
    )
    long_desc = seo_content['description_html']
    gen_seo_title = seo_content['seo_title']
    gen_seo_description = seo_content['seo_description']

    price = extract_price(soup, product_data)

    sku_raw = extract_sku(soup, product_data)
    rand_suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=4))
    parent_sku = f"CUSTOM-{rand_suffix}-{sku_raw}"

    # ============================================================
    # 🔥 FIX: FULL GALLERY (JSON endpoint + lazy-load + zoom + srcset,
    # no hard 5-image cap — capped only by the user's slider)
    # ============================================================
    max_images = config.get('max_gallery_images', 10)
    raw_image_urls = collect_gallery_images(
        url, soup, base_url_domain, session, headers, product_data, max_images
    )

    # Process images (edit or keep original)
    image_zip_data = {}
    processed_image_urls = []
    
    if config.get('edit_images', False):
        for img_url in raw_image_urls:
            try:
                img_resp = session.get(img_url, timeout=15)
                if img_resp.status_code == 200:
                    new_name, edited_data = edit_image(img_resp.content, img_url, config)
                    if new_name and edited_data:
                        image_zip_data[new_name] = edited_data
                        processed_image_urls.append(new_name)
                    else:
                        processed_image_urls.append(img_url)
            except:
                processed_image_urls.append(img_url)
    else:
        processed_image_urls = raw_image_urls
    
    # Shopify formatting: pehli image main row mein, baqi additional rows mein
    main_image = processed_image_urls[0] if processed_image_urls else ''
    additional_images = processed_image_urls[1:] if len(processed_image_urls) > 1 else []

    category_str = category_str_early
    vendor = extract_vendor(soup, product_data)
    
    tags = "Imported"
    handle = generate_handle(title)
    
    # Extract variants
    offers = product_data.get('offers')
    variations_data = []
    if isinstance(offers, list) and len(offers) > 1:
        for offer in offers:
            if isinstance(offer, dict):
                var_sku = offer.get('sku', f'VAR-{len(variations_data)+1}')
                var_price = offer.get('price', price)
                var_attrs = {}
                if 'size' in offer: var_attrs['Size'] = offer['size']
                if 'color' in offer: var_attrs['Color'] = offer['color']
                if not var_attrs: var_attrs['Option'] = f'Variant {len(variations_data)+1}'
                variations_data.append({
                    'sku': var_sku, 'price': var_price, 'attrs': var_attrs,
                    'image': offer.get('image', '')
                })

    opt1_name = opt2_name = opt3_name = ''
    if variations_data:
        attr_names = set()
        for var in variations_data:
            attr_names.update(var['attrs'].keys())
        attr_names = sorted(list(attr_names))
        if len(attr_names) > 0: opt1_name = attr_names[0]
        if len(attr_names) > 1: opt2_name = attr_names[1]
        if len(attr_names) > 2: opt3_name = attr_names[2]

    # ============================================================
    # PARENT ROW (with main image)
    # ============================================================
    parent_row = {
        'Title': title,
        'URL handle': handle,
        'Description': long_desc,
        'Vendor': vendor,
        'Product category': category_str,
        'Type': 'Graphic shirt' if 'shirt' in title.lower() else 'Clothing',
        'Tags': tags,
        'Published on online store': 'TRUE',
        'Status': 'active',
        'SKU': '',
        'Barcode': '',
        'Option1 name': opt1_name,
        'Option1 value': '',
        'Option1 Linked To': 'Option1 name' if opt1_name else '',
        'Option2 name': opt2_name,
        'Option2 value': '',
        'Option2 Linked To': 'Option2 name' if opt2_name else '',
        'Option3 name': opt3_name,
        'Option3 value': '',
        'Option3 Linked To': 'Option3 name' if opt3_name else '',
        'Price': '',
        'Compare-at price': '',
        'Cost per item': '',
        'Charge tax': 'TRUE',
        'Tax code': '',
        'Unit price total measure': '',
        'Unit price total measure unit': '',
        'Unit price base measure': '',
        'Unit price base measure unit': '',
        'Inventory tracker': '',
        'Inventory quantity': '',
        'Continue selling when out of stock': '',
        'Weight value (grams)': '',
        'Weight unit for display': '',
        'Requires shipping': 'TRUE',
        'Fulfillment service': 'manual',
        'Product image URL': main_image,
        'Image position': '1',
        'Image alt text': title,
        'Variant image URL': '',
        'Gift card': 'FALSE',
        'SEO title': gen_seo_title or title,
        'SEO description': gen_seo_description or long_desc[:300],
        'Color (product.metafields.shopify.color-pattern)': '',
        'Google Shopping / Google product category': category_str,
        'Google Shopping / Gender': '',
        'Google Shopping / Age group': '',
        'Google Shopping / Manufacturer part number (MPN)': '',
        'Google Shopping / Ad group name': '',
        'Google Shopping / Ads labels': '',
        'Google Shopping / Condition': '',
        'Google Shopping / Custom product': '',
        'Google Shopping / Custom label 0': '',
        'Google Shopping / Custom label 1': '',
        'Google Shopping / Custom label 2': '',
        'Google Shopping / Custom label 3': '',
        'Google Shopping / Custom label 4': ''
    }

    # ============================================================
    # ADDITIONAL IMAGE ROWS (Shopify guidelines ke mutabiq)
    # ============================================================
    image_rows = []
    for idx, img_url in enumerate(additional_images, start=2):
        img_row = {col: '' for col in SHOPIFY_COLUMNS}
        img_row['URL handle'] = handle
        img_row['Product image URL'] = img_url
        img_row['Image position'] = str(idx)
        image_rows.append(img_row)

    # ============================================================
    # VARIANT ROWS
    # ============================================================
    variant_rows = []
    if variations_data:
        for idx, var in enumerate(variations_data):
            var_sku = f"{parent_sku}-{var.get('sku', random.randint(100,999))}"
            var_price = var.get('price', price)
            var_attrs = var['attrs']
            attr1_val = list(var_attrs.values())[0] if len(var_attrs) > 0 else ''
            attr2_val = list(var_attrs.values())[1] if len(var_attrs) > 1 else ''
            attr3_val = list(var_attrs.values())[2] if len(var_attrs) > 2 else ''

            # Variant image
            var_img = var.get('image', '')
            var_img_url = ''
            if config.get('edit_images', False) and var_img:
                try:
                    img_resp = session.get(var_img, timeout=15)
                    if img_resp.status_code == 200:
                        new_name, edited_data = edit_image(img_resp.content, var_img, config)
                        if new_name and edited_data:
                            image_zip_data[new_name] = edited_data
                            var_img_url = new_name
                except:
                    var_img_url = var_img
            if not var_img_url:
                var_img_url = ''

            variant_row = {
                'Title': '',
                'URL handle': handle,
                'Description': '',
                'Vendor': '',
                'Product category': '',
                'Type': '',
                'Tags': '',
                'Published on online store': 'TRUE',
                'Status': 'active',
                'SKU': var_sku,
                'Barcode': random.randint(1000000000, 9999999999),
                'Option1 name': '',
                'Option1 value': attr1_val,
                'Option1 Linked To': '',
                'Option2 name': '',
                'Option2 value': attr2_val,
                'Option2 Linked To': '',
                'Option3 name': '',
                'Option3 value': attr3_val,
                'Option3 Linked To': '',
                'Price': var_price,
                'Compare-at price': '',
                'Cost per item': '',
                'Charge tax': 'TRUE',
                'Tax code': '',
                'Unit price total measure': '',
                'Unit price total measure unit': '',
                'Unit price base measure': '',
                'Unit price base measure unit': '',
                'Inventory tracker': 'shopify',
                'Inventory quantity': 10,
                'Continue selling when out of stock': 'DENY',
                'Weight value (grams)': 150,
                'Weight unit for display': 'g',
                'Requires shipping': 'TRUE',
                'Fulfillment service': 'manual',
                'Product image URL': '',
                'Image position': '',
                'Image alt text': '',
                'Variant image URL': var_img_url,
                'Gift card': 'FALSE',
                'SEO title': '',
                'SEO description': '',
                'Color (product.metafields.shopify.color-pattern)': attr2_val if opt2_name.lower() == 'color' else attr1_val if opt1_name.lower() == 'color' else '',
                'Google Shopping / Google product category': '',
                'Google Shopping / Gender': '',
                'Google Shopping / Age group': '',
                'Google Shopping / Manufacturer part number (MPN)': f'MPN-{var_sku}',
                'Google Shopping / Ad group name': '',
                'Google Shopping / Ads labels': '',
                'Google Shopping / Condition': 'New',
                'Google Shopping / Custom product': '',
                'Google Shopping / Custom label 0': '',
                'Google Shopping / Custom label 1': '',
                'Google Shopping / Custom label 2': '',
                'Google Shopping / Custom label 3': '',
                'Google Shopping / Custom label 4': ''
            }
            variant_rows.append(variant_row)
    
    # Agar simple product hai (no variants)
    if not variations_data:
        parent_row['SKU'] = parent_sku
        parent_row['Price'] = price
        parent_row['Inventory tracker'] = 'shopify'
        parent_row['Inventory quantity'] = 10
        parent_row['Continue selling when out of stock'] = 'DENY'
        parent_row['Weight value (grams)'] = 150
        parent_row['Weight unit for display'] = 'g'
        parent_row['Fulfillment service'] = 'manual'
        parent_row['Barcode'] = random.randint(1000000000, 9999999999)

    # Combine all rows: Parent -> Image Rows -> Variant Rows
    final_rows = [parent_row] + image_rows + variant_rows
    
    return final_rows, image_zip_data, None

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/126.0',
]

# ============================================================
# SHOPIFY COLUMNS
# ============================================================
SHOPIFY_COLUMNS = [
    'Title', 'URL handle', 'Description', 'Vendor', 'Product category', 'Type', 'Tags',
    'Published on online store', 'Status', 'SKU', 'Barcode', 'Option1 name',
    'Option1 value', 'Option1 Linked To', 'Option2 name', 'Option2 value',
    'Option2 Linked To', 'Option3 name', 'Option3 value', 'Option3 Linked To',
    'Price', 'Compare-at price', 'Cost per item', 'Charge tax', 'Tax code',
    'Unit price total measure', 'Unit price total measure unit',
    'Unit price base measure', 'Unit price base measure unit', 'Inventory tracker',
    'Inventory quantity', 'Continue selling when out of stock',
    'Weight value (grams)', 'Weight unit for display', 'Requires shipping',
    'Fulfillment service', 'Product image URL', 'Image position', 'Image alt text',
    'Variant image URL', 'Gift card', 'SEO title', 'SEO description',
    'Color (product.metafields.shopify.color-pattern)',
    'Google Shopping / Google product category', 'Google Shopping / Gender',
    'Google Shopping / Age group', 'Google Shopping / Manufacturer part number (MPN)',
    'Google Shopping / Ad group name', 'Google Shopping / Ads labels',
    'Google Shopping / Condition', 'Google Shopping / Custom product',
    'Google Shopping / Custom label 0', 'Google Shopping / Custom label 1',
    'Google Shopping / Custom label 2', 'Google Shopping / Custom label 3',
    'Google Shopping / Custom label 4'
]

# ============================================================
# PROCESS BATCH FUNCTION
# ============================================================
def process_batch(urls, config, session):
    all_rows = []
    image_data = {}
    failed = []
    for url in urls:
        results, img_data, error = scrape_product(url, session, config)
        if results:
            all_rows.extend(results)
            if img_data:
                image_data.update(img_data)
        else:
            failed.append(url)
    return all_rows, image_data, failed

# ============================================================
# START / RESUME PROCESSING
# ============================================================
if st.button("🚀 Generate Shopify CSV + ZIP (Batch Mode)", type="primary") or st.session_state.is_processing:
    
    if not st.session_state.is_processing and urls_input.strip():
        urls_list = [u.strip() for u in re.split(r'[,\s]+', urls_input) if u.strip().startswith('http')]
        if not urls_list:
            st.error("❌ Valid URL nahi mili.")
        else:
            st.session_state.total_urls = len(urls_list)
            st.session_state.all_urls = urls_list
            st.session_state.batch_index = 0
            st.session_state.all_final_rows = []
            st.session_state.all_image_data = {}
            st.session_state.all_failed = []
            st.session_state.is_processing = True
            st.rerun()
    
    if st.session_state.is_processing:
        urls_list = st.session_state.all_urls
        batch_idx = st.session_state.batch_index
        total = st.session_state.total_urls
        
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        current_batch = urls_list[start:end]
        
        if start < total:
            status_text = st.empty()
            progress_bar = st.progress(0)
            
            status_text.info(f"⏳ Processing Batch {batch_idx+1}/{(total // BATCH_SIZE) + 1} ({start+1} to {end} of {total})...")
            
            config = get_branding_config()
            session = requests.Session()

            batch_rows, batch_images, batch_failed = process_batch(current_batch, config, session)
            
            st.session_state.all_final_rows.extend(batch_rows)
            st.session_state.all_image_data.update(batch_images)
            st.session_state.all_failed.extend(batch_failed)
            st.session_state.batch_index += 1
            
            progress_bar.progress(1.0)
            status_text.success(f"✅ Batch {batch_idx+1} complete. Total rows so far: {len(st.session_state.all_final_rows)}")
            
            if st.session_state.batch_index * BATCH_SIZE < total:
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.is_processing = False
                
                # --- Generate Final CSV ---
                df = pd.DataFrame(st.session_state.all_final_rows, columns=SHOPIFY_COLUMNS)
                for col in SHOPIFY_COLUMNS:
                    if col not in df.columns: df[col] = ''
                df = df[SHOPIFY_COLUMNS]
                
                csv_buffer = StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_data = csv_buffer.getvalue()
                
                # Apply Base URL to Product image and Variant image columns
                if base_url:
                    for row in st.session_state.all_final_rows:
                        for col in ['Product image URL', 'Variant image URL']:
                            img_col = row.get(col, '')
                            if img_col:
                                imgs = img_col.split(', ')
                                new_imgs = []
                                for img in imgs:
                                    if not img.startswith('http'):
                                        new_imgs.append(f"{base_url.rstrip('/')}/{img.lstrip('/')}")
                                    else:
                                        new_imgs.append(img)
                                row[col] = ', '.join(new_imgs)
                    
                    df = pd.DataFrame(st.session_state.all_final_rows, columns=SHOPIFY_COLUMNS)
                    for col in SHOPIFY_COLUMNS:
                        if col not in df.columns: df[col] = ''
                    df = df[SHOPIFY_COLUMNS]
                    csv_buffer = StringIO()
                    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    csv_data = csv_buffer.getvalue()
                
                st.session_state.csv_data = csv_data
                st.session_state.df_preview = df
                st.session_state.failed_urls = st.session_state.all_failed
                st.session_state.total_rows = len(st.session_state.all_final_rows)
                st.session_state.is_ready = True
                
                st.session_state.has_zip = False
                st.session_state.zip_data = None
                
                st.rerun()
        else:
            st.session_state.is_processing = False

# ============================================================
# DISPLAY DOWNLOAD SECTION
# ============================================================
if st.session_state.is_ready:
    st.success(f"🎯 {st.session_state.total_rows} rows generated! {len(st.session_state.failed_urls)} failed.")
    if st.session_state.failed_urls:
        with st.expander(f"⚠️ Show {len(st.session_state.failed_urls)} Failed URLs"):
            st.write('\n'.join(st.session_state.failed_urls))
    
    st.subheader("📊 Preview (First 10 rows)")
    st.dataframe(st.session_state.df_preview.head(10))
    
    col_a, col_b, col_c = st.columns([2, 2, 1])
    
    with col_a:
        st.download_button(
            label="⬇️ Download Shopify CSV",
            data=st.session_state.csv_data,
            file_name=f"shopify_import_{int(time.time())}.csv",
            mime="text/csv",
            use_container_width=True,
            key="csv_download"
        )
    
    with col_b:
        if st.session_state.has_zip and st.session_state.zip_data:
            zip_size_mb = len(st.session_state.zip_data) / (1024 * 1024)
            if zip_size_mb > 800:
                st.warning(f"⚠️ ZIP size is {zip_size_mb:.1f} MB. Download might be slow.")
            st.download_button(
                label=f"⬇️ Download Images ZIP ({zip_size_mb:.1f} MB)",
                data=st.session_state.zip_data,
                file_name=f"branded_images_{int(time.time())}.zip",
                mime="application/zip",
                use_container_width=True,
                key="zip_download"
            )
        else:
            if st.button("🔄 Generate ZIP (Images)", use_container_width=True):
                with st.spinner("📦 ZIP file prepare ho rahi hai... (Large files may take 3-5 min)"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i in range(101):
                        if i % 20 == 0:
                            status_text.text(f"⏳ Compressing images... {i}%")
                        progress_bar.progress(i / 100)
                        time.sleep(0.05)
                    
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for fname, fdata in st.session_state.all_image_data.items():
                            zf.writestr(fname, fdata)
                    zip_buffer.seek(0)
                    zip_ready = zip_buffer.getvalue()
                    
                    zip_size_mb = len(zip_ready) / (1024 * 1024)
                    if zip_size_mb > 1000:
                        st.error(f"❌ ZIP file {zip_size_mb:.1f} MB ki ho gayi! (Limit: 1000 MB)")
                        st.warning("⚠️ Itni badi ZIP file server memory ko exceed kar sakti hai. Please process max 300-400 URLs at a time.")
                    else:
                        st.session_state.zip_data = zip_ready
                        st.session_state.has_zip = True
                        progress_bar.progress(1.0)
                        status_text.text("✅ ZIP ready!")
                        st.rerun()
                
            st.info("ℹ️ Click 'Generate ZIP' to prepare images for download.")
    
    with col_c:
        if st.button("🔄 Reset & New Batch", use_container_width=True):
            for key in ['is_ready', 'csv_data', 'zip_data', 'df_preview', 'failed_urls', 'total_rows', 'has_zip',
                        'batch_index', 'all_final_rows', 'all_image_data', 'all_failed', 'total_urls', 'is_processing', 'all_urls']:
                if key in st.session_state:
                    if key in ['total_rows', 'batch_index', 'total_urls']:
                        st.session_state[key] = 0
                    elif key in ['failed_urls', 'all_failed']:
                        st.session_state[key] = []
                    elif key in ['all_image_data']:
                        st.session_state[key] = {}
                    elif key in ['all_final_rows']:
                        st.session_state[key] = []
                    elif key in ['is_ready', 'has_zip', 'is_processing']:
                        st.session_state[key] = False
                    else:
                        st.session_state[key] = None
            st.rerun()

st.caption("🛒 Shopify V3.4 FINAL | Lazy Load Images Fixed | Batch Mode | 1000 MB ZIP Limit")
