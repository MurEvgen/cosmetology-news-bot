import feedparser
from groq import Groq
import requests
import os
import json
import time
import re

# ========== НАСТРОЙКИ ==========
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@derma_cosmo_facts"

MEMORY_FILE = "posted_news.json"
groq_client = Groq(api_key=GROQ_API_KEY)

# ========== ИСТОЧНИКИ (все проверены 09.09.2026) ==========
SITE_FEEDS = [
    # 🌍 Западные (профильные)
    'https://www.sciencedaily.com/rss/health_medicine/skin_care.xml',
    'https://www.healio.com/rss/dermatology',
    # 🇰🇷 Корея
    'https://www.bosa.co.kr/rss/allArticle.xml',           # 의학신문 — мед. газета (корейский)
    'https://m.koreaherald.com/rss/newsAll',               # Korea Herald
    'https://en.yna.co.kr/RSS/news.xml',                   # Yonhap News
    # 🇨🇳 Китай
    'http://www.chinadaily.com.cn/rss/lifestyle_rss.xml',  # China Daily Lifestyle
    'https://www.scmp.com/rss/2/feed',                     # SCMP (Гонконг/Китай)
    'https://weekly.chinacdc.cn/rss/current.xml',          # China CDC Weekly
]

TG_FEEDS = [
    'https://tg.i-c-a.su/rss/chatkosmetologa',
    'https://tg.i-c-a.su/rss/d_dermatology',
    'https://tg.i-c-a.su/rss/cosmetologich',
    'https://tg.i-c-a.su/rss/cosmetologiainside',
]

# Ключевые слова тематики: EN + RU + 🇰🇷 KO + 🇨 CN
RELEVANT_KEYWORDS = [
    # English
    'skin', 'dermatology', 'cosmetic', 'aesthetic', 'acne',
    'collagen', 'wrinkle', 'peptide', 'exosome', 'laser',
    'psoriasis', 'eczema', 'melanoma', 'rosacea', 'pigment',
    'botox', 'botulinum', 'filler', 'rejuvenation', 'aging',
    'sunscreen', 'moisturizer', 'skincare', 'beauty',
    # Russian
    'кожа', 'косметолог', 'дерматолог', 'эстетическ', 'акне',
    # Korean 🇰
    '피부', '화장품', '뷰티', '미용', '성형', '피부과',
    '보톡스', '필러', '레이저', '콜라겐', '엑소좀', '여드름',
    '아토피', '탈모', '주름', '색소', '자외선',
    # Chinese 🇨
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

def get_all_news_from_category(feeds, start_index):
    """Проходим по ВСЕМ источникам категории, начиная со start_index (round-robin)"""
    num_feeds = len(feeds)
    if num_feeds == 0:
        return [], 0

    all_news = []
    for i in range(num_feeds):
        idx = (start_index + i) % num_feeds
        print(f"📡 Проверяем источник #{idx+1}: {feeds[idx]}")
        news = get_news_from_rss(feeds[idx], max_items=10)
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

# ========== ПРОМПТ 1: САЙТЫ (перевод + нейтральный обзор) ==========
def process_site_news(news_item):
    prompt = f"""Ты — нейтральный научный обозреватель Telegram-канала о косметологии и доказательной медицине.
ИСТОЧНИК: {news_item['source']}
ОРИГИНАЛЬНЫЙ ЗАГОЛОВОК: {news_item['title']}
ТЕКСТ: {news_item['summary']}

ВАЖНО: Текст может быть на английском, корейском или китайском языке. Пиши пост НА РУССКОМ.

СТРУКТУРА ПОСТА:
1. <b>Цепляющий заголовок</b> (переведи на русский, профессиональный тон)
2. Введение (1-2 предложения): суть новости, почему это важно
3. Основная часть (3-5 предложений): факты, цифры, детали исследования или методики
4. Практическая польза (1-2 предложения): что это значит для отрасли
5. В конце: 🔗 <a href="{news_item['link']}">Читать в источнике</a>
6. Добавь 2-3 хэштега (#косметология #медицина #исследования)

⛔ ЗАПРЕЩЕНО:
- НЕ используй первое лицо: «мы», «я», «у нас», «наш», «в нашей практике», «мы применяем».
- Пиши БЕЗЛИЧНО: «применяется», «используется», «врачи отмечают», «исследование показывает», «специалисты рекомендуют».
- НЕ упоминай конкретные клиники, врачей, бренды оборудования и препаратов как рекламу.
- Коммерческие названия (Endolift, LASEMAR, i-PRF, Juvederm, Botox, Restylane, Morpheus8 и т.п.) заменяй на НАУЧНЫЕ/ОБЩИЕ термины: «диодный лазер 1470 нм», «PRF-терапия», «препарат ботулотоксина типа А», «гиалуроновый филлер», «микроигольчатый RF».
- Никаких призывов: «обсудите с врачом», «запишитесь», «ваша кожа заслуживает», «обратитесь к специалисту».
- Текст должен быть НЕЙТРАЛЬНЫМ информационным обзором, а НЕ авторской колонкой клиники.

ПРАВИЛА:
- Объем: 4-8 предложений
- Живой язык, без канцеляризмов
- 1-2 тематических эмодзи (🔬 💉  🌿 )
- Научная точность, не выдумывай факты

ОТВЕТЬ ТОЛЬКО готовым HTML-текстом поста. Без комментариев."""
    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты нейтральный научный обозреватель. Никаких «мы», брендов и призывов. Строго следуй формату HTML."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq (сайт): {e}")
        return None

