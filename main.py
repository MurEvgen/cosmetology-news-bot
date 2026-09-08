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

# ========== ИСТОЧНИКИ ==========
SITE_FEEDS = [
    'https://www.sciencedaily.com/rss/health_medicine/skin_care.xml',
    'https://medicalxpress.com/rss-feed/dermatology.xml',
    'https://www.medscape.com/cx/rssfeeds/10026.xml',
    'https://www.healio.com/rss/dermatology',
    'https://anndermatol.org/rss.php',
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
    'кожа', 'косметолог', 'дерматолог', 'эстетическ', 'акне',
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

def get_news_from_rss(feed_url, max_items=2):
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
            # Увеличиваем лимит до 1500 символов для более полного контекста
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
    num_feeds = len(feeds)
    if num_feeds == 0:
        return [], 0
    
    all_news = []
    for i in range(num_feeds):
        idx = (start_index + i) % num_feeds
        print(f"📡 Проверяем источник #{idx+1}: {feeds[idx]}")
        news = get_news_from_rss(feeds[idx], max_items=2)
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

# ========== ПРОМПТЫ ==========
def process_site_news(news_item):
    prompt = f"""Ты — главный редактор Telegram-канала о косметологии и доказательной медицине.
ИСТОЧНИК: {news_item['source']}
ОРИГИНАЛЬНЫЙ ЗАГОЛОВОК: {news_item['title']}
ТЕКСТ: {news_item['summary']}

ЗАДАЧА: Напиши развернутый, информативный пост для Telegram.

СТРУКТУРА ПОСТА:
1. <b>Цепляющий заголовок</b> (переведи на русский, профессиональный тон)
2. Введение (1-2 предложения): суть новости, почему это важно
3. Основная часть (4-6 предложений): ключевые факты, цифры, детали исследования или методики. Раскрой тему глубоко, но без воды.
4. Практическая польза (1-2 предложения): что это значит для врачей/пациентов, как можно применить
5. В конце: 🔗 <a href="{news_item['link']}">Читать в источнике</a>
6. Добавь 2-3 хэштега (#косметология #медицина #исследования и т.д.)

ВАЖНО:
- Объем: 5-10 предложений (если новость позволяет). Если материала мало — пиши столько, сколько есть, не выдумывай факты.
- Живой язык, без канцеляризмов
- Добавь 1-2 тематических эмодзи (🔬 💉  🌿 📊 ️)
- Сохрани научную точность, но сделай текст доступным
- НЕ добавляй вступлений вроде "Вот новость" или "Представляем"

ОТВЕТЬ ТОЛЬКО готовым HTML-текстом поста. Без комментариев."""
    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты медицинский редактор. Пиши развернутые, экспертные посты. Строго следуй формату HTML."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1200  # Увеличено с 500
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq (сайт): {e}")
        return None

def process_tg_news(news_item):
    prompt = f"""Ты — главный редактор Telegram-канала о косметологии. Тебе прислали текст поста.
ТЕКСТ:
{news_item['summary']}

ЗАДАЧА — выполни ДВА шага:

ШАГ 1: Определи, является ли этот пост РЕКЛАМОЙ.
Реклама — это: продажа курса/вебинара, призыв «запишись/купи», продвижение клиники с телефоном, промокод, розыгрыш.
Если это реклама — ответь ОДНИМ словом: SKIP

ШАГ 2: Если это НЕ реклама (полезный пост, разбор, новость, совет, клинический случай):
1. Придумай цепляющий заголовок, оберни в <b>жирный</b>
2. Перепиши текст СВОИМИ словами, сделай уникальным
3. Раскрой тему глубоко: 5-10 предложений. Добавь контекст, объясни термины, если нужно
4. Структура: введение → основная часть с фактами → вывод/практическая польза
5. Живой язык, 1-2 тематических эмодзи
6. Добавь 2-3 хэштега (#косметология #медицина)

ВАЖНО:
- НЕ упоминай источник
- НЕ добавляй ссылки на оригинал
- НЕ копируй текст дословно
- Если материала мало — пиши столько, сколько есть, не выдумывай
- Пиши так, будто это авторский экспертный контент твоего канала

ОТВЕТЬ ТОЛЬКО готовым HTML-текстом поста или словом SKIP."""
    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты редактор. Пиши развернутые, экспертные посты. Отвечай ТОЛЬКО текстом поста или словом SKIP."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1200  # Увеличено с 600
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

# ========== ГЛАВНЫЙ ЦИКЛ ==========
def main():
    print(" Запуск агрегатора (Косметология и Медицина)...\n")

    memory = load_memory()
    posted_links = memory.get('posted_links', [])
    posted_titles = memory.get('posted_titles', [])
    site_index = memory.get('site_index', 0)
    tg_index = memory.get('tg_index', 0)
    last_source = memory.get('last_source', 'tg')

    print(f"🧠 В памяти: {len(posted_links)} ссылок, {len(posted_titles)} заголовков")
    print(f"📂 Последний источник: {last_source.upper()}")
    print(f"📊 Индексы: сайты={site_index}, телеграм={tg_index}\n")

    if last_source == 'site':
        current_source = 'tg'
        feeds = TG_FEEDS
        start_index = tg_index
    else:
        current_source = 'site'
        feeds = SITE_FEEDS
        start_index = site_index

    print(f"📰 Текущая категория: {current_source.upper()}")
    print(f"📡 Проверяем все {len(feeds)} источников...\n")

    raw_news, next_index = get_all_news_from_category(feeds, start_index)

    print(f"\n📊 Всего собрано: {len(raw_news)} новостей")

    unique_news = []
    for item in raw_news:
        if item['link'] in posted_links:
            continue
        normalized = normalize_title(item['title'])
        if normalized in posted_titles:
            continue
        if not is_relevant(item):
            continue
        unique_news.append(item)

    print(f"✅ После фильтрации: {len(unique_news)} подходящих новостей\n")

    if not unique_news:
        print(f"❌ В категории {current_source.upper()} нет новых новостей.")
        print(f"💾 Сохраняем индекс {next_index} для следующего запуска.")
        if current_source == 'site':
            memory['site_index'] = next_index
        else:
            memory['tg_index'] = next_index
        save_memory(memory)
        return

    news_item = unique_news[0]
    print(f"📝 Выбираем: {news_item['title'][:60]}...")
    print(f"📡 Источник: {news_item['source']}\n")

    if is_from_telegram(news_item['feed_url']):
        print("→ Промпт: TELEGRAM (рерайт + антиреклама)")
        post_text = process_tg_news(news_item)
    else:
        print("→ Промпт: САЙТ (перевод + саммари)")
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
        
        memory['last_source'] = current_source
        
        save_memory(memory)
        print(f"💾 Память сохранена.")
        print(f"🔄 Следующий запуск будет из категории: {'TELEGRAM' if current_source == 'site' else 'САЙТОВ'}")
        print(f" Индексы: сайты={memory['site_index']}, телеграм={memory['tg_index']}")
    else:
        print("❌ Не удалось опубликовать.")

if __name__ == "__main__":
    main()
