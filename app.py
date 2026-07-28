def scrape_shopify_product(url, session, config):
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

    # ---------- IMAGE COLLECTION (Lazy Load Support) ----------
    raw_image_urls = []
    
    # JSON-LD se images
    if product_data.get('image'):
        if isinstance(product_data['image'], list):
            raw_image_urls.extend(product_data['image'])
        else:
            raw_image_urls.append(product_data['image'])
    
    # OG image
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        raw_image_urls.append(og_img.get('content'))
    
    # HTML img tags (lazy load support)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
        if src and not src.endswith('.svg') and 'logo' not in src.lower():
            full_url = urljoin(base_url_domain, src)
            if full_url not in raw_image_urls:
                raw_image_urls.append(full_url)
    
    raw_image_urls = [im for im in raw_image_urls if im.startswith('http')][:5]

    # ---------- Process Images (Edit OR Original) ----------
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
    
    main_image = processed_image_urls[0] if processed_image_urls else ''
    additional_images = processed_image_urls[1:] if len(processed_image_urls) > 1 else []

    category_str = format_category(soup)
    vendor = "Imported Vendor"
    if soup.find('meta', attrs={'name': 'author'}):
        vendor = soup.find('meta', attrs={'name': 'author'}).get('content', vendor)
    
    tags = "Imported"
    handle = generate_handle(title)
    
    # ---------- EXTRACT VARIANTS ----------
    offers = product_data.get('offers')
    variations_data = []
    
    if isinstance(offers, list) and len(offers) > 1:
        for idx, offer in enumerate(offers):
            if isinstance(offer, dict):
                var_sku = offer.get('sku', f'VAR-{idx+1}')
                var_price = offer.get('price', price)
                var_attrs = {}
                
                # Extract attributes (Size, Color, etc.)
                if 'size' in offer:
                    var_attrs['Size'] = offer['size']
                if 'color' in offer:
                    var_attrs['Color'] = offer['color']
                # If no explicit attr, create generic option
                if not var_attrs:
                    var_attrs['Option'] = f'Variant {idx+1}'
                
                # 🔥 FIX: Extract variation-specific image
                var_img = offer.get('image', '')
                
                # If JSON-LD doesn't have image, try to find from HTML
                if not var_img:
                    # Try to find image associated with this variant (if color/size matches)
                    color_val = var_attrs.get('Color', '')
                    size_val = var_attrs.get('Size', '')
                    
                    # Search HTML for img with alt text containing color/size
                    for img in soup.find_all('img'):
                        alt = img.get('alt', '').lower()
                        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                        if src:
                            # Check if alt text contains variant attribute
                            if (color_val and color_val.lower() in alt) or (size_val and size_val.lower() in alt):
                                full_url = urljoin(base_url_domain, src)
                                if full_url.startswith('http') and full_url not in [v.get('image') for v in variations_data]:
                                    var_img = full_url
                                    break
                
                variations_data.append({
                    'sku': var_sku,
                    'price': var_price,
                    'attrs': var_attrs,
                    'image': var_img  # Now this will be different for each variant if available
                })

    # ---------- OPTION NAMES ----------
    opt1_name = opt2_name = opt3_name = ''
    if variations_data:
        attr_names = set()
        for var in variations_data:
            attr_names.update(var['attrs'].keys())
        attr_names = sorted(list(attr_names))
        if len(attr_names) > 0: opt1_name = attr_names[0]
        if len(attr_names) > 1: opt2_name = attr_names[1]
        if len(attr_names) > 2: opt3_name = attr_names[2]

    # ---------- PARENT ROW ----------
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

    # ---------- ADDITIONAL IMAGE ROWS ----------
    image_rows = []
    for idx, img_url in enumerate(additional_images, start=2):
        img_row = {col: '' for col in SHOPIFY_COLUMNS}
        img_row['URL handle'] = handle
        img_row['Product image URL'] = img_url
        img_row['Image position'] = str(idx)
        image_rows.append(img_row)

    # ---------- VARIANT ROWS (WITH VARIANT IMAGES) ----------
    variant_rows = []
    if variations_data:
        for idx, var in enumerate(variations_data):
            var_sku = f"{parent_sku}-{var.get('sku', random.randint(100,999))}"
            var_price = var.get('price', price)
            var_attrs = var['attrs']
            attr1_val = list(var_attrs.values())[0] if len(var_attrs) > 0 else ''
            attr2_val = list(var_attrs.values())[1] if len(var_attrs) > 1 else ''
            attr3_val = list(var_attrs.values())[2] if len(var_attrs) > 2 else ''

            # 🔥 FIX: Process variant image separately
            var_img_original = var.get('image', '')
            var_img_url = ''
            
            if var_img_original:
                if config.get('edit_images', False):
                    try:
                        img_resp = session.get(var_img_original, timeout=15)
                        if img_resp.status_code == 200:
                            new_name, edited_data = edit_image(img_resp.content, var_img_original, config)
                            if new_name and edited_data:
                                image_zip_data[new_name] = edited_data
                                var_img_url = new_name
                            else:
                                var_img_url = var_img_original
                    except:
                        var_img_url = var_img_original
                else:
                    var_img_url = var_img_original

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
                'Variant image URL': var_img_url,  # 🔥 Now different for each variant
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
    
    # If no variants, simple product
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

    final_rows = [parent_row] + image_rows + variant_rows
    return final_rows, image_zip_data, None
