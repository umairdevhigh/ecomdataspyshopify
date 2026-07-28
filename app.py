import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import random
import time
import json
from urllib.parse import urljoin, urlparse, urlunparse
import pandas as pd
from io import BytesIO, StringIO
import zipfile
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFilter
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
import logging
from collections import defaultdict

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
st.set_page_config(page_title="Shopify + Branding Studio (Universal Scraper)", page_icon="🛒")
st.title("🛒 SHOPIFY ULTIMATE CSV + BRANDING STUDIO V4.0 (UNIVERSAL EXTRACTOR)")
st.markdown("**Now extracts from any e‑commerce site | Variant images fixed | Multi‑source merging**")

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
        'enable_rounded': st.session_state.get("enable_rounded", False)
    }

# ============================================================
# REWRITER + EXTRACTORS (Legacy helpers kept for description)
# ============================================================
class SmartRewriter:
    def __init__(self):
        self.synonyms = {
            'great': 'exceptional', 'good': 'superior', 'best': 'top-tier',
            'durable': 'long-lasting', 'strong': 'robust', 'quality': 'premium',
            'amazing': 'remarkable', 'perfect': 'ideal', 'easy': 'effortless',
            'simple': 'straightforward', 'modern': 'contemporary', 'classic': 'timeless',
            'beautiful': 'exquisite', 'nice': 'fantastic', 'cool': 'stylish',
            'high-quality': 'superior-grade', 'comfortable': 'ultra-comfortable'
        }
        self.protected = {
            'leather', 'jacket', 'biker', 'motorcycle', 'hide', 'zip', 'pocket', 
            'collar', 'sleeve', 'fit', 'style', 'men', 'women', 'unisex', 'black',
            'brown', 'tan', 'maroon', 'red', 'blue', 'green', 'grey', 'white',
            'divi', 'engine', 'woocommerce', 'wordpress', 'hoodie', 'shirt', 'tee'
        }

    def enhance_description(self, text, title=""):
        if not text or len(text) < 5:
            return f"Discover the perfect blend of style and durability with this premium {title}. Crafted for the modern individual, it offers unmatched comfort and timeless appeal."
        sentences = re.split(r'(?<=[.!?]) +', text)
        new_sentences = []
        for sent in sentences:
            words = sent.split()
            new_words = []
            for word in words:
                lower_word = word.lower().strip('.,!?')
                if lower_word in self.synonyms and lower_word not in self.protected:
                    replacement = self.synonyms[lower_word]
                    if word[0].isupper():
                        replacement = replacement.capitalize()
                    if word.endswith('.'):
                        replacement += '.'
                    new_words.append(replacement)
                else:
                    new_words.append(word)
            new_sentences.append(' '.join(new_words))
        enhanced = '. '.join(new_sentences)
        hooks = [
            "Elevate your wardrobe with ", "Step into timeless style with ",
            "Experience premium craftsmanship with ", "Make a bold statement with "
        ]
        if not enhanced.lower().startswith(('elevate', 'step', 'experience', 'make', 'discover')):
            hook = random.choice(hooks)
            enhanced = hook + enhanced[0].lower() + enhanced[1:]
        return enhanced.strip()

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

def format_category(soup, default="Apparel & Accessories > Clothing > Tops"):
    bread = soup.find('ul', {'class': re.compile(r'breadcrumb|breadcrumbs')})
    if bread:
        links = bread.find_all('a')
        if len(links) > 1:
            categories = [link.get_text(strip=True) for link in links[1:]]
            if categories: return ' > '.join(categories)
    return default

def generate_handle(title):
    handle = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    if len(handle) > 200:
        handle = handle[:200].rsplit('-', 1)[0]
    return handle

# ============================================================
# IMAGE EDITOR (unchanged)
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
# NEW ARCHITECTURE: UNIVERSAL PRODUCT EXTRACTION PIPELINE
# ============================================================

# ---------- Data Classes ----------
@dataclass
class ProductVariant:
    sku: str = ''
    price: str = ''
    compare_price: str = ''
    inventory: int = 0
    options: Dict[str, str] = field(default_factory=dict)  # e.g., {'Size': 'M', 'Color': 'Red'}
    image: str = ''  # URL of variant-specific image
    weight: str = ''
    barcode: str = ''
    availability: str = ''

