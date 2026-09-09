import feedparser
from groq import Groq
import requests
import os
import json
import time
import re
from datetime import datetime, timedelta

# ========== НАСТРОЙКИ ==========
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@derma_cosmo_facts"
CONTACT_EMAIL = "cosmetology-bot@example.com"

MEMORY_FILE = "posted_news.json"
groq_client = Groq(api_key=GROQ_API_KEY)

# ========== ИСТОЧНИКИ (16 сайтов + 4 TG) ==========
SITE_FEEDS = [
    # 🌍 Западные
    'https://www.sciencedaily.com/rss/health_medicine/skin_care.xml',
    'https://www.healio.com/rss/dermatology',
    # 🇰🇷 Корея
    'https://www.bosa.co.kr/rss/allArticle.xml',
    'https://m.koreaherald.com/rss/newsAll',
    'https://en.yna.co.kr/RSS/news.xml',
    # 🇨🇳 Китай
    'http://www.chinadaily.com.cn/rss/lifestyle_rss.xml',
    'https://www.scmp.com/rss/2/feed',
    'https://weekly.chinacdc.cn/rss/current.xml',
    # 🇷🇺 Россия
    'https://nplus1.ru/rss',
    'https://elementy.ru/rss/news',
    'https://scientificrussia.ru/rss',
    # 🔬 Научные API (псевдо-источники)
    'crossref:0140-6736:skin OR dermatology OR cosmetic OR aesthetic OR acne OR psoriasis',
    'pubmed:dermatology OR cosmetic OR aesthetic OR skin OR botulinum OR filler',
    'semanticscholar:dermatology cosmetic skin aesthetic',
    'medrxiv',
    'europepmc:dermatology OR cosmetic OR aesthetic OR skin',
]

TG_FEEDS = [
    'https://tg.i-c-a.su/rss/chatkosmetologa',
    'https://tg.i-c-a.su/rss/d_dermatology',
    'https://tg.i-c-a.su/rss/cosmetologich',
    'https://tg.i-c-a.su/rss/cosmetologiainside',
]

RELEVANT_KEYWORDS = [
    'skin', 'dermatology', 'cosmetic', 'aesthetic', 'acne',
    'collagen', 'wrinkle', 'peptide', 'exosome', 'laser',
    'psoriasis', 'eczema', 'melanoma', 'rosacea', 'pigment',
    'botox', 'botulinum', 'filler', 'rejuvenation', 'aging',
    'sunscreen', 'moisturizer', 'skincare', 'beauty',
    'vitiligo', 'atopic', 'alopecia', 'dermatitis', 'pruritus',
    'кожа', 'косметолог', 'дерматолог', 'эстетическ', 'акне',
    'псориаз', 'морщины', 'коллаген', 'ботокс', 'филлер',
    'пилинг', 'лазер', 'омоложение', 'дерматит', 'розацеа',
    '피부', '화장품', '뷰티', '미용', '성형', '피부과',
    '보톡스', '필러', '레이저', '콜라겐', '엑소좀', '여드름',
    '아토피', '탈모', '주름', '색소', '자외선',
    '皮肤', '美容', '医美', '化妆品', '整形', '激光',
    '胶原', '痤疮', '湿疹', '护肤', '美白',
]

# ========== ПАМЯТЬ ==========
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return {'posted_links': data, 'posted_titles': [], 'site_index': 0, 'tg_index': 0, 'last_source': 'tg'}
            if 'posted_titles' not in data: data['posted_titles'] = []
            if 'last_source' not in data: data['last_source'] = 'tg'
            if 'site_index' not in data: data['site_index'] = 0
            if 'tg_index' not in data: data['tg_index'] = 0
            return data
    return {'posted_links': [], 'posted_titles': [], 'site_index': 0, 'tg_index': 0, 'last_source': 'tg'}

