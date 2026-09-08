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
    'https://mdpress.ru/news/rss/',
    'https://www.cmjournal.ru/blogs/mezhdunarodnye-publikatsii-i-novosti/rss/',
    'https://www.thelancet.com/rss',
    'https://www.jaad.org/rss',
    'https://onlinelibrary.wiley.com/feed/14732165',
    'https://www.dermatologytimes.com/rss',
    'https://anndermatol.org/rss.php',
]

TG_FEEDS = [
    'https://tg.i-c-a.su/rss/chatkosmetologa',
    'https://tg.i-c-a.su/rss/d_dermatology',
    'https://tg.i-c-a.su/rss/cosmetologich',
    'https://tg.i-c-a.su/rss/cosmetologiainside',
    'https://tg.i-c-a.su/rss/lubaeva',
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
    """Загружаем память с защитой от дубликатов по ссылке и заголовку"""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Конвертация старого формата (просто список ссылок)
            if isinstance(data, list):
                return {
                    'posted_links': data,
                    'posted_titles': [],
                    'site_index': 0, 'tg_index': 0,
                    'last_source': 'tg'  # Начинаем с сайтов
                }
            # Если файл новой структуры, но без поля posted_titles
            if 'posted_titles' not in data:
                data['posted_titles'] = []
            if 'last_source' not in data:
                data['last_source'] = 'tg'
            return data
    return {
        'posted_links': [],
        'posted_titles': [],
        'site_index': 0, 'tg_index': 0,
        'last_source': 'tg'  # Начинаем с сайтов
    }

def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def normalize_title(title):
    """Приводим заголовок к стандартному виду для сравнения"""
    title = title.lower().strip()
    # Убираем спецсимволы в конце
    title = re.sub(r'[.!?\s]+$', '', title)
    # Убираем лишние пробелы внутри
    title = re.sub(r'\s+', ' ', title)
    return title

# ========== ЧТЕНИЕ RSS ==========
def clean_html(text):
    """Убираем HTML-теги из текста"""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return text.strip()

def get_news_from_rss(feed_url, max_items=2):
    try:
        feed = feedparser.parse(feed_url)
        news_list = []
        for entry in feed.entries[:max_items]:
            raw = entry.get('summary', entry.get('description', ''))
            summary = clean_html(raw)
            summary = (summary[:600] + '...') if len(summary) > 600 else summary

            news_list.append({
                'title': clean_html(entry.title),
                'summary': summary,
                'link': entry.link,
                'source': feed.feed.get('title', 'Неизвестный источник'),
                'feed_url': feed_url,
            })
        return news_list
    except Exception as e:
        print(f"️ Ошибка чтения {feed_url}: {e}")
        return []

def get_news_round_robin(feeds, start_index):
    """Читаем новости по кругу из всех источников"""
    num = len(feeds)
    if num == 0:
        return [], 0
    all_news = []
    for i in range(num):
        idx = (start_index + i) % num
        all_news.extend(get_news_from_rss(feeds[idx], max_items=2))
        time.sleep(0.5)  # Пауза между запросами к сайтам
    return all_news, (start_index + 1) % num

# ========== ФИЛЬТРЫ ==========
def is_from_telegram(feed_url):
    """Определяем, пришёл ли пост из Telegram-канала"""
    return 'tg.i-c-a.su' in feed_url or 'rsshub.app/telegram' in feed_url

def is_relevant(news_item):
    """Для The Lancet: пропускаем новости не по теме"""
    if 'thelancet.com' not in news_item.get('feed_url', ''):
        return True  # Другие источники не фильтруем
    text = (news_item['title'] + ' ' + news_item['summary']).lower()
    return any(kw in text for kw in RELEVANT_KEYWORDS)

# ========== ПРОМПТЫ ==========
def process_site_news(news_item):
    """Промпт 1: для сайтов (перевод + саммари)"""
    prompt = f"""Ты — главный редактор Telegram-канала о косметологии и доказательной медицине.

ИСТОЧНИК: {news_item['source']}
ОРИГИНАЛЬНЫЙ ЗАГОЛОВОК: {news_item['title']}
ТЕКСТ: {news_item['summary']}

ЗАДАЧА:
1. Переведи заголовок на русский. Сделай его цепляющим, но профессиональным. Оберни в тег <b>жирный</b>.
2. Напиши саммари в 2-3 предложениях. Живой язык, без канцеляризмов. Добавь 1-2 эмодзи (🔬  🧬 🌿).
3. В конце добавь: 🔗 <a href="{news_item['link']}">Читать в источнике</a>
4. Добавь 2-3 хэштега (#косметология #медицина #исследования и т.д.).

ОТВЕТЬ ТОЛЬКО готовым HTML-текстом поста. Без вступлений и комментариев."""

    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты медицинский редактор. Строго следуй формату HTML."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=500
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq (сайт): {e}")
        return None

def process_tg_news(news_item):
    """Промпт 2: для Telegram (рерайт + антиреклама)"""
    prompt = f"""Ты — главный редактор Telegram-канала о косметологии. Тебе прислали текст поста.

ТЕКСТ:
{news_item['summary']}

ЗАДАЧА — выполни ДВА шага:

ШАГ 1: Определи, является ли этот пост РЕКЛАМОЙ.
Реклама — это:
- Прямая продажа курса, вебинара, марафона, консультации
- Призыв «запишись», «купи», «жми ссылку», «осталось 3 места»
- Продвижение конкретной клиники с адресом и телефоном
- Партнёрская ссылка или промокод
- Розыгрыш, giveaway, конкурс
- Упоминание конкретного автора/блогера с призывом подписаться

Если это реклама — ответь ОДНИМ словом: SKIP

ШАГ 2: Если это НЕ реклама (полезный пост, разбор кейса, научная новость,
совет, обзор процедуры, лайфхак для пациентов), то:
1. Придумай цепляющий заголовок, оберни в <b>жирный</b>.
2. Перепиши текст СВОИМИ словами. Сохрани суть и факты, но сделай уникальным.
3. Суть в 2-4 предложениях. Живой язык, 1-2 тематических эмодзи.
4. Добавь 2-3 релевантных хэштега (#косметология #медицина и т.д.).

ВАЖНО:
- НЕ упоминай, откуда взят материал.
- НЕ добавляй ссылки на оригинал.
- НЕ копируй текст дословно.
- Пиши так, будто это авторский контент твоего канала.

ОТВЕТЬ ТОЛЬКО готовым HTML-текстом поста или словом SKIP.
Никаких вступлений и комментариев."""

    try:
        resp = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": "Ты редактор. Отвечай ТОЛЬКО текстом поста или словом SKIP."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600
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
    data = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false"
    }
    try:
        resp = requests.post(url, data=data, timeout=15)
        result = resp.json()
        if result.get('ok'):
            print(f"✅ Опубликовано в {CHANNEL_ID}!")
            return True
        print(f"️ Telegram вернул: {result}")
    except Exception as e:
        print(f"️ Ошибка Telegram: {e}")
    return False

