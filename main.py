#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот-агрегатор новостей по косметологии и дерматологии
Собирает новости из сайтов, научных журналов и Telegram-каналов,
генерирует посты на русском языке и публикует в канал.
"""

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
MEMORY_FILE = "posted_news.json"

# Инициализация клиента Groq
groq_client = Groq(api_key=GROQ_API_KEY)

# ========== КАТЕГОРИИ ИСТОЧНИКОВ ==========

# Категория 1: САЙТЫ (новостные порталы и блоги)
SITE_FEEDS = [
    # Международные
    'https://www.cosmeticsdesign-asia.com/Article/RSS/All',
    'https://www.cosmeticsdesign-europe.com/Article/RSS/All',
    'https://www.cosmeticsdesign.com/Article/RSS/All',
    'https://www.happi.com/contents/view_breaking-news/feed/',
    'https://www.beautyindependent.com/feed/',
    'https://cosmeticsbusiness.com/news/rss',
    'https://www.premiumbeautynews.com/spip.php?page=backend',
    
    # Российские
    'https://www.cosmo.ru/beauty/feed/',
    'https://www.elle.ru/krasota/feed/',
    'https://www.marieclaire.ru/krasota/feed/',
    'https://www.glamour.ru/beauty/feed/',
    'https://www.allure.ru/feed/',
    'https://www.vogue.ru/beauty/feed/',
    'https://www.tatler.ru/beauty/feed/',
    'https://www.buro247.ru/beauty/feed/',
    
    # Научно-популярные
    'https://naked-science.ru/feed',
    'https://elementy.ru/rss/news',
    'https://www.scientificrussia.ru/feed/',
]

# Категория 2: НАУКА (научные журналы и препринты)
SCIENCE_FEEDS = [
    'crossref:2077-0383:cosmetic OR dermatology OR aesthetic OR skin',
    'crossref:1465-3249:cosmetic OR dermatology OR aesthetic',
    'crossref:1660-4601:dermatology OR cosmetic OR skin',
    'pubmed:cosmetic OR dermatology OR aesthetic OR skin care',
    'semanticscholar:dermatology cosmetic aesthetic skin',
    'medrxiv',
    'europepmc:dermatology OR cosmetic OR aesthetic OR skin',
]

# Категория 3: TELEGRAM (специализированные каналы)
TG_FEEDS = [
    'https://tg.i-c-a.su/rss/chatkosmetologa',
    'https://tg.i-c-a.su/rss/d_dermatology',
    'https://tg.i-c-a.su/rss/cosmetologich',
    'https://tg.i-c-a.su/rss/cosmetologiainside',
    'https://tg.i-c-a.su/rss/esteticmed',
    'https://tg.i-c-a.su/rss/dermatologpro',
]

CATEGORIES = ['site', 'science', 'tg']

# ========== КЛЮЧЕВЫЕ СЛОВА ДЛЯ ФИЛЬТРАЦИИ ==========
RELEVANT_KEYWORDS = [
    # Английские
    'skin', 'dermatology', 'cosmetic', 'aesthetic', 'acne',
    'collagen', 'wrinkle', 'peptide', 'exosome', 'laser',
    'psoriasis', 'eczema', 'melanoma', 'rosacea', 'pigment',
    'botox', 'botulinum', 'filler', 'rejuvenation', 'skin aging',
    'sunscreen', 'moisturizer', 'skincare', 'dermatitis',
    'vitiligo', 'atopic', 'alopecia', 'pruritus', 'dermatosis',
    'cosmeceutical', 'beauty', 'facial', 'injectable',
    
    # Русские
    'кожа', 'косметолог', 'дерматолог', 'эстетическ', 'акне',
    'псориаз', 'морщины', 'коллаген', 'ботокс', 'филлер',
    'пилинг', 'лазерная терапия', 'омоложение', 'дерматит', 'розацеа',
    'красота', 'уход за кожей', 'увлажнение', 'старение кожи',
    'инъекции', 'процедуры', 'косметика', 'макияж',
    
    # Корейские
    '피부', '화장품', '뷰티', '미용', '성형', '피부과',
    '보톡스', '필러', '레이저', '콜라겐', '엑소좀', '여드름',
    '아토피', '탈모', '주름', '색소', '자외선',
    
    # Китайские
    '皮肤', '美容', '医美', '化妆品', '整形', '激光治疗',
    '胶原', '痤疮', '湿疹', '护肤', '美白',
]

# ========== ПАМЯТЬ ==========
def load_memory():
    """Загружает память о ранее опубликованных постах."""
    default = {
        'posted_links': [],
        'posted_titles': [],
        'site_index': 0,
        'science_index': 0,
        'tg_index': 0,
        'next_category': 'site',
    }
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Обеспечиваем наличие всех ключей
            for key in default:
                if key not in data:
                    data[key] = default[key]
            return data
        except Exception as e:
            print(f"⚠️ Ошибка загрузки памяти: {e}")
            return default
    return default

def save_memory(memory):
    """Сохраняет память о опубликованных постах."""
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения памяти: {e}")

def normalize_title(title):
    """Нормализует заголовок для сравнения."""
    if not title:
        return ""
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title

# ========== 📅 ПАРСИНГ ДАТ ==========
def parse_publication_date(news_item):
    """Извлекает дату публикации и определяет, будущая ли она."""
    text = (news_item.get('summary', '') + ' ' + news_item.get('title', '')).lower()
    current_year = datetime.now().year
    
    year_patterns = [
        r'\b(20\d{2})\b',
        r'published[:\s]+.*?(\d{4})',
        r'epub[:\s]+.*?(\d{4})',
        r'in press.*?(\d{4})',
    ]
    
    for pattern in year_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                year = int(match)
                if 2000 <= year <= 2100:
                    is_future = year > current_year
                    return {
                        'year': year,
                        'is_future': is_future,
                        'status': 'препринт/в печати' if is_future else 'опубликовано'
                    }
            except ValueError:
                continue
    
    return {'year': None, 'is_future': False, 'status': 'дата не указана'}

# ========== 🛡️ ОЧИСТКА И ФОРМАТИРОВАНИЕ ==========
def clean_post_text(text):
    """Очищает текст поста от лишних символов."""
    if not text:
        return text
    
    # Удаляем лишние пробелы и переносы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()
    
    return text

def format_post(text):
    """Форматирует пост для публикации."""
    if not text:
        return text
    
    # Разделяем на строки
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        line = line.strip()
        if line:
            formatted_lines.append(line)
    
    return '\n\n'.join(formatted_lines)

# ========== ЧТЕНИЕ RSS ==========
def clean_html(text):
    """Удаляет HTML теги из текста."""
    if not text:
        return ""
    # Удаляем теги
    text = re.sub(r'<[^>]+>', ' ', text)
    # Декодируем HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    # Удаляем лишние пробелы
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_news_from_rss(feed_url, max_items=10):
    """Получает новости из RSS ленты."""
    try:
        feed = feedparser.parse(feed_url)
        
        if feed.bozo and not feed.entries:
            print(f"   ⚠️ Ошибка парсинга {feed_url}")
            return []
        
        news_list = []
        for entry in feed.entries[:max_items]:
            title = entry.get('title', '')
            summary = clean_html(entry.get('summary', entry.get('description', '')))
            
            # Обрезаем длинные описания
            if len(summary) > 1500:
                summary = summary[:1500] + '...'
            
            # Парсим дату
            date_info = parse_publication_date({'title': title, 'summary': summary})
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': entry.get('link', ''),
                'source': feed_url.split('/')[2] if '//' in feed_url else feed_url,
                'feed_url': feed_url,
                'date_info': date_info,
            })
        
        print(f"   🔍 {news_list[0]['source'] if news_list else feed_url}: записей {len(news_list)}")
        return news_list
        
    except Exception as e:
        print(f"   ⚠️ Ошибка чтения {feed_url}: {e}")
        return []

# ========== 🔬 НАУЧНЫЕ API ==========
def fetch_abstract_from_openalex(doi):
    """Получает аннотацию статьи из OpenAlex по DOI."""
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            abstract_inverted = data.get('abstract_inverted_index')
            if abstract_inverted:
                # Восстанавливаем текст из инвертированного индекса
                words = {}
                for word, positions in abstract_inverted.items():
                    for pos in positions:
                        words[pos] = word
                abstract = ' '.join(words[i] for i in sorted(words.keys()))
                return abstract
        return ""
    except Exception:
        return ""

def get_news_from_crossref(issn, query, max_items=6):
    """Получает новости из Crossref по ISSN журнала."""
    try:
        url = "https://api.crossref.org/works"
        params = {
            "filter": f"issn:{issn},type:journal-article",
            "query": query,
            "rows": max_items,
            "sort": "published",
            "order": "desc",
        }
        headers = {'User-Agent': 'CosmoNewsBot/1.0 (contact@example.com)'}
        response = requests.get(url, params=params, headers=headers, timeout=20)
        
        if response.status_code != 200:
            print(f"   ⚠️ Crossref статус {response.status_code}")
            return []
        
        items = response.json().get("message", {}).get("items", [])
        source_name = f"Crossref {issn}"
        print(f"   🔍 {source_name}: записей {len(items)}")
        
        news_list = []
        for item in items:
            title = item.get('title', [''])[0] if item.get('title') else ''
            if not title:
                continue
            
            doi = item.get('DOI', '')
            link = f"https://doi.org/{doi}" if doi else ''
            
            # Получаем авторов
            authors = []
            for author in item.get('author', [])[:3]:
                name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                if name:
                    authors.append(name)
            authors_str = ", ".join(authors) if authors else "не указаны"
            
            # Парсим дату
            date_parts = item.get('published-print', {}).get('date-parts', [[]])[0]
            if not date_parts:
                date_parts = item.get('published-online', {}).get('date-parts', [[]])[0]
            year = date_parts[0] if date_parts else None
            current_year = datetime.now().year
            is_future = year and year > current_year
            
            # Пытаемся получить аннотацию из OpenAlex
            abstract = fetch_abstract_from_openalex(doi)
            if not abstract:
                abstract = f"Научная статья. Авторы: {authors_str}."
            
            summary = abstract[:1500] + '...' if len(abstract) > 1500 else abstract
            summary += f" | Авторы: {authors_str}. Источник: журнал."
            if year:
                summary += f" Год: {year}."
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': source_name,
                'feed_url': f'crossref:{issn}',
                'date_info': {
                    'year': year,
                    'is_future': is_future,
                    'status': 'препринт/в печати' if is_future else 'опубликовано'
                }
            })
        
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка Crossref: {e}")
        return []

def get_news_from_pubmed(query, max_items=8):
    """Получает новости из PubMed."""
    try:
        # Поиск статей
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_items,
            "retmode": "json",
            "sort": "date",
        }
        response = requests.get(search_url, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"   ⚠️ PubMed статус {response.status_code}")
            return []
        
        id_list = response.json().get('esearchresult', {}).get('idlist', [])
        if not id_list:
            print("   🔍 PubMed: записей 0")
            return []
        
        # Получаем детали статей
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "xml",
        }
        response = requests.get(fetch_url, params=params, timeout=15)
        
        if response.status_code != 200:
            return []
        
        # Простой парсинг XML (без xmltodict для упрощения)
        content = response.text
        articles = []
        
        # Извлекаем заголовки и ссылки
        titles = re.findall(r'<ArticleTitle>(.*?)</ArticleTitle>', content, re.DOTALL)
        pmids = re.findall(r'<PMID[^>]*>(\d+)</PMID>', content)
        
        print(f"   🔍 PubMed: записей {len(titles)}")
        
        for i, title in enumerate(titles[:max_items]):
            title = clean_html(title)
            pmid = pmids[i] if i < len(pmids) else ''
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ''
            
            # Пытаемся извлечь аннотацию
            abstract_match = re.search(r'<AbstractText[^>]*>(.*?)</AbstractText>', content, re.DOTALL)
            abstract = clean_html(abstract_match.group(1)) if abstract_match else "Научная статья."
            
            # Парсим год
            year_match = re.search(r'<Year>(\d{4})</Year>', content)
            year = int(year_match.group(1)) if year_match else None
            current_year = datetime.now().year
            is_future = year and year > current_year
            
            summary = abstract[:1500] + '...' if len(abstract) > 1500 else abstract
            
            articles.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': 'PubMed',
                'feed_url': 'pubmed:query',
                'date_info': {
                    'year': year,
                    'is_future': is_future,
                    'status': 'препринт/в печати' if is_future else 'опубликовано'
                }
            })
        
        return articles
    except Exception as e:
        print(f"   ⚠️ Ошибка PubMed: {e}")
        return []

def get_news_from_semantic_scholar(query, max_items=6):
    """Получает новости из Semantic Scholar."""
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": max_items,
            "fields": "title,abstract,authors,year,externalIds,url,openAccessPdf",
        }
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 429:
            print("   ⚠️ Semantic Scholar: rate limit")
            return []
        
        if response.status_code != 200:
            print(f"   ⚠️ Semantic Scholar статус {response.status_code}")
            return []
        
        papers = response.json().get('data', [])
        print(f"   🔍 Semantic Scholar: записей {len(papers)}")
        
        news_list = []
        for paper in papers:
            title = paper.get('title', '')
            if not title:
                continue
            
            abstract = paper.get('abstract', '') or "Научная статья."
            year = paper.get('year')
            current_year = datetime.now().year
            is_future = year and year > current_year
            
            # Получаем ссылку
            external_ids = paper.get('externalIds', {})
            doi = external_ids.get('DOI', '')
            pmid = external_ids.get('PubMed', '')
            
            if doi:
                link = f"https://doi.org/{doi}"
            elif pmid:
                link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            else:
                link = paper.get('url', '')
            
            # Авторы
            authors = [a.get('name', '') for a in paper.get('authors', [])[:3]]
            authors_str = ", ".join(authors) if authors else "не указаны"
            
            summary = abstract[:1500] + '...' if len(abstract) > 1500 else abstract
            summary += f" | Авторы: {authors_str}."
            if year:
                summary += f" Год: {year}."
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': 'Semantic Scholar',
                'feed_url': 'semanticscholar:query',
                'date_info': {
                    'year': year,
                    'is_future': is_future,
                    'status': 'препринт/в печати' if is_future else 'опубликовано'
                }
            })
        
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка Semantic Scholar: {e}")
        return []

def get_news_from_medrxiv(max_items=6):
    """Получает препринты из medRxiv по дерматологии."""
    try:
        # Получаем список категорий
        url = "https://api.medrxiv.org/details/medrxiv/dermatology/0/10"
        response = requests.get(url, timeout=20)
        
        if response.status_code != 200:
            print(f"   ⚠️ medRxiv статус {response.status_code}")
            return []
        
        papers = response.json().get('collection', [])
        print(f"   🔍 medRxiv: препринтов {len(papers)}")
        
        news_list = []
        for paper in papers[:max_items]:
            title = paper.get('title', '')
            if not title:
                continue
            
            abstract = paper.get('abstract', '') or "Препринт."
            doi = paper.get('doi', '')
            link = f"https://doi.org/{doi}" if doi else paper.get('jatsxml', '')
            
            # Авторы
            authors = paper.get('authors', '')
            authors_list = [a.strip() for a in authors.split(',')[:3]] if authors else []
            authors_str = ", ".join(authors_list) if authors_list else "не указаны"
            
            # Дата
            date_str = paper.get('date', '')
            year = int(date_str.split('-')[0]) if date_str else None
            current_year = datetime.now().year
            is_future = year and year > current_year
            
            summary = abstract[:1500] + '...' if len(abstract) > 1500 else abstract
            summary += f" | Авторы: {authors_str}."
            if date_str:
                summary += f" Препринт от {date_str}."
            
            news_list.append({
                'title': f"[Препринт] {title}",
                'summary': summary,
                'link': link,
                'source': 'medRxiv',
                'feed_url': 'medrxiv:dermatology',
                'date_info': {
                    'year': year,
                    'is_future': is_future,
                    'status': 'препринт'
                }
            })
        
        print(f"   🔍 medRxiv по теме: {len(news_list)}")
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка medRxiv: {e}")
        return []

def get_news_from_europepmc(query, max_items=6):
    """Получает новости из Europe PMC."""
    try:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": max_items,
        }
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"   ⚠️ Europe PMC статус {response.status_code}")
            return []
        
        results = response.json().get('resultList', {}).get('result', [])
        print(f"   🔍 Europe PMC: записей {len(results)}")
        
        news_list = []
        for item in results:
            title = item.get('title', '')
            if not title:
                continue
            
            abstract = item.get('abstractText', '') or "Научная статья."
            
            # Парсим год
            year = item.get('pubYear')
            year = int(year) if year else None
            current_year = datetime.now().year
            is_future = year and year > current_year
            
            # Ссылка
            pmid = item.get('pmid', '')
            pmcid = item.get('pmcid', '')
            doi = item.get('doi', '')
            
            if doi:
                link = f"https://doi.org/{doi}"
            elif pmcid:
                link = f"https://europepmc.org/article/MED/{pmcid}"
            elif pmid:
                link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            else:
                link = ''
            
            # Авторы
            author_list = item.get('authorList', {}).get('author', [])
            authors = [a.get('fullName', '') for a in author_list[:3]]
            authors_str = ", ".join(authors) if authors else "не указаны"
            
            summary = abstract[:1500] + '...' if len(abstract) > 1500 else abstract
            summary += f" | Авторы: {authors_str}."
            if year:
                summary += f" Год: {year}."
            
            news_list.append({
                'title': title,
                'summary': summary,
                'link': link,
                'source': 'Europe PMC',
                'feed_url': 'europepmc:query',
                'date_info': {
                    'year': year,
                    'is_future': is_future,
                    'status': 'препринт/в печати' if is_future else 'опубликовано'
                }
            })
        
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка Europe PMC: {e}")
        return []

# ========== ДИСПЕТЧЕР ИСТОЧНИКОВ ==========
def fetch_from_feed(feed):
    """Диспетчер для получения новостей из разных источников."""
    if feed.startswith('crossref:'):
        parts = feed.split(':', 2)
        if len(parts) >= 3:
            return get_news_from_crossref(parts[1], parts[2])
        return []
    
    if feed.startswith('pubmed:'):
        query = feed.split(':', 1)[1] if ':' in feed else 'dermatology'
        return get_news_from_pubmed(query)
    
    if feed.startswith('semanticscholar:'):
        query = feed.split(':', 1)[1] if ':' in feed else 'dermatology'
        return get_news_from_semantic_scholar(query)
    
    if feed == 'medrxiv':
        return get_news_from_medrxiv()
    
    if feed.startswith('europepmc:'):
        query = feed.split(':', 1)[1] if ':' in feed else 'dermatology'
        return get_news_from_europepmc(query)
    
    # Обычный RSS
    return get_news_from_rss(feed)

# ========== ФИЛЬТРАЦИЯ ==========
def is_relevant(news_item):
    """Проверяет, соответствует ли новость тематике канала."""
    title = news_item.get('title', '').lower()
    summary = news_item.get('summary', '').lower()
    text = f"{title} {summary}"
    
    # Проверяем наличие хотя бы одного ключевого слова
    return any(keyword.lower() in text for keyword in RELEVANT_KEYWORDS)

def is_from_telegram(feed_url):
    """Проверяет, является ли источник Telegram-каналом."""
    return 'tg.i-c-a.su' in feed_url or 'telegram' in feed_url.lower()

def get_feeds_for_category(category):
    """Возвращает список источников для категории."""
    if category == 'site':
        return SITE_FEEDS
    elif category == 'science':
        return SCIENCE_FEEDS
    elif category == 'tg':
        return TG_FEEDS
    return []

# ========== ПОИСК НОВОСТЕЙ ==========
def find_news_in_category(category, memory, posted_links, posted_titles):
    """Ищет новости в указанной категории."""
    feeds = get_feeds_for_category(category)
    if not feeds:
        return None, 0
    
    index_key = f"{category}_index"
    start_index = memory.get(index_key, 0) % len(feeds)
    
    print(f"   📡 [{category.upper()}] начинаем с источника #{start_index+1}/{len(feeds)}")
    
    # Проходим по всем источникам категории по кругу
    for i in range(len(feeds)):
        idx = (start_index + i) % len(feeds)
        feed = feeds[idx]
        
        print(f"   📡 [{category.upper()}] источник #{idx+1}/{len(feeds)}: {feed}")
        news_items = fetch_from_feed(feed)
        
        # Задержка для научных API
        if category == 'science':
            time.sleep(2.0)
        else:
            time.sleep(0.5)
        
        for item in news_items:
            # Проверка на дубликаты
            if item['link'] in posted_links:
                print(f"   ⏭ Пропуск (дубликат ссылки): {item['title'][:50]}")
                continue
            
            normalized_title = normalize_title(item['title'])
            if normalized_title in posted_titles:
                print(f"   ⏭ Пропуск (дубликат заголовка): {item['title'][:50]}")
                continue
            
            # Проверка релевантности
            if not is_relevant(item):
                print(f"   ⏭ Пропуск (не по теме): {item['title'][:50]}")
                continue
            
            print(f"   ✅ Найдена новость: {item['title'][:60]}")
            # Возвращаем новость и следующий индекс
            return item, (idx + 1) % len(feeds)
    
    print(f"   ❌ В категории {category.upper()} новостей нет")
    return None, (start_index + 1) % len(feeds)

# ========== ГЕНЕРАЦИЯ ПОСТОВ ==========
def process_site_news(news_item):
    """Генерирует пост для новостей с сайтов."""
    date_info = news_item.get('date_info', {})
    year = date_info.get('year')
    is_future = date_info.get('is_future', False)
    
    date_hint = ""
    if year and is_future:
        current_year = datetime.now().year
        date_hint = f"""