def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def normalize_title(title):
    title = title.lower().strip()
    title = re.sub(r'[.!?\s]+$', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title

# ========== 🛡️ ОЧИСТКА ОТ ИЕРОГЛИФОВ ==========
def clean_post_text(text):
    if not text:
        return text
    cjk_pattern = re.compile(
        "["
        "\u2E80-\u2EFF\u2F00-\u2FDF\u3040-\u309F\u30A0-\u30FF"
        "\u3130-\u318F\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF"
        "\uF900-\uFAFF\uFE30-\uFE4F\U00020000-\U0002A6DF"
        "]+", re.UNICODE
    )
    text = cjk_pattern.sub('', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r' +([.,!?;:])', r'\1', text)
    text = re.sub(r'<b>\s*</b>', '', text)
    return text.strip()

# ========== 🎨 ФОРМАТИРОВАНИЕ СТРУКТУРЫ ==========
def format_post(text):
    if not text:
        return text
    hashtags = re.findall(r'#[A-Za-zА-Яа-яЁё0-9_]+', text)
    seen = set()
    unique_tags = []
    for t in hashtags:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)
    text_no_tags = re.sub(r'#[A-Za-zА-Яа-яЁё0-9_]+', '', text)
    lines = [ln.strip() for ln in text_no_tags.split('\n')]
    lines = [re.sub(r'\s{2,}', ' ', ln) for ln in lines if ln.strip()]
    if not lines:
        return ' '.join(unique_tags)
    title = lines[0]
    title = re.sub(r'^<b>\s*', '', title)
    title = re.sub(r'\s*</b>$', '', title)
    title = f'<b>{title.strip()}</b>'
    body = '\n\n'.join(lines[1:]).strip()
    parts = [title]
    if body:
        parts.append(body)
    if unique_tags:
        parts.append(' '.join(unique_tags))
    return '\n\n'.join(parts)

# ========== ЧТЕНИЕ RSS ==========
def clean_html(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return text.strip()

def get_news_from_rss(feed_url, max_items=10):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        feed = feedparser.parse(feed_url, request_headers=headers)
        source_title = feed.feed.get('title', 'Unknown')
        status = getattr(feed, 'status', 'N/A')
        print(f"🔍 {source_title} (Status: {status}): найдено {len(feed.entries)} записей")

        news_list = []
        for entry in feed.entries[:max_items]:
            raw = entry.get('summary', entry.get('description', ''))
            summary = clean_html(raw)
            summary = (summary[:1500] + '...') if len(summary) > 1500 else summary
            news_list.append({
                'title': clean_html(entry.title),
                'summary': summary,
                'link': entry.link,
                'source': source_title,
                'feed_url': feed_url,
            })
        return news_list
    except Exception as e:
        print(f"⚠️ Ошибка чтения {feed_url}: {e}")
        return []

# ========== 🔬 НАУЧНЫЕ API ==========
def fetch_abstract_from_openalex(doi):
    """Добирает аннотацию из OpenAlex по DOI."""
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        resp = requests.get(url, params={"mailto": CONTACT_EMAIL}, timeout=10)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        inv = data.get("abstract_inverted_index")
        if not inv:
            return ""
        positions = []
        for word, idxs in inv.items():
            for i in idxs:
                positions.append((i, word))
        positions.sort()
        return " ".join(w for _, w in positions)
    except Exception:
        return ""

def get_news_from_crossref(issn, query, max_items=6):
    """Crossref API — свежие статьи журнала по ISSN."""
    try:
        url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "filter": f"issn:{issn},type:journal-article",
            "sort": "published",
            "order": "desc",
            "rows": max_items,
            "mailto": CONTACT_EMAIL,
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}

        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code != 200:
            print(f"⚠️ Crossref вернул статус {resp.status_code}")
            return []

        items = resp.json().get("message", {}).get("items", [])
        source_name = "The Lancet" if issn == "0140-6736" else f"Journal {issn}"
        print(f"🔍 {source_name} (Crossref): найдено {len(items)} записей")

        news_list = []
        for n, item in enumerate(items):
            title = item.get("title", [""])[0] if item.get("title") else ""
            if not title:
                continue
            doi = item.get("DOI", "")
            link = f"https://doi.org/{doi}"

            authors = []
            for a in item.get("author", [])[:3]:
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                if name:
                    authors.append(name)
            authors_str = ", ".join(authors) if authors else "не указаны"

            date_parts = item.get("published", {}).get("date-parts", [[None]])[0]
            year = date_parts[0] if date_parts and date_parts[0] else "б. г."

            abstract = re.sub(r'<[^>]+>', '', item.get("abstract", "") or "").strip()
            if not abstract and n < 4 and doi:
                abstract = fetch_abstract_from_openalex(doi)
                time.sleep(0.3)

            if abstract:
                summary = (abstract[:1500] + '...') if len(abstract) > 1500 else abstract
            else:
                summary = f"Научная статья в журнале {source_name}. Тема: {title}. Авторы: {authors_str}. Год: {year}."

            summary += f" | Авторы: {authors_str}. Источник: {source_name}, {year}."

            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': source_name,
                'feed_url': f"crossref:{issn}",
            })
        return news_list
    except Exception as e:
        print(f"⚠️ Ошибка Crossref: {e}")
        return []

