import streamlit as st
import requests
from bs4 import BeautifulSoup
import csv
import re
import random
import time
from urllib.parse import urljoin
import json
import pandas as pd
from io import BytesIO, StringIO
import zipfile
import os
from PIL import Image, ImageEnhance, ImageOps

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="Shopify Ultimate CSV Generator", page_icon="🛒")

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

# ---------- ROTATING USER-AGENTS ----------
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/126.0',
]

# ---------- REWRITER (SIRF GENERIC ADJECTIVES) ----------
class SmartRewriter:
    def __init__(self):
        self.synonyms = {
            'great': 'exceptional', 'good': 'superior', 'best': 'top-tier',
            'durable': 'long-lasting', 'strong': 'robust', 'quality': 'premium',
            'amazing': 'remarkable', 'perfect': 'ideal', 'easy': 'effortless',
            'simple': 'straightforward', 'modern': 'contemporary', 'classic': 'timeless',
            'beautiful': 'exquisite', 'nice': 'fantastic', 'cool': 'stylish',
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
    # Shopify URL handle generator
    handle = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    # Truncate if too long (Shopify max 255 chars)
    if len(handle) > 200:
        handle = handle[:200].rsplit('-', 1)[0]
    return handle

# ---------- IMAGE EDITOR ----------
def edit_image(img_data, filename):
    try:
        img = Image.open(BytesIO(img_data))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        angle = random.uniform(-2.5, 2.5)
        img = img.rotate(angle, expand=False, fillcolor=(255, 255, 255))
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(random.uniform(0.92, 1.08))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(random.uniform(0.95, 1.05))
        img = ImageOps.expand(img, border=3, fill='white')
        
        new_filename = f"edited_{int(time.time())}_{random.randint(1000,9999)}_{filename.split('/')[-1].split('?')[0]}"
        if not new_filename.lower().endswith(('.jpg', '.jpeg')):
            new_filename = new_filename.rsplit('.', 1)[0] + '.jpg'
        
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=85, optimize=True)
        buffer.seek(0)
        return new_filename, buffer.getvalue()
    except Exception as e:
        try:
            new_filename = f"edited_{int(time.time())}_{random.randint(1000,9999)}_{filename.split('/')[-1].split('?')[0]}"
            if not new_filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                new_filename = new_filename.rsplit('.', 1)[0] + '.jpg'
            return new_filename, img_data
        except:
            return None, None

