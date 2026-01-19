from flask import Flask, request, render_template, send_file
import requests
import re
from bs4 import BeautifulSoup as par
import zipfile
import io

app = Flask(__name__)

# --- CONFIG CONSTANTS ---
HEADERS_SFILE = {
    'authority': 'sfile.co',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
    'referer': 'https://sfile.co/',
    'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
}

def get_session():
    s = requests.Session()
    s.headers.update(HEADERS_SFILE)
    return s

def clean_and_unique_filename(filename, config_ext, existing_names):
    """
    Membersihkan nama file, memastikan ekstensi benar, dan menangani duplikat.
    Contoh: "File.hc" -> "File (1).hc" jika sudah ada.
    """
    # Format ekstensi target
    ext = f".{config_ext}".lower() if not config_ext.startswith('.') else config_ext.lower()
    
    # 1. Hapus suffix bawaan sfile
    base = filename.replace(' - sfile.co', '')
    
    # 2. Hapus karakter ilegal
    base = re.sub(r'[\\/*?:"<>|]', "", base)
    
    # 3. Hapus ekstensi target jika sudah ada di nama (biar bersih)
    # Mencegah .hc.hc
    pattern = re.compile(re.escape(ext), re.IGNORECASE)
    base = pattern.sub("", base)
    
    # 4. Trim spasi
    base = base.strip()
    
    # 5. Rakit nama file
    final_name = f"{base}{ext}"
    
    # 6. Cek Duplikat (Auto Increment)
    counter = 1
    root_name = base
    while final_name in existing_names:
        final_name = f"{root_name} ({counter}){ext}"
        counter += 1
        
    return final_name

def scrape_worker(user_pages, config_filter, target_category, zip_obj):
    ses = get_session()
    local_tas = set()     # Cache ID agar tidak download ulang file sama di sesi ini
    zip_filenames = set() # Cache Nama File dalam ZIP agar tidak bentrok
    files_added = 0

    def process_uid(uid):
        nonlocal files_added
        url = f'https://sfile.co/{uid}'
        try:
            resp = ses.get(url)
            get = par(resp.text, 'html.parser')
            
            # Ambil Judul
            title_tag = re.search('<title>(.*?)</title>', str(get))
            if not title_tag: return
            title = title_tag.group(1)

            # Ambil Link Download
            link_tag = re.search('href="(.*?)" id="download"', str(get))
            if not link_tag: return
            link = link_tag.group(1)

            # Filter Config
            if config_filter.lower() in title.lower():
                # Masuk halaman download
                gett = ses.get(link, cookies=ses.cookies.get_dict()).text
                direct_match = re.search(r'downloadButton.href = "(.*?)";', str(gett))
                
                if direct_match:
                    dl_link = direct_match.group(1).replace(r'\/', '/')
                    
                    # Download Konten File
                    file_content = ses.get(dl_link).content
                    
                    # Generate Nama Unik
                    final_name = clean_and_unique_filename(title, config_filter, zip_filenames)
                    
                    # Catat nama file agar tidak dipakai lagi
                    zip_filenames.add(final_name)
                    
                    # Tulis ke ZIP
                    zip_obj.writestr(final_name, file_content)
                    files_added += 1
        except Exception:
            pass # Skip jika gagal download satu file

    # Loop Halaman
    for page in range(1, user_pages + 1):
        try:
            url_target = f'https://sfile.co/{target_category}?page={page}'
            resp_text = ses.get(url_target).text
            links = re.findall('<a href="(.*?)"', str(resp_text))
            
            for url in links:
                id_match = re.search(r'https://sfile.co/(\w+)', str(url))
                if id_match:
                    uid = id_match.group(1)
                    # Pastikan bukan duplikat dan bukan link kategori
                    if uid not in local_tas and uid != target_category:
                        local_tas.add(uid)
                        if 'latest' not in uid and 'trends' not in uid: 
                            process_uid(uid)
        except:
            continue

    return files_added

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download_zip', methods=['POST'])
def download_zip_api():
    try:
        # Ambil Input
        try:
            pages = int(request.form.get('pages', 1))
        except ValueError:
            return "Input halaman harus angka", 400

        config = request.form.get('config', '').strip()
        category = request.form.get('category', 'latest') # Default latest
        
        if not config: return "Config filter wajib diisi!", 400
        
        # Siapkan Buffer ZIP di Memory
        mem_zip = io.BytesIO()
        
        # Mulai Proses
        with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            count = scrape_worker(pages, config, category, zf)

        mem_zip.seek(0)
        
        if count == 0:
            return "Tidak ada file ditemukan. Coba tambah halaman atau ganti config.", 404

        # Kirim File
        return send_file(
            mem_zip,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"Pack-{config}-{category}.zip"
        )

    except Exception as e:
        return f"Server Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, port=9000, threaded=True)