def get_news_from_pubmed(query, max_items=8):
    """PubMed E-utilities — золотой стандарт медицинской литературы."""
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": f"({query}) AND (free full text[SB] OR open access[Filter])",
            "retmax": max_items,
            "sort": "pub_date",
            "retmode": "json",
            "email": CONTACT_EMAIL,
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"⚠️ PubMed вернул статус {resp.status_code}")
            return []
        
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            print("🔍 PubMed: найдено 0 записей")
            return []
        
        url_summ = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        params_summ = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
            "email": CONTACT_EMAIL,
        }
        resp2 = requests.get(url_summ, params=params_summ, headers=headers, timeout=15)
        if resp2.status_code != 200:
            return []
        
        docs = resp2.json().get("result", {})
        print(f"🔍 PubMed: найдено {len(ids)} записей")
        
        news_list = []
        for pmid in ids:
            doc = docs.get(pmid, {})
            if not doc:
                continue
            title = doc.get("title", "")
            if not title:
                continue
            authors = ", ".join(a.get("name", "") for a in doc.get("authors", [])[:3]) or "не указаны"
            pubdate = doc.get("pubdate", "")
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            summary = f"Научная статья в PubMed. PMID: {pmid}. Авторы: {authors}. Опубликовано: {pubdate}."
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': 'PubMed',
                'feed_url': 'pubmed:dermatology',
            })
        return news_list
    except Exception as e:
        print(f"⚠️ Ошибка PubMed: {e}")
        return []

def get_news_from_semantic_scholar(query, max_items=6):
    """Semantic Scholar — AI-поиск по научным статьям с TLDR."""
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": max_items,
            "fields": "title,abstract,authors,year,url,tldr,externalIds",
            "year": "2024-2026",
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 429:
            print("⚠️ Semantic Scholar: rate limit, пропуск")
            return []
        if resp.status_code != 200:
            print(f"⚠️ Semantic Scholar вернул статус {resp.status_code}")
            return []
        
        items = resp.json().get("data", [])
        print(f"🔍 Semantic Scholar: найдено {len(items)} записей")
        
        news_list = []
        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            
            abstract = item.get("abstract") or ""
            tldr = item.get("tldr", {}).get("text", "") if item.get("tldr") else ""
            
            authors = ", ".join(a.get("name", "") for a in (item.get("authors") or [])[:3]) or "не указаны"
            year = item.get("year", "")
            
            doi = item.get("externalIds", {}).get("DOI")
            link = f"https://doi.org/{doi}" if doi else (item.get("url") or "")
            
            summary = tldr or abstract or f"Научная статья. Авторы: {authors}. Год: {year}."
            summary = (summary[:1500] + '...') if len(summary) > 1500 else summary
            summary += f" | Авторы: {authors}. Год: {year}."
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': 'Semantic Scholar',
                'feed_url': 'semanticscholar:dermatology',
            })
        return news_list
    except Exception as e:
        print(f"⚠️ Ошибка Semantic Scholar: {e}")
        return []

