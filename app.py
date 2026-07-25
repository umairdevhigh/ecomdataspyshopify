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
import os
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFilter

# ---------- SESSION STATE ----------
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

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="Shopify + Branding Studio", page_icon="🛒")
st.title("🛒 SHOPIFY ULTIMATE CSV GENERATOR + BRANDING STUDIO")
st.markdown("**Scrape + Brand Images (Logo, Watermark, Borders) + Shopify CSV**")

# ---------- BRANDING STUDIO UI (FULL) ----------
st.subheader("🎨 Branding Studio (Optional)")
with st.expander("⚙️ Configure Image Branding", expanded=True):
    col_a, col_b = st.columns(2)
    
    with col_a:
        # 1. Logo Toggle (Top-Left)
        st.checkbox("🖼️ Add Corner Logo (Top-Left)", key="enable_logo", value=False)
        if st.session_state.get("enable_logo", False):
            st.file_uploader("Upload Corner Logo", type=['png', 'jpg', 'jpeg'], key="logo_uploader")
        
        # 2. Watermark
        st.checkbox("🔤 Add Center Watermark", key="enable_watermark", value=False)
        if st.session_state.get("enable_watermark", False):
            st.radio("Watermark Type", ["Text", "Image Logo"], key="watermark_type", horizontal=True)
            st.slider("Watermark Size (%)", 5, 50, 15, key="watermark_size")
            st.slider("Watermark Opacity (%)", 10, 80, 20, key="watermark_opacity")
            if st.session_state.get("watermark_type") == "Text":
                st.text_input("Watermark Text", "YourBrand.com", key="watermark_text")
            else:
                st.file_uploader("Upload Watermark Logo (PNG)", type=['png', 'jpg', 'jpeg'], key="watermark_logo_uploader")
        
        # 3. Drop Shadow
        st.checkbox("🌑 Drop Shadow", key="enable_shadow", value=False)
        
        # 4. Rounded Corners
        st.checkbox("🔄 Rounded Corners", key="enable_rounded", value=False)
        
        # 5. Mirror Flip
        st.checkbox("🔄 Mirror Flip (Anti-Duplicate)", key="enable_flip", value=True)

    with col_b:
        # 6. Border
        st.checkbox("🖼️ Add Border", key="enable_border", value=False)
        if st.session_state.get("enable_border", False):
            st.color_picker("Border Color", "#000000", key="border_color")
        
        # 7. Gradient Frame
        st.checkbox("🌈 Add Gradient Frame", key="enable_gradient", value=False)
        if st.session_state.get("enable_gradient", False):
            st.color_picker("Gradient Color 1", "#FF5733", key="grad_color_1")
            st.color_picker("Gradient Color 2", "#33FF57", key="grad_color_2")
        
        # 8. Core Tweaks
        st.checkbox("✨ Brightness/Contrast Tweak", key="enable_enhance", value=True)

# ---------- MAIN INPUTS ----------
st.subheader("📥 Input & Controls")
edit_images = st.checkbox("🖌️ Enable Image Editing (Master Switch)", value=True)

col_inp1, col_inp2 = st.columns([3, 1])
with col_inp1:
    urls_input = st.text_area("🔗 Paste Product URLs (One per line):", height=150)
with col_inp2:
    base_url = st.text_input("🌐 Base URL:", placeholder="https://domain.com/wp-content/uploads/")

# ---------- HELPER: GET CONFIG ----------
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

# ---------- REWRITER ----------
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

# ---------- SAFE EXTRACTORS ----------
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