⚠️ ВАЖНО — ДАТА ПУБЛИКАЦИИ:
В тексте указан {year} год, но сейчас {current_year} год. Это означает, что статья является ПРЕПРИНТОМ или находится "в печати" (еще не опубликована).
- Пиши: "исследование планируется к публикации в {year} году" или "работа находится в стадии препринта"
- НЕ пиши "опубликовано в {year} году" как свершившийся факт
- Используй формулировки: "ожидается публикация", "в печати", "предварительные результаты"
"""
    
    prompt = f"""Ты — профессиональный научный журналист, специализирующийся на косметологии и дерматологии.
Твоя задача — написать увлекательный, информативный пост на русском языке для канала о красоте и здоровье кожи.

ИСТОЧНИК: {news_item.get('source', 'Не указан')}
ЗАГОЛОВОК: {news_item.get('title', '')}
СОДЕРЖАНИЕ: {news_item.get('summary', '')}
{date_hint}

ТРЕБОВАНИЯ К ПОСТУ:
1. Напиши на русском языке
2. Объем: 150-250 слов
3. Структура:
   - Яркий заголовок (до 60 символов)
   - Краткое введение (2-3 предложения)
   - Основная часть с ключевыми фактами (3-5 предложений)
   - Практическая ценность для читателя (1-2 предложения)
   - 2-3 хэштега в конце