# ========== ГЛАВНЫЙ ЦИКЛ ==========
def main():
    print("🚀 Запуск агрегатора (Косметология и Медицина)...\n")

    memory = load_memory()
    posted_links = memory.get('posted_links', [])
    posted_titles = memory.get('posted_titles', [])
    site_index = memory.get('site_index', 0)
    tg_index = memory.get('tg_index', 0)
    last_source = memory.get('last_source', 'tg')

    print(f" В памяти: {len(posted_links)} ссылок, {len(posted_titles)} заголовков")
    print(f"📂 Последний источник: {last_source.upper()}\n")

    # СТРОГОЕ ЧЕРЕДОВАНИЕ: если последний был сайт, теперь берем из TG, и наоборот
    if last_source == 'site':
        feeds = TG_FEEDS
        start_index = tg_index
        current_source = 'tg'
        print(f"📱 Берем из: Telegram-каналы ({len(feeds)} источников)")
    else:
        feeds = SITE_FEEDS
        start_index = site_index
        current_source = 'site'
        print(f"📰 Берем из: Сайты ({len(feeds)} источников)")

    raw_news, next_index = get_news_round_robin(feeds, start_index)

    # ТРОЙНАЯ ЗАЩИТА ОТ ПОВТОРОВ:
    # 1. По ссылке (URL)
    # 2. По нормализованному заголовку
    # 3. По релевантности теме
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

    print(f" Найдено {len(raw_news)} → новых и по теме: {len(unique_news)}\n")

    if not unique_news:
        print(f"🔄 Новых новостей в {current_source.upper()} нет. Пропускаем этот час.")
        # Сохраняем индекс, но не меняем last_source
        if current_source == 'site':
            memory['site_index'] = next_index
        else:
            memory['tg_index'] = next_index
        save_memory(memory)
        return

    news_item = unique_news[0]
    print(f" Обрабатываем: {news_item['title'][:50]}...")

    # Выбираем промпт в зависимости от источника
    if is_from_telegram(news_item['feed_url']):
        print("   → Промпт: TELEGRAM (рерайт + антиреклама)")
        post_text = process_tg_news(news_item)
    else:
        print("   → Промпт: САЙТ (перевод + саммари)")
        post_text = process_site_news(news_item)

    if not post_text:
        # Пост был рекламой или произошла ошибка —
        # помечаем ссылку как обработанную, чтобы не крутить её вечно
        posted_links.append(news_item['link'])
        posted_titles.append(normalize_title(news_item['title']))
        memory['posted_links'] = posted_links[-1000:]
        memory['posted_titles'] = posted_titles[-1000:]
        if current_source == 'site':
            memory['site_index'] = next_index
        else:
            memory['tg_index'] = next_index
        # Не меняем last_source, так как пост не опубликован
        save_memory(memory)
        print("⏭ Пропущено (реклама или ошибка).")
        return

    print("\n--- ГОТОВЫЙ ПОСТ ---")
    print(post_text)
    print("--------------------\n")

    if post_to_telegram(post_text):
        posted_links.append(news_item['link'])
        posted_titles.append(normalize_title(news_item['title']))
        
        # Храним последние 1000 записей
        memory['posted_links'] = posted_links[-1000:]
        memory['posted_titles'] = posted_titles[-1000:]

        if current_source == 'site':
            memory['site_index'] = next_index
        else:
            memory['tg_index'] = next_index

        # Обновляем last_source для строгого чередования
        memory['last_source'] = current_source
        save_memory(memory)
        print(f"🎉 Готово! Следующий пост будет из: {'TELEGRAM' if current_source == 'site' else 'САЙТОВ'}")
    else:
        print("❌ Не удалось опубликовать.")

if __name__ == "__main__":
    main()