def get_news_from_medrxiv(max_items=10):
    """medRxiv — свежие медицинские препринты."""
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        
        url = f"https://api.medrxiv.org/details/medrxiv/{start_date}/{end_date}/0"
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            print(f"⚠️ medRxiv вернул статус {resp.status_code}")
            return []
        
        items = resp.json().get("collection", [])
        print(f"🔍 medRxiv: получено {len(items)} препринтов")
        
        news_list = []
        skin_keywords = ['skin', 'dermat', 'cosmetic', 'aesthetic', 'acne', 
                        'psoriasis', 'eczema', 'hair', 'pigment', 'laser',
                        'vitiligo', 'melanoma', 'rosacea']
        
        for item in items[:max_items * 3]:
            title = item.get("title", "")
            if not title:
                continue
            
            category = item.get("category", "").lower()
            abstract = item.get("abstract", "") or ""
            combined = (title + " " + abstract + " " + category).lower()
            
            if not any(kw in combined for kw in skin_keywords):
                continue
            
            doi = item.get("doi", "")
            link = f"https://doi.org/{doi}" if doi else ""
            authors = item.get("authors", "не указаны")
            pub_date = item.get("date", "")
            
            summary = (abstract[:1500] + '...') if len(abstract) > 1500 else abstract
            summary += f" | Авторы: {authors}. Препринт: {pub_date}."
            
            news_list.append({
                'title': f"[Препринт] {title}",
                'summary': summary,
                'link': link,
                'source': 'medRxiv',
                'feed_url': 'medrxiv:dermatology',
            })
            
            if len(news_list) >= max_items:
                break
        
        print(f"🔍 medRxiv после фильтра по теме: {len(news_list)} записей")
        return news_list
    except Exception as e:
        print(f"⚠️ Ошибка medRxiv: {e}")
        return []

def get_news_from_europepmc(query, max_items=6):
    """Europe PMC — европейский аналог PubMed."""
    try:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": max_items,
            "sort": "FIRST_PDATE desc",
            "cursorMark": "*",
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"⚠️ Europe PMC вернул статус {resp.status_code}")
            return []
        
        items = resp.json().get("resultList", {}).get("result", [])
        print(f"🔍 Europe PMC: найдено {len(items)} записей")
        
        news_list = []
        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            
            abstract = item.get("abstractText", "")
            authors = ", ".join(a.get("fullName", "") for a in (item.get("authorList", {}).get("author", [])[:3])) or "не указаны"
            year = item.get("pubYear", "")
            
            pmid = item.get("pmid")
            doi = item.get("doi")
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (f"https://doi.org/{doi}" if doi else "")
            
            summary = (abstract[:1500] + '...') if len(abstract) > 1500 else abstract
            if not summary:
                summary = f"Научная статья. Авторы: {authors}. Год: {year}."
            summary += f" | Авторы: {authors}. Год: {year}."
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': 'Europe PMC',
                'feed_url': 'europepmc:dermatology',
            })
        return news_list
    except Exception as e:
        print(f"⚠️ Ошибка Europe PMC: {e}")
        return []

# ========== СБОР ПО КАТЕГОРИИ ==========
def get_all_news_from_category(feeds, start_index):
    """Round-robin обход всех источников категории."""
    num_feeds = len(feeds)
    if num_feeds == 0:
        return [], 0

    all_news = []
    for i in range(num_feeds):
        idx = (start_index + i) % num_feeds
        feed = feeds[idx]
        print(f"📡 Проверяем источник #{idx+1}: {feed}")
        
        if feed.startswith('crossref:'):
            parts = feed.split(':', 2)
            issn = parts[1]
            query = parts[2] if len(parts) > 2 else "dermatology OR skin"
            news = get_news_from_crossref(issn, query, max_items=6)
        elif feed.startswith('pubmed:'):
            query = feed.split(':', 1)[1]
            news = get_news_from_pubmed(query, max_items=8)
        elif feed.startswith('semanticscholar:'):
            query = feed.split(':', 1)[1]
            news = get_news_from_semantic_scholar(query, max_items=6)
        elif feed == 'medrxiv':
            news = get_news_from_medrxiv(max_items=6)
        elif feed.startswith('europepmc:'):
            query = feed.split(':', 1)[1]
            news = get_news_from_europepmc(query, max_items=6)
        else:
            news = get_news_from_rss(feed, max_items=10)
        
        all_news.extend(news)
        time.sleep(0.5)

    next_index = (start_index + 1) % num_feeds
    return all_news, next_index