# ========== ПРОМПТ 2: TELEGRAM (рерайт + антиреклама + обезличивание) ==========
def process_tg_news(news_item):
    prompt = f"""Ты — нейтральный научный обозреватель Telegram-канала о косметологии.
ТЕКСТ ИСХОДНОГО ПОСТА:
{news_item['summary']}

ЗАДАЧА — выполни ДВА шага:

ШАГ 1: Определи, является ли этот пост РЕКЛАМОЙ.
Реклама — это:
- Прямая продажа курса/вебинара/консультации
- Призыв «запишись», «купи», «жми ссылку», «осталось 3 места»
- Продвижение конкретной клиники с адресом/телефоном
- Промокод, розыгрыш, giveaway
- Призыв подписаться на конкретного автора
Если это реклама — ответь ОДНИМ словом: SKIP

ШАГ 2: Если это НЕ реклама, а полезный экспертный контент (разбор, кейс, научная новость, совет):

СТРУКТУРА ПОСТА:
1. <b>Цепляющий заголовок</b>
2. Введение (1-2 предложения): о чем речь и почему это интересно
3. Основная часть (3-5 предложений): факты, методика, научное обоснование
4. Вывод/практическая польза (1-2 предложения): значение для отрасли
5. 2-3 хэштега (#косметология #медицина)

⛔ КРИТИЧЕСКИ ВАЖНО — ЗАПРЕЩЕНО:
1. НИКАКОГО первого лица: ЗАПРЕЩЕНЫ слова «мы», «я», «у нас», «наш», «в нашей практике», «мы применяем», «в моем опыте», «нашими пациентами».
   ПИШИ БЕЗЛИЧНО: «применяется», «используется», «врачи отмечают», «в клинической практике используется», «исследование показывает».
2. ОБЕЗЛИЧИВАЙ БРЕНДЫ:
   - Названия аппаратов (Endolift, LASEMAR, Morpheus8, Sylfirm, Picosure) → заменяй на технические характеристики: «диодный лазер 1470 нм», «микроигольчатый RF-аппарат», «пикосекундный лазер».
   - Названия препаратов (Juvederm, Restylane, Belotero, i-PRF) → заменяй на общий тип: «гиалуроновый филлер», «препарат на основе PRF», «биоревитализант».
   - Можно ОДИН раз упомянуть бренд в скобках как пример, но НЕ делать на нем акцент.
3. НИКАКИХ призывов к действию: «обсудите с врачом», «запишитесь на консультацию», «ваша кожа заслуживает», «обратитесь к специалисту», «приходите к нам».
4. Текст должен звучать как НЕЙТРАЛЬНЫЙ научный обзор, а НЕ как реклама клиники или личное мнение врача.

ПРАВИЛА:
- Объем: 4-8 предложений
- Живой язык, без канцеляризмов
- 1-2 тематических эмодзи (🔬 💉 🧬 🌿 📊)
- НЕ копируй текст дословно, переписывай своими словами
- НЕ упоминай источник, НЕ добавляй ссылки

ОТВЕТЬ ТОЛЬКО готовым HTML-текстом поста или словом SKIP. Никаких комментариев."""
    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты нейтральный научный обозреватель. ЗАПРЕЩЕНЫ слова «мы», «я», «у нас», бренды и призывы. Отвечай ТОЛЬКО HTML-текстом или словом SKIP."},
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

    # Определяем приоритетную категорию (чередование) и запасную (fallback)
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

    # ШАГ 2: Fallback — если в приоритетной нет новостей
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

    # Обрабатываем через Groq
    if is_from_telegram(news_item['feed_url']):
        print("→ Промпт: TELEGRAM (рерайт + антиреклама + обезличивание)")
        post_text = process_tg_news(news_item)
    else:
        print("→ Промпт: САЙТ (перевод + нейтральный обзор)")
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

    print("\n--- ГОТОВЫЙ ПОСТ ---")
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