# ---------- ULTIMATE IMAGE EDITOR (FULL BRANDING) ----------
def edit_image(img_data, filename, config):
    try:
        img = Image.open(BytesIO(img_data))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        width, height = img.size
        final_img = img

        # 1. Mirror Flip
        if config.get('enable_flip', True):
            final_img = final_img.transpose(Image.FLIP_LEFT_RIGHT)
        
        # 2. Brightness/Contrast
        if config.get('enable_enhance', True):
            enhancer = ImageEnhance.Brightness(final_img)
            final_img = enhancer.enhance(random.uniform(0.92, 1.08))
            enhancer = ImageEnhance.Contrast(final_img)
            final_img = enhancer.enhance(random.uniform(0.95, 1.05))
        
        # 3. Rounded Corners
        if config.get('enable_rounded', False):
            mask = Image.new('L', final_img.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((0, 0, width, height), radius=30, fill=255)
            final_img.putalpha(mask)
            bg = Image.new('RGB', final_img.size, (255, 255, 255))
            bg.paste(final_img, mask=final_img.split()[-1])
            final_img = bg
        
        # 4. Drop Shadow
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
        
        # 5. Corner Logo
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

        # 6. Center Watermark (Text or Image)
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
            
            else:  # Image Logo Watermark
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

        # 7. Border
        if config.get('enable_border', False):
            border_size = 10
            color = config.get('border_color', '#000000')
            final_img = ImageOps.expand(final_img, border=border_size, fill=color)
            width, height = final_img.size
        
        # 8. Gradient Frame
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
        final_img.save(buffer, format='JPEG', quality=90, optimize=True)
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

# ---------- SHOPIFY SCRAPER (UPDATED WITH CONFIG) ----------
def scrape_product(url, session, config, base_url):
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
    
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            data_type = data.get('@type')
            is_product = False
            if isinstance(data_type, str) and data_type == 'Product': is_product = True
            elif isinstance(data_type, list) and 'Product' in data_type: is_product = True
            if is_product:
                product_data = data
                break
        except: pass

    title = product_data.get('name') or (soup.find('h1').get_text(strip=True) if soup.find('h1') else None)
    if not title:
        og_title = soup.find('meta', property='og:title')
        title = og_title.get('content') if og_title else url.split('/')[-1].replace('-', ' ')

    raw_desc = product_data.get('description') or ''
    if not raw_desc:
        desc_meta = soup.find('meta', attrs={'name': 'description'})
        raw_desc = desc_meta.get('content') if desc_meta else ''
    if not raw_desc or len(raw_desc) < 20:
        og_desc = soup.find('meta', property='og:description')
        raw_desc = og_desc.get('content') if og_desc else title

    rewriter = SmartRewriter()
    long_desc = rewriter.enhance_description(raw_desc, title)

    price = safe_get_offer_price(product_data.get('offers'))
    if not price:
        price_span = soup.find('span', {'class': re.compile(r'price|amount|sale-price')})
        if price_span:
            match = re.search(r'[\d,]+\.?\d*', price_span.get_text())
            price = match.group() if match else '0'
        else: price = '0'

    sku_raw = safe_get_sku(product_data.get('sku'))
    if not sku_raw:
        sku_span = soup.find('span', {'class': re.compile(r'sku|id|model')})
        sku_raw = sku_span.get_text(strip=True) if sku_span else f"OLD-{random.randint(1000,9999)}"
    rand_suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=4))
    parent_sku = f"CUSTOM-{rand_suffix}-{sku_raw}"

    raw_image_urls = []
    if product_data.get('image'):
        if isinstance(product_data['image'], list): raw_image_urls.extend(product_data['image'])
        else: raw_image_urls.append(product_data['image'])
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'): raw_image_urls.append(og_img.get('content'))
    for img in soup.find_all('img'):
        src = img.get('data-src') or img.get('src')
        if src and not src.endswith('.svg') and 'logo' not in src.lower():
            full_url = urljoin(base_url_domain, src)
            if full_url not in raw_image_urls: raw_image_urls.append(full_url)
    raw_image_urls = [im for im in raw_image_urls if im.startswith('http')][:10]

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
            except Exception as e:
                processed_image_urls.append(img_url)
    else:
        processed_image_urls = raw_image_urls
    
    images_str = ', '.join(processed_image_urls) if processed_image_urls else ''

    category_str = format_category(soup)
    vendor = "Imported Vendor"
    if soup.find('meta', attrs={'name': 'author'}):
        vendor = soup.find('meta', attrs={'name': 'author'}).get('content', vendor)
    
    tags = "Imported"
    handle = generate_handle(title)
    
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

    parent_row = {
        'Title': title, 'URL handle': handle, 'Description': long_desc, 'Vendor': vendor,
        'Product category': category_str, 'Type': 'Graphic shirt' if 'shirt' in title.lower() else 'Clothing',
        'Tags': tags, 'Published on online store': 'TRUE', 'Status': 'active', 'SKU': '',
        'Barcode': '', 'Option1 name': opt1_name, 'Option1 value': '', 'Option1 Linked To': 'Option1 name' if opt1_name else '',
        'Option2 name': opt2_name, 'Option2 value': '', 'Option2 Linked To': 'Option2 name' if opt2_name else '',
        'Option3 name': opt3_name, 'Option3 value': '', 'Option3 Linked To': 'Option3 name' if opt3_name else '',
        'Price': '', 'Compare-at price': '', 'Cost per item': '', 'Charge tax': 'TRUE', 'Tax code': '',
        'Unit price total measure': '', 'Unit price total measure unit': '', 'Unit price base measure': '', 'Unit price base measure unit': '',
        'Inventory tracker': '', 'Inventory quantity': '', 'Continue selling when out of stock': '',
        'Weight value (grams)': '', 'Weight unit for display': '', 'Requires shipping': 'TRUE',
        'Fulfillment service': 'manual', 'Product image URL': images_str, 'Image position': '1',
        'Image alt text': title, 'Variant image URL': '', 'Gift card': 'FALSE',
        'SEO title': title, 'SEO description': long_desc[:300],
        'Color (product.metafields.shopify.color-pattern)': '', 'Google Shopping / Google product category': category_str,
        'Google Shopping / Gender': '', 'Google Shopping / Age group': '', 'Google Shopping / Manufacturer part number (MPN)': '',
        'Google Shopping / Ad group name': '', 'Google Shopping / Ads labels': '', 'Google Shopping / Condition': '',
        'Google Shopping / Custom product': '', 'Google Shopping / Custom label 0': '', 'Google Shopping / Custom label 1': '',
        'Google Shopping / Custom label 2': '', 'Google Shopping / Custom label 3': '', 'Google Shopping / Custom label 4': ''
    }
    results = [parent_row]

    if variations_data:
        for idx, var in enumerate(variations_data):
            var_sku = f"{parent_sku}-{var.get('sku', random.randint(100,999))}"
            var_price = var.get('price', price)
            var_attrs = var['attrs']
            attr1_val = list(var_attrs.values())[0] if len(var_attrs) > 0 else ''
            attr2_val = list(var_attrs.values())[1] if len(var_attrs) > 1 else ''
            attr3_val = list(var_attrs.values())[2] if len(var_attrs) > 2 else ''

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
                'Title': '', 'URL handle': handle, 'Description': '', 'Vendor': '', 'Product category': '',
                'Type': '', 'Tags': '', 'Published on online store': 'TRUE', 'Status': 'active',
                'SKU': var_sku, 'Barcode': random.randint(1000000000, 9999999999),
                'Option1 name': '', 'Option1 value': attr1_val, 'Option1 Linked To': '',
                'Option2 name': '', 'Option2 value': attr2_val, 'Option2 Linked To': '',
                'Option3 name': '', 'Option3 value': attr3_val, 'Option3 Linked To': '',
                'Price': var_price, 'Compare-at price': '', 'Cost per item': '', 'Charge tax': 'TRUE', 'Tax code': '',
                'Unit price total measure': '', 'Unit price total measure unit': '', 'Unit price base measure': '', 'Unit price base measure unit': '',
                'Inventory tracker': 'shopify', 'Inventory quantity': 10, 'Continue selling when out of stock': 'DENY',
                'Weight value (grams)': 150, 'Weight unit for display': 'g', 'Requires shipping': 'TRUE',
                'Fulfillment service': 'manual', 'Product image URL': '', 'Image position': '',
                'Image alt text': '', 'Variant image URL': var_img_url, 'Gift card': 'FALSE',
                'SEO title': '', 'SEO description': '',
                'Color (product.metafields.shopify.color-pattern)': attr2_val if opt2_name.lower() == 'color' else attr1_val if opt1_name.lower() == 'color' else '',
                'Google Shopping / Google product category': '', 'Google Shopping / Gender': '',
                'Google Shopping / Age group': '', 'Google Shopping / Manufacturer part number (MPN)': f'MPN-{var_sku}',
                'Google Shopping / Ad group name': '', 'Google Shopping / Ads labels': '',
                'Google Shopping / Condition': 'New', 'Google Shopping / Custom product': '',
                'Google Shopping / Custom label 0': '', 'Google Shopping / Custom label 1': '',
                'Google Shopping / Custom label 2': '', 'Google Shopping / Custom label 3': '', 'Google Shopping / Custom label 4': ''
            }
            results.append(variant_row)
    
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

    return results, image_zip_data, None