# ========== ФИЛЬТРЫ ==========
def is_from_telegram(feed_url):
    return 'tg.i-c-a.su' in feed_url or 'rsshub.app/telegram' in feed_url

def is_relevant(news_item):
    text = (news_item['title'] + ' ' + news_item['summary']).lower()
    return any(kw in text for kw in RELEVANT_KEYWORDS)

# ========== ПРОМПТ 1: САЙТЫ / НАУЧНЫЕ API ==========
def process_site_news(news_item):
    prompt = f"""Ты — нейтральный научный обозреватель Telegram-канала о косметологии и доказательной медицине.
ИСТОЧНИК: {news_item['source']}
ОРИГИНАЛЬНЫЙ ЗАГОЛОВОК: {news_item['title']}
ТЕКСТ: {news_item['summary']}

ВАЖНО — ЯЗЫК:
- Текст может быть на английском, корейском или китайском языке.
- Пиши пост ИСКЛЮЧИТЕЛЬНО НА РУССКОМ.
- Все названия городов и термины переводи на русский (Seoul → Сеул, Beijing → Пекин).
- В финальном тексте НЕ ДОЛЖНО БЫТЬ ни одного иероглифа.

⚠️ ФОРМАТ ВЫВОДА (СТРОГО, с переносами строк):
<b>Заголовок</b>
<ПУСТАЯ СТРОКА>
Основной текст поста (4-8 предложений).
<ПУСТАЯ СТРОКА>
#хэштег1 #хэштег2 #хэштег3

В конце основного текста добавь ссылку: 🔗 <a href="{news_item['link']}">Читать в источнике</a>

⛔ ЗАПРЕЩЕНО:
- Первое лицо: «мы», «я», «у нас», «наш», «в нашей практике». Пиши БЕЗЛИЧНО: «применяется», «используется», «врачи отмечают», «исследование показывает».
- Конкретные клиники, врачи, бренды оборудования и препаратов. Коммерческие названия (Endolift, LASEMAR, i-PRF, Juvederm, Botox, Morpheus8, Dupixent) заменяй на общие термины: «диодный лазер 1470 нм», «PRF-терапия», «ботулотоксин типа А», «гиалуроновый филлер», «ингибитор интерлейкинов IL-4/IL-13».
- Призывы: «обсудите с врачом», «запишитесь», «ваша кожа заслуживает».
- Текст — НЕЙТРАЛЬНЫЙ информационный обзор, НЕ авторская колонка клиники.

ПРАВИЛА:
- Живой язык, без канцеляризмов
- 1-2 тематических эмодзи (🔬 💉 🧬 🌿 📊)
- Научная точность, не выдумывай факты. Если текста мало — пиши короткий пост, не сочиняй детали.

ОТВЕТЬ ТОЛЬКО готовым постом в указанном формате. Без комментариев."""
    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты нейтральный научный обозреватель. Пиши ТОЛЬКО на русском, БЕЗ иероглифов. Никаких «мы», брендов и призывов. Строго соблюдай пустые строки между заголовком, текстом и хэштегами."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq (сайт): {e}")
        return None