@dataclass
class UniversalProduct:
    url: str = ''
    title: str = ''
    handle: str = ''
    description: str = ''
    vendor: str = ''
    brand: str = ''
    category: str = ''
    product_type: str = ''
    tags: List[str] = field(default_factory=list)
    status: str = 'active'
    seo_title: str = ''
    seo_description: str = ''
    price: str = ''
    compare_price: str = ''
    sku: str = ''
    barcode: str = ''
    inventory: int = 0
    weight: str = ''
    dimensions: Dict[str, str] = field(default_factory=dict)
    attributes: Dict[str, str] = field(default_factory=dict)  # extra metadata
    gallery_images: List[str] = field(default_factory=list)  # all images (URLs)
    variants: List[ProductVariant] = field(default_factory=list)
    # Additional discovered images not in gallery (e.g., from other sources)
    extra_images: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

# ---------- Website Discovery ----------
class WebsiteDiscovery:
    """Inspect page to determine available data sources."""
    @staticmethod
    def discover(soup: BeautifulSoup, text: str) -> Dict[str, bool]:
        sources = {
            'json_ld': False,
            'embedded_json': False,
            'javascript_vars': False,
            'microdata': False,
            'opengraph': False,
            'meta_tags': False,
            'html_dom': True,  # always true
            'api_endpoint': False,
            'client_side_rendered': False
        }
        # Check JSON-LD
        if soup.find('script', type='application/ld+json'):
            sources['json_ld'] = True
        # Check embedded JSON (common in WooCommerce, etc.)
        if re.search(r'\{[\s\S]*?"@context"[\s\S]*?"@type"[\s\S]*?"Product"', text):
            sources['embedded_json'] = True
        # Check for JavaScript objects (e.g., product data in window)
        if re.search(r'window\.[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*\{', text):
            sources['javascript_vars'] = True
        # Check microdata
        if soup.find(itemscope=True):
            sources['microdata'] = True
        # Check OpenGraph
        if soup.find('meta', property='og:type') and soup.find('meta', property='og:title'):
            sources['opengraph'] = True
        # Check meta tags
        if soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'name': 'keywords'}):
            sources['meta_tags'] = True
        # Check for API endpoints (e.g., /api/product/ in script)
        if re.search(r'["\']/api/[a-zA-Z0-9/_-]+["\']', text):
            sources['api_endpoint'] = True
        # Check for client-side rendering (e.g., #app, data-reactroot)
        if soup.find(id='app') or soup.find('div', attrs={'data-reactroot': True}):
            sources['client_side_rendered'] = True
        return sources

# ---------- Extractors ----------
class BaseExtractor:
    """Base class for all extractors."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        return {}

class StructuredDataExtractor(BaseExtractor):
    """Extract from JSON-LD."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        data = {}
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                json_data = json.loads(script.string)
                if isinstance(json_data, list):
                    for item in json_data:
                        if item.get('@type') == 'Product':
                            data = item
                            break
                elif isinstance(json_data, dict) and json_data.get('@type') == 'Product':
                    data = json_data
                    break
            except:
                continue
        return data