4. Стиль:
   - Научно-популярный, но не сухой
   - Используй эмодзи умеренно (2-4 шт)
   - Избегай кликбейта и преувеличений
   - Указывай источник информации

5. Формат:
   - Заголовок в начале
   - Пустая строка
   - Текст поста
   - Пустая строка
   - Хэштеги

НЕ делай:
- Не выдумывай факты, которых нет в исходном тексте
- Не используй фразы типа "шок", "невероятно", "сенсация"
- Не давай медицинских рекомендаций

Верни ТОЛЬКО текст поста, без пояснений."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты профессиональный научный журналист, пишущий о косметологии и дерматологии."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"   ⚠️ Ошибка генерации поста: {e}")
        return None

def process_tg_news(news_item):
    """Генерирует пост для новостей из Telegram-каналов."""
    date_info = news_item.get('date_info', {})
    year = date_info.get('year')
    is_future = date_info.get('is_future', False)
    
    date_hint = ""
    if year and is_future:
        current_year = datetime.now().year
        date_hint = f"""
⚠️ ВАЖНО — ДАТА ПУБЛИКАЦИИ:
В тексте указан {year} год, но сейчас {current_year} год. Это означает, что информация может быть предварительной или анонсом.
- Пиши осторожно, с указанием на предварительный характер
- НЕ подавай как уже свершившийся факт
"""
    
    prompt = f"""Ты — профессиональный научный журналист, специализирующийся на косметологии и дерматологии.
Твоя задача — переписать пост из Telegram-канала в своем стиле для канала о красоте и здоровье кожи.

ЗАГОЛОВОК: {news_item.get('title', '')}
СОДЕРЖАНИЕ: {news_item.get('summary', '')}
{date_hint}

ТРЕБОВАНИЯ К ПОСТУ:
1. Напиши на русском языке
2. Объем: 150-250 слов
3. Структура:
   - Яркий заголовок (до 60 символов)
   - Краткое введение (2-3 предложения)
   - Основная часть с ключевыми фактами (3-5 предложений)
   - Практическая ценность для читателя (1-2 предложения)
   - 2-3 хэштега в конце

4. Стиль:
   - Научно-популярный, но не сухой
   - Используй эмодзи умеренно (2-4 шт)
   - Избегай кликбейта и преувеличений
   - Сохраняй ключевые факты из оригинала

5. Формат:
   - Заголовок в начале
   - Пустая строка
   - Текст поста
   - Пустая строка
   - Хэштеги

НЕ делай:
- Не выдумывай факты, которых нет в исходном тексте
- Не используй фразы типа "шок", "невероятно", "сенсация"
- Не давай медицинских рекомендаций
- Не копируй оригинальный текст дословно

Верни ТОЛЬКО текст поста, без пояснений."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты профессиональный научный журналист, пишущий о косметологии и дерматологии."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"   ⚠️ Ошибка генерации поста: {e}")
        return None

# ========== ПУБЛИКАЦИЯ ==========
def post_to_telegram(text):
    """Публикует пост в Telegram канал."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        
        if result.get('ok'):
            print(f"✅ Опубликовано в {CHANNEL_ID}!")
            return True
        else:
            print(f"⚠️ Telegram вернул ошибку: {result}")
            return False
    except Exception as e:
        print(f"⚠️ Ошибка публикации: {e}")
        return False