# ---------- SHOPIFY SCRAPER ----------
def scrape_product(url, session, edit_images):
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
    base_url = f"{resp.url.split('/')[0]}//{resp.url.split('/')[2]}"
    product_data = {}
    
    # Parse JSON-LD
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

    # ----- 1. TITLE (ORIGINAL) -----
    title = product_data.get('name') or (soup.find('h1').get_text(strip=True) if soup.find('h1') else None)
    if not title:
        og_title = soup.find('meta', property='og:title')
        title = og_title.get('content') if og_title else url.split('/')[-1].replace('-', ' ')

    # ----- 2. DESCRIPTION (ENHANCE) -----
    raw_desc = product_data.get('description') or ''
    if not raw_desc:
        desc_meta = soup.find('meta', attrs={'name': 'description'})
        raw_desc = desc_meta.get('content') if desc_meta else ''
    if not raw_desc or len(raw_desc) < 20:
        og_desc = soup.find('meta', property='og:description')
        raw_desc = og_desc.get('content') if og_desc else title

    rewriter = SmartRewriter()
    long_desc = rewriter.enhance_description(raw_desc, title)

    # ----- 3. PRICE -----
    price = safe_get_offer_price(product_data.get('offers'))
    if not price:
        price_span = soup.find('span', {'class': re.compile(r'price|amount|sale-price')})
        if price_span:
            match = re.search(r'[\d,]+\.?\d*', price_span.get_text())
            price = match.group() if match else '0'
        else: price = '0'

    # ----- 4. SKU (REGENERATE) -----
    sku_raw = safe_get_sku(product_data.get('sku'))
    if not sku_raw:
        sku_span = soup.find('span', {'class': re.compile(r'sku|id|model')})
        sku_raw = sku_span.get_text(strip=True) if sku_span else f"OLD-{random.randint(1000,9999)}"
    rand_suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=4))
    parent_sku = f"CUSTOM-{rand_suffix}-{sku_raw}"

    # ----- 5. IMAGES (FETCH + OPTIONAL EDIT) -----
    raw_image_urls = []
    if product_data.get('image'):
        if isinstance(product_data['image'], list): raw_image_urls.extend(product_data['image'])
        else: raw_image_urls.append(product_data['image'])
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'): raw_image_urls.append(og_img.get('content'))
    for img in soup.find_all('img'):
        src = img.get('data-src') or img.get('src')
        if src and not src.endswith('.svg') and 'logo' not in src.lower():
            full_url = urljoin(base_url, src)
            if full_url not in raw_image_urls: raw_image_urls.append(full_url)
    raw_image_urls = [im for im in raw_image_urls if im.startswith('http')][:10]

    image_zip_data = {}
    processed_image_urls = []
    
    if edit_images:
        for img_url in raw_image_urls:
            try:
                img_resp = session.get(img_url, timeout=15)
                if img_resp.status_code == 200:
                    new_name, edited_data = edit_image(img_resp.content, img_url)
                    if new_name and edited_data:
                        image_zip_data[new_name] = edited_data
                        processed_image_urls.append(new_name)
                    else:
                        processed_image_urls.append(img_url)
            except Exception:
                processed_image_urls.append(img_url)
    else:
        processed_image_urls = raw_image_urls
    
    images_str = ', '.join(processed_image_urls) if processed_image_urls else ''

    # ----- 6. CATEGORY, VENDOR, TAGS -----
    category_str = format_category(soup)
    vendor = "Imported Vendor"
    tags = "Imported"
    if soup.find('meta', attrs={'name': 'author'}):
        vendor = soup.find('meta', attrs={'name': 'author'}).get('content', vendor)
    
    # ----- 7. VARIATIONS (ATTRIBUTE DETECTION) -----
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

    # ----- 8. BUILD SHOPIFY ROWS -----
    handle = generate_handle(title)
    
    # Option names (parent level)
    opt1_name = opt2_name = opt3_name = ''
    if variations_data:
        attr_names = set()
        for var in variations_data:
            attr_names.update(var['attrs'].keys())
        attr_names = sorted(list(attr_names))
        if len(attr_names) > 0: opt1_name = attr_names[0]
        if len(attr_names) > 1: opt2_name = attr_names[1]
        if len(attr_names) > 2: opt3_name = attr_names[2]

    # ---- PARENT ROW ----
    parent_row = {
        'Title': title,
        'URL handle': handle,
        'Description': long_desc,
        'Vendor': vendor,
        'Product category': category_str,
        'Type': 'Graphic shirt' if 'shirt' in title.lower() else 'Clothing',  # Generic fallback
        'Tags': tags,
        'Published on online store': 'TRUE',
        'Status': 'active',
        'SKU': '',  # SKU parent pe empty
        'Barcode': '',
        'Option1 name': opt1_name,
        'Option1 value': '',  # Parent pe empty
        'Option1 Linked To': 'Option1 name' if opt1_name else '',
        'Option2 name': opt2_name,
        'Option2 value': '',
        'Option2 Linked To': 'Option2 name' if opt2_name else '',
        'Option3 name': opt3_name,
        'Option3 value': '',
        'Option3 Linked To': 'Option3 name' if opt3_name else '',
        'Price': '',  # Parent pe empty
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
        'Product image URL': images_str,
        'Image position': '1',
        'Image alt text': title,
        'Variant image URL': '',
        'Gift card': 'FALSE',
        'SEO title': title,
        'SEO description': long_desc[:300],
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
    results = [parent_row]

    # ---- VARIATION ROWS (CHILDREN) ----
    if variations_data:
        for idx, var in enumerate(variations_data):
            var_sku = f"{parent_sku}-{var.get('sku', random.randint(100,999))}"
            var_price = var.get('price', price)
            var_attrs = var['attrs']
            
            attr1_val = list(var_attrs.values())[0] if len(var_attrs) > 0 else ''
            attr2_val = list(var_attrs.values())[1] if len(var_attrs) > 1 else ''
            attr3_val = list(var_attrs.values())[2] if len(var_attrs) > 2 else ''

            # Variation Image (if specific)
            var_img = var.get('image', '')
            var_img_url = ''
            if edit_images and var_img:
                try:
                    img_resp = session.get(var_img, timeout=15)
                    if img_resp.status_code == 200:
                        new_name, edited_data = edit_image(img_resp.content, var_img)
                        if new_name and edited_data:
                            image_zip_data[new_name] = edited_data
                            var_img_url = new_name
                except:
                    var_img_url = var_img
            if not var_img_url:
                var_img_url = ''  # Leave blank, Shopify will use parent images

            variant_row = {
                'Title': '',  # Empty for variants
                'URL handle': handle,  # Same as parent (linking)
                'Description': '',  # Empty for variants
                'Vendor': '',  # Empty for variants
                'Product category': '',  # Empty for variants
                'Type': '',
                'Tags': '',
                'Published on online store': 'TRUE',
                'Status': 'active',
                'SKU': var_sku,
                'Barcode': random.randint(1000000000, 9999999999),
                'Option1 name': '',  # Empty for variants
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
                'Product image URL': '',  # Empty for variants (parent handles main images)
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
            results.append(variant_row)
    
    # If no variations, we just have 1 row (simple product).
    # The parent row already has SKU and Price empty. We need to fill them for simple product.
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

# ---------- STREAMLIT UI ----------
st.title("🛒 SHOPIFY ULTIMATE CSV GENERATOR")
st.markdown("**Exact Shopify Format | Image Edit Toggle | Original Names**")

with st.expander("📌 SHOPIFY FEATURES", expanded=True):
    st.write("""
    - ✅ **Exact Shopify Columns** (as per sample).
    - ✅ **Parent + Variations** via `URL handle` linking.
    - ✅ **Image Edit Toggle**:
        - **ON**: Edited images (Mirror, Rotate, Brightness, Border) → CSV + ZIP.
        - **OFF**: Original images → Only CSV.
    - ✅ **SEO Title & Description** auto-filled.
    - ✅ **SKU Regeneration** to avoid clashes.
    - ✅ **Anti-Block** (Rotating User-Agents + delay).
    """)

urls_input = st.text_area("🔗 Paste Product URLs (Max 20-30 per batch):", height=120)

col1, col2 = st.columns(2)
with col1:
    edit_images = st.checkbox("🖌️ Edit Images (Avoid Duplicates)", value=False)
with col2:
    base_url = st.text_input("🌐 Base URL (Required if Edit ON):", 
                             placeholder="https://domain.com/wp-content/uploads/",
                             help="Example: https://demosite3.localserver360.com/wp-content/uploads/")

# ---------- EXACT SHOPIFY COLUMNS (FROM SAMPLE) ----------
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

if st.button("🚀 Generate Shopify CSV ( + ZIP if Edit ON )", type="primary"):
    if not urls_input.strip():
        st.error("❌ Kuch URLs toh daalo!")
    else:
        urls = [u.strip() for u in re.split(r'[,\s]+', urls_input) if u.strip().startswith('http')]
        if not urls:
            st.error("❌ Valid URL nahi mili.")
        else:
            # Reset State
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
            
            session = requests.Session()
            total_urls = len(urls)
            
            for idx, url in enumerate(urls):
                status_text.text(f"⏳ Processing {idx+1}/{total_urls} (Edit: {'ON' if edit_images else 'OFF'})...")
                results, image_data, error = scrape_product(url, session, edit_images)
                if results:
                    all_rows.extend(results)
                    if image_data:
                        all_image_data.update(image_data)
                else:
                    failed_urls.append(url)
                progress_bar.progress((idx + 1) / total_urls)
                time.sleep(random.uniform(4.0, 6.5))
            
            progress_bar.progress(1.0)
            status_text.text("✅ Complete!")
            
            if not all_rows:
                st.error("❌ Koi product scrape nahi ho saka.")
                st.stop()
            
            # Apply Base URL to Images (sirf tab jab Edit ON ho)
            if edit_images and base_url:
                for row in all_rows:
                    # Parent Product Image
                    img_col = row.get('Product image URL', '')
                    if img_col:
                        imgs = img_col.split(', ')
                        new_imgs = []
                        for img in imgs:
                            if not img.startswith('http'):
                                new_imgs.append(f"{base_url.rstrip('/')}/{img.lstrip('/')}")
                            else:
                                new_imgs.append(img)
                        row['Product image URL'] = ', '.join(new_imgs)
                    
                    # Variant Image
                    var_img = row.get('Variant image URL', '')
                    if var_img and not var_img.startswith('http'):
                        row['Variant image URL'] = f"{base_url.rstrip('/')}/{var_img.lstrip('/')}"

            df = pd.DataFrame(all_rows, columns=SHOPIFY_COLUMNS)
            for col in SHOPIFY_COLUMNS:
                if col not in df.columns: df[col] = ''
            df = df[SHOPIFY_COLUMNS]
            
            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_data = csv_buffer.getvalue()
            
            # ZIP prepare
            zip_buffer = BytesIO()
            has_zip = False
            zip_ready = None
            if edit_images and all_image_data:
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filename, binary_data in all_image_data.items():
                        zip_file.writestr(filename, binary_data)
                zip_buffer.seek(0)
                zip_ready = zip_buffer.getvalue()
                has_zip = True

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
                file_name=f"edited_images_{int(time.time())}.zip",
                mime="application/zip",
                use_container_width=True,
                key="zip_download"
            )
        else:
            if edit_images:
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

st.caption("🛒 Shopify Mode: Exact 55+ Columns | Toggle Image Edit | Variant Linking")