# ========== ПРОМПТ 2: TELEGRAM ==========
def process_tg_news(news_item):
    prompt = f"""Ты — нейтральный научный обозреватель Telegram-канала о косметологии.
ТЕКСТ ИСХОДНОГО ПОСТА:
{news_item['summary']}

ЗАДАЧА — выполни ДВА шага:

ШАГ 1: Определи, является ли этот пост РЕКЛАМОЙ.
Реклама — это: продажа курса/вебинара, призыв «запишись/купи», продвижение клиники с адресом/телефоном, промокод, розыгрыш, призыв подписаться на автора.
Если это реклама — ответь ОДНИМ словом: SKIP

ШАГ 2: Если это НЕ реклама, а полезный экспертный контент:

⚠️ ФОРМАТ ВЫВОДА (СТРОГО, с переносами строк):
<b>Заголовок</b>
<ПУСТАЯ СТРОКА>
Основной текст поста (4-8 предложений).
<ПУСТАЯ СТРОКА>
#хэштег1 #хэштег2 #хэштег3

⛔ КРИТИЧЕСКИ ВАЖНО — ЗАПРЕЩЕНО:
1. ЯЗЫК: только русский, НИ ОДНОГО иероглифа. Все иностранные названия переводи (Seoul → Сеул).
2. ЛИЧНОСТЬ: ЗАПРЕЩЕНЫ «мы», «я», «у нас», «наш», «в нашей практике», «в моем опыте». Пиши БЕЗЛИЧНО: «применяется», «используется», «врачи отмечают», «в клинической практике используется».
3. БРЕНДЫ: названия аппаратов (Endolift, LASEMAR, Morpheus8, Sylfirm) → «диодный лазер 1470 нм», «микроигольчатый RF-аппарат»; препараты (Juvederm, Restylane, i-PRF) → «гиалуроновый филлер», «препарат на основе PRF».
4. ПРИЗЫВЫ: никаких «обсудите с врачом», «запишитесь», «ваша кожа заслуживает».
5. ТОН: НЕЙТРАЛЬНЫЙ научный обзор, НЕ реклама клиники и НЕ личное мнение врача.

ПРАВИЛА:
- Живой язык, без канцеляризмов
- 1-2 тематических эмодзи (🔬 💉 🧬 🌿 📊)
- НЕ копируй дословно, переписывай своими словами
- НЕ упоминай источник, НЕ добавляй ссылки

ОТВЕТЬ ТОЛЬКО готовым постом в указанном формате или словом SKIP."""
    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты нейтральный научный обозреватель. Пиши ТОЛЬКО на русском, БЕЗ иероглифов. ЗАПРЕЩЕНЫ «мы», «я», бренды и призывы. Строго соблюдай пустые строки между заголовком, текстом и хэштегами."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )
        result = resp.choices[0].message.content.strip()
        if result.upper().startswith('SKIP'):
            print(f"🚫 Реклама пропущена: {news_item['title'][:40]}...")
            return None
        return result
    except Exception as e:
        print(f"⚠️ Ошибка Groq (TG): {e}")
        return None

# ========== ПОСТИНГ ==========
def post_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "false"}
    try:
        resp = requests.post(url, data=data, timeout=15)
        result = resp.json()
        if result.get('ok'):
            print(f"✅ Опубликовано в {CHANNEL_ID}!")
            return True
        print(f"⚠️ Telegram вернул: {result}")
    except Exception as e:
        print(f"⚠️ Ошибка Telegram: {e}")
    return False

# ========== СБОР И ФИЛЬТРАЦИЯ ==========
def collect_and_filter(feeds, start_index, posted_links, posted_titles):
    raw_news, next_index = get_all_news_from_category(feeds, start_index)
    print(f"\n📊 Всего собрано: {len(raw_news)} новостей")

    unique_news = []
    for item in raw_news:
        if item['link'] in posted_links: continue
        normalized = normalize_title(item['title'])
        if normalized in posted_titles: continue
        if not is_relevant(item): continue
        unique_news.append(item)

    print(f"✅ После фильтрации: {len(unique_news)} подходящих новостей")
    return unique_news, next_index