# ========== ГЛАВНЫЙ ЦИКЛ ==========
def main():
    """Главная функция бота."""
    print("🚀 Запуск агрегатора (Косметология и Медицина)...\n")
    
    # Загружаем память
    memory = load_memory()
    posted_links = memory.get('posted_links', [])
    posted_titles = memory.get('posted_titles', [])
    
    print(f"🧠 В памяти: {len(posted_links)} ссылок, {len(posted_titles)} заголовков")
    print(f"🔁 Цикл категорий: САЙТ → НАУКА → TG → по кругу")
    print(f"📌 Указатели: сайт=#{memory['site_index']+1}, наука=#{memory['science_index']+1}, тг=#{memory['tg_index']+1}")
    print(f"📂 Следующая категория: {memory['next_category'].upper()}\n")
    
    # Определяем порядок категорий
    start_pos = CATEGORIES.index(memory['next_category']) if memory['next_category'] in CATEGORIES else 0
    
    chosen_item = None
    chosen_cat = None
    
    # Проходим по категориям по кругу
    for step in range(len(CATEGORIES)):
        cat = CATEGORIES[(start_pos + step) % len(CATEGORIES)]
        print(f"📰 Проверяем категорию: {cat.upper()}")
        
        item, new_index = find_news_in_category(cat, memory, posted_links, posted_titles)
        
        # Обновляем указатель категории
        memory[f"{cat}_index"] = new_index
        
        if item:
            chosen_item = item
            chosen_cat = cat
            break
        
        print()
    
    if not chosen_item:
        print("❌ Новостей нет ни в одной категории. Пропускаем этот час.")
        memory['next_category'] = CATEGORIES[(start_pos + 1) % len(CATEGORIES)]
        save_memory(memory)
        return
    
    print(f"\n📝 Выбираем: {chosen_item['title'][:60]}...")
    print(f"📡 Источник: {chosen_item['source']}")
    print(f"📂 Категория: {chosen_cat.upper()}")
    
    if 'date_info' in chosen_item:
        di = chosen_item['date_info']
        if di.get('year'):
            print(f"📅 Год: {di['year']} ({di['status']})")
    
    print()
    
    # Генерируем пост
    if chosen_cat == 'tg':
        print("→ Промпт: TELEGRAM (рерайт + обезличивание)")
        post_text = process_tg_news(chosen_item)
    else:
        print("→ Промпт: САЙТ/НАУКА (перевод + нейтральный обзор)")
        post_text = process_site_news(chosen_item)
    
    if not post_text:
        print("⏭ Пропущено (ошибка генерации).")
        # Добавляем в память, чтобы не повторять
        posted_links.append(chosen_item['link'])
        posted_titles.append(normalize_title(chosen_item['title']))
        memory['posted_links'] = posted_links[-500:]
        memory['posted_titles'] = posted_titles[-500:]
        memory['next_category'] = chosen_cat
        save_memory(memory)
        return
    
    # Форматируем пост
    post_text = format_post(clean_post_text(post_text))
    
    print("\n--- ГОТОВЫЙ ПОСТ ---")
    print(post_text)
    print("--------------------\n")
    
    # Публикуем
    if post_to_telegram(post_text):
        print("🎉 Успешно опубликовано!")
        
        # Обновляем память
        posted_links.append(chosen_item['link'])
        posted_titles.append(normalize_title(chosen_item['title']))
        memory['posted_links'] = posted_links[-500:]
        memory['posted_titles'] = posted_titles[-500:]
        
        # Следующая категория
        memory['next_category'] = CATEGORIES[(start_pos + 1) % len(CATEGORIES)]
        
        save_memory(memory)
        
        print(f"💾 Память сохранена.")
        print(f"🔄 Следующая категория: {memory['next_category'].upper()}")
        print(f"📌 Указатели: сайт=#{memory['site_index']+1}, наука=#{memory['science_index']+1}, тг=#{memory['tg_index']+1}")
    else:
        print("❌ Не удалось опубликовать.")
        memory['next_category'] = chosen_cat
        save_memory(memory)

if __name__ == "__main__":
    main()