class EmbeddedJsonExtractor(BaseExtractor):
    """Extract from embedded JSON (common in WooCommerce, custom)."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        # Look for JSON that contains product-like keys
        # Simple heuristic: search for "product" or "Product" and parse
        # We'll use a more robust approach: find all JSON objects in scripts or inline.
        # This is simplified; we can also look for data-* attributes.
        # For now, we'll return empty; we can implement more robust parsing if needed.
        # But we'll rely on other extractors.
        return {}

class JavaScriptObjectExtractor(BaseExtractor):
    """Extract from JavaScript variables (e.g., window.productData)."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        # Find common patterns like var product = {...};
        # We'll search for product-like assignments.
        # This is complex; we'll implement a basic regex search.
        data = {}
        patterns = [
            r'var\s+product\s*=\s*(\{[\s\S]*?\});',
            r'window\.productData\s*=\s*(\{[\s\S]*?\});',
            r'productData\s*=\s*(\{[\s\S]*?\});',
            r'data-product\s*=\s*[\'"]([^\'"]+)[\'"]',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    # If it's a JSON object
                    json_str = match.group(1)
                    # Try to parse as JSON (might need to clean)
                    # Sometimes the object contains JavaScript comments or functions, so we try to extract JSON.
                    # We'll use a simple approach: find the outermost braces.
                    # We'll just store raw and attempt to parse later.
                    # For now, we'll not implement full parsing.
                    pass
                except:
                    continue
        return {}

class MicrodataExtractor(BaseExtractor):
    """Extract from microdata (itemscope, itemprop)."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        data = {}
        # Find product microdata
        product = soup.find(itemscope=True, attrs={'itemtype': re.compile(r'Product')})
        if product:
            # Extract properties
            props = {}
            for prop in product.find_all(itemprop=True):
                key = prop.get('itemprop')
                value = prop.get('content') or prop.get('src') or prop.get_text(strip=True)
                if key and value:
                    props[key] = value
            # Map to our fields
            if 'name' in props:
                data['name'] = props['name']
            if 'description' in props:
                data['description'] = props['description']
            if 'sku' in props:
                data['sku'] = props['sku']
            if 'price' in props:
                data['price'] = props['price']
            if 'image' in props:
                data['image'] = props['image']
        return data

class OpenGraphExtractor(BaseExtractor):
    """Extract from OpenGraph meta tags."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        data = {}
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            data['name'] = og_title['content']
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            data['description'] = og_desc['content']
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            data['image'] = og_image['content']
        og_url = soup.find('meta', property='og:url')
        if og_url and og_url.get('content'):
            data['url'] = og_url['content']
        og_type = soup.find('meta', property='og:type')
        if og_type and og_type.get('content'):
            data['@type'] = og_type['content']
        return data

class MetaTagExtractor(BaseExtractor):
    """Extract from standard meta tags."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        data = {}
        desc = soup.find('meta', attrs={'name': 'description'})
        if desc and desc.get('content'):
            data['description'] = desc['content']
        keywords = soup.find('meta', attrs={'name': 'keywords'})
        if keywords and keywords.get('content'):
            data['keywords'] = keywords['content']
        return data

class HtmlDomExtractor(BaseExtractor):
    """Extract from HTML DOM (title, h1, images, etc.)."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        data = {}
        # Title
        title_tag = soup.find('title')
        if title_tag:
            data['name'] = title_tag.get_text(strip=True)
        # H1
        h1 = soup.find('h1')
        if h1 and not data.get('name'):
            data['name'] = h1.get_text(strip=True)
        # Price: find common patterns
        price_span = soup.find('span', {'class': re.compile(r'price|amount|sale-price')})
        if price_span:
            match = re.search(r'[\d,]+\.?\d*', price_span.get_text())
            if match:
                data['price'] = match.group()
        # SKU: find common patterns
        sku_span = soup.find('span', {'class': re.compile(r'sku|id|model')})
        if sku_span:
            data['sku'] = sku_span.get_text(strip=True)
        # Category from breadcrumbs
        bread = soup.find('ul', {'class': re.compile(r'breadcrumb|breadcrumbs')})
        if bread:
            links = bread.find_all('a')
            if len(links) > 1:
                categories = [link.get_text(strip=True) for link in links[1:]]
                if categories:
                    data['category'] = ' > '.join(categories)
        # Images from img tags
        images = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
            if src and not src.endswith('.svg') and 'logo' not in src.lower():
                full_url = urljoin(url, src)
                images.append(full_url)
        if images:
            data['images'] = images
        return data

class ImageExtractor(BaseExtractor):
    """Specialized image extractor from various attributes."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        images = set()
        # All img tags
        for img in soup.find_all('img'):
            for attr in ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-image', 'data-large-image']:
                src = img.get(attr)
                if src:
                    full = urljoin(url, src)
                    if full.startswith('http'):
                        images.add(full)
        # Background images (style attribute)
        for elem in soup.find_all(style=True):
            style = elem.get('style')
            if style and 'background-image' in style:
                match = re.search(r'url\([\'"]?([^\)\'"]+)[\'"]?\)', style)
                if match:
                    full = urljoin(url, match.group(1))
                    if full.startswith('http'):
                        images.add(full)
        # Picture sources
        for source in soup.find_all('source'):
            srcset = source.get('srcset')
            if srcset:
                for part in srcset.split(','):
                    part = part.strip().split(' ')[0]
                    full = urljoin(url, part)
                    if full.startswith('http'):
                        images.add(full)
        return {'images': list(images)}

class VariantExtractor(BaseExtractor):
    """Extract variants from various sources."""
    @staticmethod
    def extract(soup: BeautifulSoup, text: str, url: str) -> Dict[str, Any]:
        variants = []
        # Look for JSON-LD offers
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    offers = data.get('offers')
                    if isinstance(offers, list):
                        for offer in offers:
                            if isinstance(offer, dict):
                                variant = ProductVariant(
                                    sku=offer.get('sku', ''),
                                    price=offer.get('price', ''),
                                    compare_price=offer.get('price', ''),
                                    inventory=offer.get('inventory', 0),
                                    options={},
                                    image=offer.get('image', ''),
                                    availability=offer.get('availability', '')
                                )
                                # Extract attributes
                                if 'size' in offer:
                                    variant.options['Size'] = offer['size']
                                if 'color' in offer:
                                    variant.options['Color'] = offer['color']
                                variants.append(variant)
            except:
                continue
        # Also look for HTML selects (e.g., size/color dropdowns)
        selects = soup.find_all('select')
        for sel in selects:
            # This is complex; we'll skip for now.
            pass
        return {'variants': variants}

# ---------- Data Merger ----------
class DataMerger:
    """Merge multiple extraction results into a UniversalProduct."""
    @staticmethod
    def merge(sources: List[Dict[str, Any]], url: str) -> UniversalProduct:
        product = UniversalProduct(url=url)
        # We'll merge by taking the first non-empty value, with priority: JSON-LD > OpenGraph > HTML > others
        # But we can implement more sophisticated merging.
        # For simplicity, we'll combine lists and take max length for descriptions, etc.
        # We'll use a dict to collect all values and pick the best.

        # Collect fields
        fields = {
            'name': [],
            'description': [],
            'price': [],
            'sku': [],
            'image': [],
            'images': [],
            'category': [],
            'brand': [],
            'vendor': [],
            'variants': [],
            'availability': [],
            'weight': [],
            'barcode': [],
            'inventory': [],
        }

        for src in sources:
            for key in fields:
                if key in src:
                    val = src[key]
                    if isinstance(val, list):
                        fields[key].extend(val)
                    else:
                        fields[key].append(val)

        # Now choose best values
        # Title: take first non-empty, prefer from JSON-LD or OpenGraph
        if fields['name']:
            # Simple: take first that is not empty and has reasonable length
            for name in fields['name']:
                if name and len(name) > 3:
                    product.title = name
                    break
        # Description: take longest non-empty
        if fields['description']:
            descs = [d for d in fields['description'] if d and len(d) > 10]
            if descs:
                product.description = max(descs, key=len)
        # Price: take first valid number
        if fields['price']:
            for price in fields['price']:
                if price and re.search(r'[\d,]+\.?\d*', price):
                    product.price = re.search(r'[\d,]+\.?\d*', price).group()
                    break
        # SKU: take first non-empty
        if fields['sku']:
            for sku in fields['sku']:
                if sku:
                    product.sku = sku
                    break
        # Category: take first non-empty
        if fields['category']:
            for cat in fields['category']:
                if cat:
                    product.category = cat
                    break
        # Vendor/Brand
        if fields['vendor']:
            product.vendor = fields['vendor'][0]
        if fields['brand']:
            product.brand = fields['brand'][0]
        # Images: collect all unique
        all_images = set()
        for imgs in fields['images']:
            if isinstance(imgs, list):
                all_images.update(imgs)
            elif isinstance(imgs, str):
                all_images.add(imgs)
        # Also add image from 'image' field
        if fields['image']:
            for img in fields['image']:
                if img:
                    all_images.add(img)
        product.gallery_images = list(all_images)

        # Variants: merge and deduplicate by SKU
        variant_dict = {}
        for vlist in fields['variants']:
            if isinstance(vlist, list):
                for v in vlist:
                    if isinstance(v, ProductVariant):
                        key = v.sku or id(v)
                        if key not in variant_dict:
                            variant_dict[key] = v
                        else:
                            # Merge options and other fields
                            existing = variant_dict[key]
                            if not existing.price and v.price:
                                existing.price = v.price
                            if not existing.image and v.image:
                                existing.image = v.image
                            # Merge options
                            for k, val in v.options.items():
                                if k not in existing.options:
                                    existing.options[k] = val
        product.variants = list(variant_dict.values())

        # Handle missing data
        if not product.title:
            product.title = "Product"
        if not product.price:
            product.price = "0.00"
        if not product.sku:
            product.sku = f"SKU-{random.randint(1000,9999)}"

        return product

# ---------- Variant Image Mapper ----------
class VariantImageMapper:
    """Map each variant to the most probable image using confidence."""
    @staticmethod
    def map_variants(product: UniversalProduct) -> None:
        if not product.variants:
            return
        # Build a set of all gallery images
        all_imgs = set(product.gallery_images)
        # For each variant, find the best image
        # Priority order:
        # 1. Direct image from variant (already set)
        # 2. Match by option values (e.g., Color: Red) in alt/text/data attributes
        # 3. Match by position (order)
        # 4. Fallback to first image

        # Build image metadata (from page) - we don't have that info here, so we'll use the list order.
        # We'll assume the gallery images are in order of appearance.
        # For matching by attributes, we would need to have scraped alt/title/data.
        # Since our extractors didn't store that, we'll use a simpler approach:
        # If variant has a color, try to find image with that color in URL or alt.
        # We can't do that without more data. So we'll assign by order:
        # Sort variants by options if possible.
        # For now, we'll assign images to variants in order.

        # If there are more variants than images, we'll reuse the last image.
        num_variants = len(product.variants)
        num_images = len(all_imgs)
        if num_images == 0:
            return
        # Sort variants by a consistent key (SKU or first option)
        sorted_vars = sorted(product.variants, key=lambda v: (v.sku, list(v.options.values())[0] if v.options else ''))
        # Assign images in order, cycling if needed
        for idx, var in enumerate(sorted_vars):
            if not var.image:  # only assign if not already set
                if idx < num_images:
                    var.image = list(all_imgs)[idx]
                else:
                    var.image = list(all_imgs)[-1]

# ---------- Shopify Converter ----------
class ShopifyConverter:
    """Convert UniversalProduct to Shopify CSV rows."""
    @staticmethod
    def convert(product: UniversalProduct, config: Dict, session: requests.Session, base_url_override: str = '') -> Tuple[List[Dict], Dict[str, bytes]]:
        # Generate handle
        handle = generate_handle(product.title)
        rewriter = SmartRewriter()
        long_desc = rewriter.enhance_description(product.description, product.title)

        # Determine option names from variants
        opt1_name = opt2_name = opt3_name = ''
        if product.variants:
            # Collect all option keys from variants
            option_keys = set()
            for var in product.variants:
                option_keys.update(var.options.keys())
            option_keys = sorted(option_keys)
            if len(option_keys) > 0: opt1_name = option_keys[0]
            if len(option_keys) > 1: opt2_name = option_keys[1]
            if len(option_keys) > 2: opt3_name = option_keys[2]

        # Prepare main image (first image from gallery)
        main_image_url = product.gallery_images[0] if product.gallery_images else ''
        # Process images with branding if enabled
        image_zip_data = {}
        processed_image_urls = {}  # original URL -> processed filename or original

        # Helper to download and process an image
        def process_image(img_url: str) -> str:
            if not img_url:
                return ''
            if img_url in processed_image_urls:
                return processed_image_urls[img_url]
            if config.get('edit_images', False):
                try:
                    resp = session.get(img_url, timeout=15)
                    if resp.status_code == 200:
                        new_name, edited_data = edit_image(resp.content, img_url, config)
                        if new_name and edited_data:
                            image_zip_data[new_name] = edited_data
                            processed_image_urls[img_url] = new_name
                            return new_name
                        else:
                            processed_image_urls[img_url] = img_url
                            return img_url
                    else:
                        processed_image_urls[img_url] = img_url
                        return img_url
                except:
                    processed_image_urls[img_url] = img_url
                    return img_url
            else:
                processed_image_urls[img_url] = img_url
                return img_url

        # Process main image
        if main_image_url:
            main_image_url = process_image(main_image_url)

        # Process variant images
        for var in product.variants:
            if var.image:
                var.image = process_image(var.image)

        # Build parent row
        parent_row = {
            'Title': product.title,
            'URL handle': handle,
            'Description': long_desc,
            'Vendor': product.vendor or "Imported Vendor",
            'Product category': product.category or "Apparel & Accessories > Clothing > Tops",
            'Type': product.product_type or ('Graphic shirt' if 'shirt' in product.title.lower() else 'Clothing'),
            'Tags': ', '.join(product.tags) if product.tags else 'Imported',
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
            'Product image URL': main_image_url,
            'Image position': '1',
            'Image alt text': product.title,
            'Variant image URL': '',
            'Gift card': 'FALSE',
            'SEO title': product.seo_title or product.title,
            'SEO description': product.seo_description or long_desc[:300],
            'Color (product.metafields.shopify.color-pattern)': '',
            'Google Shopping / Google product category': product.category or '',
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

        # Additional image rows (images beyond first, not used as variant images)
        # We'll collect all images that are not used as main or variant images
        used_images = set([main_image_url] + [v.image for v in product.variants if v.image])
        additional_images = [img for img in product.gallery_images if img not in used_images]
        image_rows = []
        for idx, img_url in enumerate(additional_images[:5], start=2):
            img_row = {col: '' for col in SHOPIFY_COLUMNS}
            img_row['URL handle'] = handle
            img_row['Product image URL'] = img_url
            img_row['Image position'] = str(idx)
            image_rows.append(img_row)

        # Variant rows
        variant_rows = []
        if product.variants:
            for var in product.variants:
                var_sku = f"{product.sku}-{var.sku}" if var.sku else f"{product.sku}-VAR-{random.randint(100,999)}"
                var_price = var.price or product.price
                # Get option values in order
                attrs = var.options
                attr1_val = attrs.get(opt1_name, '') if opt1_name else ''
                attr2_val = attrs.get(opt2_name, '') if opt2_name else ''
                attr3_val = attrs.get(opt3_name, '') if opt3_name else ''

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
                    'Barcode': var.barcode or random.randint(1000000000, 9999999999),
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
                    'Compare-at price': var.compare_price or '',
                    'Cost per item': '',
                    'Charge tax': 'TRUE',
                    'Tax code': '',
                    'Unit price total measure': '',
                    'Unit price total measure unit': '',
                    'Unit price base measure': '',
                    'Unit price base measure unit': '',
                    'Inventory tracker': 'shopify',
                    'Inventory quantity': var.inventory or 10,
                    'Continue selling when out of stock': 'DENY',
                    'Weight value (grams)': var.weight or 150,
                    'Weight unit for display': 'g',
                    'Requires shipping': 'TRUE',
                    'Fulfillment service': 'manual',
                    'Product image URL': '',
                    'Image position': '',
                    'Image alt text': '',
                    'Variant image URL': var.image or '',
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

        # If no variants, make parent row the only row with SKU/price/inventory
        if not product.variants:
            parent_row['SKU'] = product.sku
            parent_row['Price'] = product.price
            parent_row['Inventory tracker'] = 'shopify'
            parent_row['Inventory quantity'] = product.inventory or 10
            parent_row['Continue selling when out of stock'] = 'DENY'
            parent_row['Weight value (grams)'] = 150
            parent_row['Weight unit for display'] = 'g'
            parent_row['Fulfillment service'] = 'manual'
            parent_row['Barcode'] = product.barcode or random.randint(1000000000, 9999999999)

        final_rows = [parent_row] + image_rows + variant_rows
        return final_rows, image_zip_data

# ---------- Main Scraper (now using new architecture) ----------
def scrape_shopify_product(url, session, config):
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    try:
        resp = session.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except:
        return None, None, "Failed to fetch URL"

    soup = BeautifulSoup(resp.text, 'lxml')
    text = resp.text

    # 1. Discover sources
    sources = WebsiteDiscovery.discover(soup, text)

    # 2. Extract data from each available source
    extractors = []
    if sources['json_ld']:
        extractors.append(StructuredDataExtractor)
    if sources['embedded_json']:
        extractors.append(EmbeddedJsonExtractor)
    if sources['javascript_vars']:
        extractors.append(JavaScriptObjectExtractor)
    if sources['microdata']:
        extractors.append(MicrodataExtractor)
    if sources['opengraph']:
        extractors.append(OpenGraphExtractor)
    if sources['meta_tags']:
        extractors.append(MetaTagExtractor)
    # Always use HTML and image extractors
    extractors.append(HtmlDomExtractor)
    extractors.append(ImageExtractor)
    extractors.append(VariantExtractor)

    # Run extractors
    extraction_results = []
    for Extractor in extractors:
        try:
            data = Extractor.extract(soup, text, url)
            if data:
                extraction_results.append(data)
        except:
            continue

    # 3. Merge into UniversalProduct
    product = DataMerger.merge(extraction_results, url)

    # 4. Map variant images
    VariantImageMapper.map_variants(product)

    # 5. Convert to Shopify rows and process images
    rows, image_data = ShopifyConverter.convert(product, config, session, base_url_override='')

    return rows, image_data, None

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
        results, img_data, error = scrape_shopify_product(url, session, config)
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

st.caption("🛒 Shopify V4.0 | Universal Extractor | Variant Images Fixed | No Duplicates")