# ---------- USER-AGENTS ----------
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/126.0',
]

# ---------- SHOPIFY COLUMNS ----------
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

# ---------- MAIN LOGIC ----------
if st.button("🚀 Generate Shopify CSV + ZIP", type="primary"):
    if not urls_input.strip():
        st.error("❌ Kuch URLs toh daalo!")
    else:
        urls = [u.strip() for u in re.split(r'[,\s]+', urls_input) if u.strip().startswith('http')]
        if not urls:
            st.error("❌ Valid URL nahi mili.")
        else:
            st.session_state.is_ready = False
            st.session_state.csv_data = None
            st.session_state.zip_data = None
            st.session_state.df_preview = None
            st.session_state.failed_urls = []
            st.session_state.total_rows = 0
            st.session_state.has_zip = False

            progress_bar = st.progress(0)
            status_text = st.empty()
            all_rows = []
            failed_urls = []
            all_image_data = {}
            
            config = get_branding_config()
            session = requests.Session()
            total_urls = len(urls)
            
            for idx, url in enumerate(urls):
                status_text.text(f"⏳ Processing {idx+1}/{total_urls}...")
                results, image_data, error = scrape_product(url, session, config, base_url)
                if results:
                    all_rows.extend(results)
                    if image_data:
                        all_image_data.update(image_data)
                else:
                    failed_urls.append(url)
                progress_bar.progress((idx + 1) / total_urls)
                time.sleep(random.uniform(1.0, 2.5))
            
            progress_bar.progress(1.0)
            status_text.text("✅ Complete!")
            
            if not all_rows:
                st.error("❌ Koi product scrape nahi ho saka.")
                st.stop()
            
            # Apply Base URL to images in CSV
            for row in all_rows:
                for col in ['Product image URL', 'Variant image URL']:
                    img_col = row.get(col, '')
                    if img_col and base_url:
                        imgs = img_col.split(', ')
                        new_imgs = []
                        for img in imgs:
                            if not img.startswith('http'):
                                new_imgs.append(f"{base_url.rstrip('/')}/{img.lstrip('/')}")
                            else:
                                new_imgs.append(img)
                        row[col] = ', '.join(new_imgs)

            df = pd.DataFrame(all_rows, columns=SHOPIFY_COLUMNS)
            for col in SHOPIFY_COLUMNS:
                if col not in df.columns: df[col] = ''
            df = df[SHOPIFY_COLUMNS]
            
            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_data = csv_buffer.getvalue()
            
            zip_buffer = BytesIO()
            has_zip = False
            if config.get('edit_images', False) and all_image_data:
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filename, binary_data in all_image_data.items():
                        zip_file.writestr(filename, binary_data)
                zip_buffer.seek(0)
                zip_ready = zip_buffer.getvalue()
                has_zip = True
            else:
                zip_ready = None

            st.session_state.csv_data = csv_data
            st.session_state.zip_data = zip_ready
            st.session_state.df_preview = df
            st.session_state.failed_urls = failed_urls
            st.session_state.total_rows = len(all_rows)
            st.session_state.is_ready = True
            st.session_state.has_zip = has_zip
            
            st.rerun()