# ========== ГЛАВНЫЙ ЦИКЛ ==========
def main():
    print("🚀 Запуск агрегатора (Косметология и Медицина)...\n")

    memory = load_memory()
    posted_links = memory.get('posted_links', [])
    posted_titles = memory.get('posted_titles', [])
    site_index = memory.get('site_index', 0)
    tg_index = memory.get('tg_index', 0)
    last_source = memory.get('last_source', 'tg')

    print(f"🧠 В памяти: {len(posted_links)} ссылок, {len(posted_titles)} заголовков")
    print(f"📂 Последний источник: {last_source.upper()}")
    print(f"📊 Индексы: сайты={site_index}, телеграм={tg_index}\n")

    # Определяем приоритет и запасной источник
    if last_source == 'site':
        priority_source = 'tg'
        priority_feeds = TG_FEEDS
        priority_index = tg_index
        fallback_source = 'site'
        fallback_feeds = SITE_FEEDS
        fallback_index = site_index
    else:
        priority_source = 'site'
        priority_feeds = SITE_FEEDS
        priority_index = site_index
        fallback_source = 'tg'
        fallback_feeds = TG_FEEDS
        fallback_index = tg_index

    # ШАГ 1: Приоритетная категория
    print(f"📰 Приоритет: {priority_source.upper()} ({len(priority_feeds)} источников)")
    unique_news, priority_next_index = collect_and_filter(priority_feeds, priority_index, posted_links, posted_titles)

    current_source = priority_source
    next_index = priority_next_index

    # ШАГ 2: Fallback, если в приоритетной нет новостей
    if not unique_news:
        print(f"\n⚠️ В {priority_source.upper()} нет новых новостей. Пробуем запасной источник...")
        print(f"📰 Запасной: {fallback_source.upper()} ({len(fallback_feeds)} источников)")
        unique_news, fallback_next_index = collect_and_filter(fallback_feeds, fallback_index, posted_links, posted_titles)

        if unique_news:
            current_source = fallback_source
            next_index = fallback_next_index
        else:
            print(f"\n❌ Новостей нет ни в одной категории. Пропускаем этот час.")
            memory['site_index'] = (site_index + 1) % len(SITE_FEEDS)
            memory['tg_index'] = (tg_index + 1) % len(TG_FEEDS)
            save_memory(memory)
            return

    # Берем первую подходящую новость
    news_item = unique_news[0]
    print(f"\n📝 Выбираем: {news_item['title'][:60]}...")
    print(f"📡 Источник: {news_item['source']}")
    print(f"📂 Категория: {current_source.upper()}\n")

    # Обработка через Groq
    if is_from_telegram(news_item['feed_url']):
        print("→ Промпт: TELEGRAM (рерайт + антиреклама + обезличивание)")
        post_text = process_tg_news(news_item)
    else:
        print("→ Промпт: САЙТ/НАУЧНЫЙ (перевод + нейтральный обзор)")
        post_text = process_site_news(news_item)

    if not post_text:
        print("⏭ Пропущено (реклама или ошибка Groq).")
        posted_links.append(news_item['link'])
        posted_titles.append(normalize_title(news_item['title']))
        memory['posted_links'] = posted_links[-1000:]
        memory['posted_titles'] = posted_titles[-1000:]
        if current_source == 'site':
            memory['site_index'] = next_index
        else:
            memory['tg_index'] = next_index
        save_memory(memory)
        return

    # Очистка и форматирование
    post_text = format_post(clean_post_text(post_text))

    print("\n--- ГОТОВЫЙ ПОСТ (после очистки и форматирования) ---")
    print(post_text)
    print("--------------------\n")

    # Публикация
    if post_to_telegram(post_text):
        print(f"🎉 Успешно опубликовано!")

        posted_links.append(news_item['link'])
        posted_titles.append(normalize_title(news_item['title']))
        memory['posted_links'] = posted_links[-1000:]
        memory['posted_titles'] = posted_titles[-1000:]

        if current_source == 'site':
            memory['site_index'] = next_index
        else:
            memory['tg_index'] = next_index

        # Чередование: меняем приоритет только если опубликовали из приоритетной категории
        if current_source == priority_source:
            memory['last_source'] = current_source

        save_memory(memory)
        print(f"💾 Память сохранена.")
        print(f"🔄 Следующий приоритет: {'TELEGRAM' if memory['last_source'] == 'site' else 'САЙТЫ'}")
        print(f"📊 Индексы: сайты={memory['site_index']}, телеграм={memory['tg_index']}")
    else:
        print("❌ Не удалось опубликовать.")

if __name__ == "__main__":
    main()
