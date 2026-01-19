from flask import Flask, request, render_template, send_file, make_response
import requests
import re
from bs4 import BeautifulSoup as par
import zipfile
import io
import json  # <--- Tambahan Import Penting

app = Flask(__name__)

# --- HEADERS ---
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

def clean_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

def scrape_engine(pages, config_filter, category, zip_obj):
    ses = get_session()
    tas_uid = []
    
    # 1. Scrape UID
    for page in range(1, pages + 1):
        try:
            url = f'https://sfile.co/{category}?page={page}'
            resp = ses.get(url).text
            source = re.findall('<a href="(.*?)"', str(resp))
            for link_url in source:
                id_match = re.search(r'https://sfile.co/(\w+)', str(link_url))
                if id_match:
                    uid = id_match.group(1)
                    if uid not in tas_uid and uid != category:
                        tas_uid.append(uid)
        except:
            continue

    # 2. Download & Filter
    processed_files_list = [] # List untuk menyimpan nama file sukses
    processed_names_set = set() # Set untuk cek duplikat nama

    for uid in tas_uid:
        try:
            url_file = f'https://sfile.co/{uid}'
            resp_file = ses.get(url_file)
            get = par(resp_file.text, 'html.parser')
            
            title_tag = re.search('<title>(.*?)</title>', str(get))
            if not title_tag: continue
            title = title_tag.group(1)

            if config_filter.lower() in title.lower():
                link_tag = re.search('href="(.*?)" id="download"', str(get))
                if not link_tag: continue
                link_download_page = link_tag.group(1)
                
                gett = ses.get(link_download_page, cookies=ses.cookies.get_dict()).text
                direct_match = re.search(r'downloadButton.href = "(.*?)";', str(gett))
                
                if direct_match:
                    direct_link = direct_match.group(1).replace(r'\/', '/')
                    file_content = ses.get(direct_link).content
                    
                    clean_name = clean_filename(title.replace(' - sfile.co', ''))
                    
                    final_name = clean_name
                    counter = 1
                    while final_name in processed_names_set:
                        final_name = f"{clean_name} ({counter})" # Tambah angka jika kembar
                        counter += 1
                    
                    # Tambahkan ekstensi manual jika hilang (opsional, tapi aman)
                    if not "." in final_name[-5:]: 
                         final_name += f".{config_filter}"

                    processed_names_set.add(final_name)
                    processed_files_list.append(final_name) # Simpan ke list laporan

                    zip_obj.writestr(final_name, file_content)
                    
        except:
            continue

    return processed_files_list

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download_zip', methods=['POST'])
def download_zip_api():
    try:
        pages = int(request.form.get('pages', 1))
        config = request.form.get('config', '').strip()
        category = request.form.get('category', 'latest')
        
        if not config: return "Config filter wajib diisi!", 400

        mem_zip = io.BytesIO()
        
        with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # scrape_engine sekarang mengembalikan LIST file, bukan cuma angka
            success_files = scrape_engine(pages, config, category, zf)

        mem_zip.seek(0)
        total_files = len(success_files)
        
        if total_files == 0:
            return "Tidak ada file ditemukan dengan config tersebut.", 404

        filename = f"Sfile-{config}-{total_files}Files.zip"
        
        response = make_response(send_file(
            mem_zip,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        ))
        
        # --- KIRIM DATA KE FRONTEND ---
        # 1. Jumlah File
        response.headers['X-File-Count'] = str(total_files)
        
        # 2. Daftar Nama File (Dikirim sebagai JSON String di Header)
        # Limit header size: Ambil max 50 nama file agar header tidak overflow
        json_list = json.dumps(success_files[:50]) 
        response.headers['X-File-List'] = json_list
        
        return response

    except Exception as e:
        return f"Server Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, port=8000, threaded=True)