# ---------- PERSISTENT DOWNLOAD BUTTONS ----------
if st.session_state.is_ready:
    st.success(f"🎯 {st.session_state.total_rows} rows generated! {len(st.session_state.failed_urls)} failed.")
    if st.session_state.failed_urls:
        with st.expander(f"⚠️ Show {len(st.session_state.failed_urls)} Failed URLs"):
            st.write('\n'.join(st.session_state.failed_urls))
    
    st.subheader("📊 Preview (First 5 rows)")
    st.dataframe(st.session_state.df_preview.head(5))
    
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
            st.download_button(
                label=f"⬇️ Download Images ZIP ({len(st.session_state.zip_data) // 1024} KB)",
                data=st.session_state.zip_data,
                file_name=f"branded_images_{int(time.time())}.zip",
                mime="application/zip",
                use_container_width=True,
                key="zip_download"
            )
        else:
            if config.get('edit_images', False):
                st.info("ℹ️ No edited images generated.")
            else:
                st.info("ℹ️ Image editing OFF.")
    with col_c:
        if st.button("🔄 Reset & New Batch", use_container_width=True):
            st.session_state.is_ready = False
            st.session_state.csv_data = None
            st.session_state.zip_data = None
            st.session_state.df_preview = None
            st.session_state.failed_urls = []
            st.session_state.total_rows = 0
            st.session_state.has_zip = False
            st.rerun()

st.caption("🛒 Shopify Mode | Branding Studio V2 | Watermark Size + Image Watermark | Full Columns")
