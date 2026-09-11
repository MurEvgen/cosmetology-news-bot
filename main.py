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

# ========== КАТЕГОРИИ ИСТОЧНИКОВ ==========
SITE_FEEDS = [
    'https://www.sciencedaily.com/rss/health_medicine/skin_care.xml',
    'https://www.healio.com/rss/dermatology',
    'https://www.bosa.co.kr/rss/allArticle.xml',
    'https://m.koreaherald.com/rss/newsAll',
    'https://en.yna.co.kr/RSS/news.xml',
    'https://www.scmp.com/rss/2/feed',
    'https://weekly.chinacdc.cn/rss/current.xml',
    'https://nplus1.ru/rss',
    'https://elementy.ru/rss/news',
    'https://scientificrussia.ru/rss',
]

SCIENCE_FEEDS = [
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

CATEGORIES = ['site', 'science', 'tg']

# ========== ✅ БЕЛЫЙ СПИСОК ==========
WHITELIST_KEYWORDS = [
    # 🧴 ЗАБОЛЕВАНИЯ КОЖИ (EN)
    'acne', 'pimples', 'blackheads', 'comedone',
    'psoriasis', 'eczema', 'atopic dermatitis', 'contact dermatitis', 'seborrheic dermatitis',
    'rosacea', 'couperose', 'melasma',
    'melanoma', 'basal cell carcinoma', 'squamous cell carcinoma', 'skin cancer',
    'vitiligo', 'hyperpigmentation', 'pigmentation', 'lentigo',
    'alopecia', 'hair loss', 'telogen effluvium', 'androgenetic alopecia',
    'dermatitis', 'pruritus', 'urticaria',
    'warts', 'molluscum', 'onychomycosis', 'fungal skin',
    'scabies', 'folliculitis', 'impetigo',
    'actinic keratosis', 'seborrheic keratosis',
    'cutaneous lupus', 'lichen planus',
    'pemphigus', 'scleroderma', 'morphea', 'xerosis', 'ichthyosis',
    
    # 💉 ЭСТЕТИЧЕСКИЕ ПРОЦЕДУРЫ (EN)
    'botox', 'botulinum toxin', 'botulinum', 'dysport', 'xeomin',
    'filler', 'dermal filler', 'hyaluronic acid filler',
    'lip augmentation', 'cheek filler',
    'mesotherapy', 'biorevitalization', 'skin booster',
    'prp', 'platelet-rich plasma', 'prf', 'platelet-rich fibrin',
    'microneedling', 'dermapen', 'collagen induction',
    'chemical peel', 'glycolic peel', 'salicylic peel', 'tca peel',
    'laser treatment', 'laser resurfacing', 'co2 laser', 'erbium laser',
    'ipl', 'intense pulsed light', 'photorejuvenation',
    'radiofrequency', 'rf treatment', 'microneedling rf',
    'hifu', 'ultherapy', 'ultrasound lifting',
    'cryotherapy', 'cryolipolysis',
    'thread lift', 'pdo threads',
    'lipolysis', 'deoxycholic acid',
    'skin tightening', 'non-surgical facelift',
    'dermabrasion', 'microdermabrasion',
    'tattoo removal', 'laser hair removal',
    'scar treatment', 'keloid', 'hypertrophic scar',
    'stretch marks', 'striae', 'hyperhidrosis',
    
    # 🧖 УХОД ЗА КОЖЕЙ (EN)
    'skincare', 'skin care', 'skin barrier',
    'moisturizer', 'hydration', 'humectant',
    'sunscreen', 'sun protection', 'spf', 'uv protection', 'photoprotection',
    'anti-aging', 'anti-ageing', 'rejuvenation',
    'collagen', 'elastin', 'hyaluronic acid',
    'retinol', 'retinoid', 'tretinoin', 'adapalene',
    'vitamin c', 'ascorbic acid', 'antioxidant',
    'niacinamide', 'peptide', 'growth factor', 'exosome',
    'ceramide', 'lipid barrier',
    'exfoliation', 'aha', 'bha', 'glycolic acid', 'salicylic acid',
    'cleanser', 'toner', 'serum', 'sheet mask',
    'k-beauty', 'korean skincare',
    'sensitive skin', 'dry skin', 'oily skin',
    'pore', 'skin texture', 'skin tone',
    
    # 💇 ТРИХОЛОГИЯ (EN)
    'hair care', 'hair growth', 'hair restoration',
    'hair transplant', 'scalp health', 'dandruff', 'seborrhea',
    'hair thinning', 'minoxidil', 'finasteride',
    
    # 🔬 ДЕРМАТОЛОГИЧЕСКИЕ ТЕРМИНЫ (EN)
    'dermatology', 'dermatologist', 'cosmetic dermatology',
    'aesthetic medicine', 'aesthetic dermatology',
    'skin biopsy', 'dermoscopy',
    'epidermis', 'dermis', 'keratinocyte', 'melanocyte',
    'stratum corneum', 'skin microbiome',
    'photoaging', 'wrinkle', 'fine lines',
    'skin laxity', 'melanin', 'tyrosinase',
    
    # 🇷🇺 РУССКИЕ ТЕРМИНЫ
    'акне', 'угри', 'прыщи', 'комедон',
    'псориаз', 'экзема', 'дерматит', 'атопический дерматит', 'себорейный дерматит',
    'розацеа', 'купероз',
    'меланома', 'базалиома', 'рак кожи',
    'витилиго', 'пигментация', 'гиперпигментация', 'мелазма',
    'алопеция', 'облысение', 'выпадение волос',
    'зуд', 'крапивница',
    'бородавки', 'онихомикоз', 'грибок кожи',
    'кератоз',
    
    'ботокс', 'ботулотоксин', 'диспорт', 'ксеомин',
    'филлер', 'гиалуроновый филлер', 'увеличение губ',
    'мезотерапия', 'биоревитализация', 'скин-бустер',
    'плазмолифтинг', 'плазмотерапия',
    'микроигольчатая терапия', 'дермапен',
    'химический пилинг', 'пилинг',
    'лазерная шлифовка', 'лазерная терапия', 'со2 лазер', 'эрбиевый лазер',
    'фототерапия', 'фотомоложение', 'фотоомоложение',
    'радиочастотный лифтинг', 'rf-лифтинг', 'рф-лифтинг',
    'нитяной лифтинг', 'нитевой лифтинг', 'тредлифтинг',
    'криотерапия', 'криолиполиз',
    'удаление тату', 'лазерная эпиляция',
    'лечение рубцов', 'келоид', 'растяжки', 'стрии',
    'гипергидроз', 'потливость',
    
    'уход за кожей', 'кожный барьер',
    'увлажнение', 'гидратация',
    'солнцезащитный крем', 'солнцезащита', 'спф',
    'антивозрастной', 'омоложение', 'противовозрастной',
    'коллаген', 'эластин', 'гиалуроновая кислота',
    'ретинол', 'ретиноид', 'третиноин',
    'витамин с', 'антиоксидант',
    'ниацинамид', 'пептид', 'фактор роста', 'экзосома',
    'керамид',
    'отшелушивание',
    'сыворотка', 'тоник', 'маска для лица',
    'чувствительная кожа', 'сухая кожа', 'жирная кожа',
    'поры', 'текстура кожи', 'тон кожи',
    
    'уход за волосами', 'рост волос', 'восстановление волос',
    'пересадка волос', 'кожа головы', 'перхоть', 'себорея',
    'миноксидил',
    
    'дерматология', 'дерматолог', 'косметолог', 'косметология',
    'эстетическая медицина', 'эстетическая дерматология',
    'биопсия кожи', 'дерматоскопия',
    'эпидермис', 'дерма', 'кератиноцит', 'меланоцит',
    'микробиом кожи',
    'фотостарение', 'морщины', 'дряблость кожи',
    
    # 🇰🇷 КОРЕЙСКИЕ ТЕРМИНЫ
    '피부', '피부과',
    '여드름', '건선', '습진', '아토피',
    '흑색종', '백반증', '색소침착', '기미',
    '탈모', '원형탈모',
    '보톡스', '필러',
    '메조테라피', '물광주사',
    '레이저', '피부레이저',
    '필링', '리프팅', '실리프팅',
    '주름', '탄력', '미백', '보습', '수분',
    '자외선차단', '선크림',
    '미용', '뷰티',
    '스킨케어',
    '콜라겐', '히알루론산', '펩타이드',
    '레티놀',
    
    # 🇨🇳 КИТАЙСКИЕ ТЕРМИНЫ
    '皮肤', '皮肤科',
    '痤疮', '粉刺', '银屑病', '湿疹', '皮炎',
    '玫瑰痤疮', '黑色素瘤', '白癜风', '色素沉着', '黄褐斑',
    '脱发', '斑秃',
    '肉毒素', '玻尿酸', '填充剂',
    '水光针', '激光', '光子嫩肤',
    '化学换肤', '果酸换肤',
    '射频', '热玛吉', '超声刀', '线雕', '埋线提升',
    '皱纹', '抗衰老', '年轻化', '美白', '祛斑',
    '保湿', '补水', '防晒', '防晒霜',
    '美容', '护肤品',
    '胶原蛋白', '透明质酸', '多肽', '视黄醇',
]

# ========== ❌ НЕГАТИВНЫЙ СПИСОК ==========
NEGATIVE_KEYWORDS = [
    # 🏙️ УРБАНИСТИКА / ИНФРАСТРУКТУРА
    'urban planning', 'urban development', 'city planning',
    'data centre', 'data center', 'smart city', 'metropolis',
    'infrastructure project', 'transport corridor',
    'урбанист', 'градостроит', 'инфраструктурн проект',
    'транспортный коридор', 'метрополис', 'дата-центр',
    'northern metropolis', 'северная метрополия',
    'green data centre', 'logistics flow', 'логистическ поток',
    
    # 💼 БИЗНЕС / РИТЕЙЛ
    'retail network', 'store network', 'chain expansion',
    'opened stores', '200 stores', 'retail points',
    'pharmacy chain', 'store launch', 'business expansion',
    'розничная сеть', 'торговая сеть', 'сеть магазинов',
    'открыл точек', 'сеть аптек', 'аптечная сеть',
    '200 точек', 'розничн', 'бизнес-экспансия',
    'pharmacy beauty zone', 'baropharm',
    'sales channel', 'канал сбыта', 'торговые точки',
    
    # 🌍 ГЕОПОЛИТИКА / ДИПЛОМАТИЯ
    'geopolitics', 'diplomacy', 'diplomatic', 'foreign policy',
    'foreign minister', 'foreign affairs', 'bilateral relations',
    'global south', 'public diplomacy', 'summit',
    'state visit', 'international relations',
    'strait', 'ormuz', 'strait of ormuz',
    'геополитик', 'дипломат', 'внешняя политика',
    'министр иностранных дел', 'международные отношения',
    'публичная дипломатия', 'государственный визит',
    'глобальный юг', 'двусторонние отношения',
    'пролив', 'ормуз',
    'phone call between ministers', 'телефонные переговоры',
    'развивающиеся страны', 'многосторонн',
    
    # 💊 ФАРМАЦЕВТИЧЕСКИЙ БИЗНЕС / ОБЩАЯ ОНКОЛОГИЯ
    'series a', 'series b', 'funding round', 'venture capital',
    'pharmaceutical investment', 'drug development',
    'solid tumor', 'solid tumour', 'oncology drug',
    'anti-cancer', 'peptide-drug conjugate', 'pdc therapy',
    'раунд финансирования', 'венчурн', 'инвестиции в разработку',
    'солидн опухол', 'противораков', 'онкопрепарат',
    'pdc', 'two step therapeutics', 'twostep',
    'fda approved', 'clinical trial', 'phase i', 'phase ii', 'phase iii',
    'клиническ испытан', 'фазы испытан',
    'pfizer', 'merck', 'oncology',
    'таргетн терап', 'онколог',
    
    # 🚀 ВОЕННАЯ / ОБОРОННАЯ ТЕМАТИКА
    'missile', 'rocket', 'weapon', 'military', 'defense', 'defence',
    'aerospace', 'army', 'navy', 'air force', 'armed forces',
    'artillery', 'tank', 'fighter jet', 'warship', 'submarine',
    'nuclear weapon', 'arms deal', 'arms export', 'defense contract',
    'munition', 'ammunition', 'warfare', 'combat',
    'ракет', 'оружие', 'военн', 'оборон', 'вооружен',
    'армия', 'флот', 'артиллери', 'танк', 'истребитель',
    'подводная лодка', 'корабль', 'ядерн', 'ополчен',
    'боеприпас', 'боеголов', 'вооружение', 'оборонительн',
    'hanwha', 'chunmoo', 'chunmu', 'k2 tank', 'kf-21', 'k9 howitzer',
    'ханва', 'чунму',
    
    # 🚬 Табак
    'cigarette', 'tobacco', 'smoking', 'vaping', 'e-cigarette',
    'сигарет', 'табак', 'курение', 'вейп',
    
    # ⚡ Энергетика/промышленность
    'power plant', 'energy equipment', 'nuclear', 'coal mine',
    'энергетическое оборудование', 'электростанция', 'атомная энергетика',
    
    # 🔬 Физика/оптика (НЕ медицинская)
    'physics conference', 'optics conference', 'laser physics', 'quantum optics',
    'photonics research', 'spectroscopy', 'laser beam', 'optical fiber',
    'конференция по физике', 'лазерная физика', 'квантовая оптика', 'фотоника',
    'оптике', 'оптика',
    
    # 🏬 Прочий ритейл
    'retail store opening', 'fashion store', 'flagship store opening',
    'music platform', 'entertainment company', 'k-pop', 'idol group',
    'открытие магазина', 'флагманский магазин', 'музыкальная платформа',
    
    # 📚 Литература/культура
    'writers festival', 'literary festival', 'book festival', 'poetry reading',
    'novel launch', 'author event', 'literary award', 'book fair',
    'cultural festival', 'film festival', 'music festival', 'art exhibition',
    'сеульский фестиваль писателей', 'фестиваль писателей',
    'литературный фестиваль', 'книжная ярмарка', 'поэтический вечер',
    'писатель', 'поэт', 'романист', 'прозаик', 'литературн',
    
    # 🎬 Кино/искусство
    'cultural context', 'historical drama', 'joseon dynasty', 'dynasty era',
    'movie premiere', 'film director', 'tv series', 'web drama',
    'историческая драма', 'династия чосон', 'кинопремьера', 'сериал',
    'культурный контекст', 'эпоха чосон',
    
    # 📈 Политика/экономика
    'stock market', 'economic policy', 'trade war', 'inflation',
    'interest rate', 'currency exchange', 'gdp growth', 'stock exchange',
    'фондовый рынок', 'экономическая политика', 'торговая война', 'инфляция',
    
    # 🎓 Образование
    'university ranking', 'school curriculum', 'student exam',
    'рейтинг университетов', 'школьная программа',
    
    # 🚗 Транспорт/инфраструктура
    'highway construction', 'railway project', 'airport expansion',
    'строительство дороги', 'железная дорога',
    
    # 🦴 РЕВМАТОЛОГИЯ / ОРТОПЕДИЯ
    'rheumatoid arthritis', 'rheumatoid', 'osteoarthritis', 'arthritis',
    'joint inflammation', 'autoimmune joint', 'synovial', 'synovitis',
    'ревматоидный артрит', 'ревматоид', 'остеоартр', 'артрит',
    'воспаление суставов', 'суставн', 'сустав', 'суставы', 'синов',
    'хрящевая ткань', 'хрящ',
    
    # 🫀 КАРДИОЛОГИЯ / НЕВРОЛОГИЯ
    'cardiac', 'heart attack', 'cardiovascular disease', 'myocardial',
    'stroke', 'neurological disorder', 'alzheimer', 'parkinson',
    'инфаркт', 'инсульт', 'кардиолог', 'неврологич', 'болезнь альцгеймера',
    
    # 🦠 ОБЩАЯ ОНКОЛОГИЯ (рак кожи оставляем!)
    'lung cancer', 'breast cancer', 'prostate cancer', 'colon cancer',
    'leukemia', 'lymphoma', 'glioblastoma',
    'рак легких', 'рак груди', 'рак простаты', 'лейкемия', 'лимфома',
    
    # 🧠 СИСТЕМНЫЕ БОЛЕЗНИ
    'systemic lupus', 'crohn disease', 'ulcerative colitis', 'celiac',
    'fibromyalgia', 'системная красная волчанка', 'болезнь крона', 'целиакия',
    
    # 🏥 ХИРУРГИЯ / ТРАНСПЛАНТОЛОГИЯ
    'organ transplant', 'liver transplant', 'kidney transplant',
    'heart surgery', 'bypass surgery',
    'пересадка органа', 'шунтирование',
    
    # 👶 ОБЩАЯ ПЕДИАТРИЯ
    'childhood vaccination', 'pediatric nutrition', 'infant formula',
    'детские прививки', 'детское питание',
    
    # 🧬 ОБЩАЯ ГЕНЕТИКА
    'genome sequencing', 'gene editing', 'crispr study',
    'секвенирование генома',
]

# ========== КОНТЕКСТНЫЕ ПАРЫ ==========
CONTEXT_PAIRS = {
    'laser': ['dermatology', 'skin', 'cosmetic', 'aesthetic', 'treatment',
              'therapy', 'surgery', 'hair removal', 'resurfacing',
              'лазерная терапия', 'лазерное лечение', 'лазерная шлифовка'],
    'beauty': ['skincare', 'cosmetic', 'aesthetic', 'procedure', 'treatment',
               'product', 'cream', 'serum', 'skin', 'уход за кожей',
               'косметическ', 'dermatology'],
    'aesthetic': ['medicine', 'procedure', 'treatment', 'surgery', 'dermatology',
                  'cosmetic', 'injectable', 'filler', 'skin', 'clinic',
                  'эстетическая медицина', 'косметолог'],
    'store': ['cosmetic', 'beauty', 'skincare', 'dermatology', 'pharmacy',
              'магазин косметики'],
    'festival': ['beauty expo', 'cosmetic expo', 'dermatology congress',
                 'medical congress', 'конгресс дерматологов',
                 'косметическая выставка'],
    'culture': ['cell culture', 'tissue culture', 'bacterial culture',
                'клеточная культура', 'тканевая культура'],
    
    # 🆕 Новые контекстные пары
    'peptide': ['skincare', 'cosmetic', 'anti-aging', 'cream', 'serum',
                'collagen', 'wrinkle', 'moisturizer', 'dermatology',
                'крем', 'сыворотка', 'уход за кожей', 'коллаген',
                'морщины', 'увлажн', 'косметическ', 'anti-age',
                'skin care', 'rejuvenation', 'омоложен'],
    'pharmacy': ['cosmetic', 'dermatology', 'skincare', 'drug',
                 'аптечная косметика', 'дерматологическ', 'лекарственн'],
    'k-beauty': ['skincare', 'cosmetic', 'skin', 'routine', 'dermatology',
                 'уход за кожей', 'косметическ', 'процедур'],
    'invest': ['dermatology', 'cosmetic', 'skincare', 'beauty',
               'инвестиции в косметолог', 'инвестиции в уход'],
    '뷰티': ['피부', '스킨케어', '피부과', '화장품', '미용'],
    '화장품': ['피부', '피부과', '스킨케어', '미용'],
}

# Источники, требующие строгой проверки
GENERAL_NEWS_SOURCES = [
    'scmp', 'china daily', 'korea herald', 'yonhap',
    'nplus1', 'elementy', 'scientific russia',
    'bosa.co.kr', 'yna.co.kr', '의학신문',
]
CULTURE_RISK_SOURCES = [
    'korea herald', 'yonhap', 'china daily', 'scmp',
    'bosa.co.kr', 'yna.co.kr',
]

# 🎯 Специализированные источники (ТОЛЬКО профильные дерматологические)
SPECIALIZED_SOURCES = [
    'healio',
    'sciencedaily',
    'skin care news',
    'forum kosmetolog', 'дневник дерматовен',
    'чат косметолог', 'косметология inside',
    'dermatolog', 'kosmetolog',
    'pubmed', 'crossref', 'semanticscholar',
    'europepmc', 'medrxiv', 'lancet',
]

# ========== ПАМЯТЬ ==========
def load_memory():
    default = {
        'posted_links': [], 'posted_titles': [],
        'site_index': 0, 'science_index': 0, 'tg_index': 0,
        'next_category': 'site',
    }
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                data = {'posted_links': data}
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            if data.get('next_category') not in CATEGORIES:
                data['next_category'] = 'site'
            return data
        except Exception:
            return default
    return default

def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def normalize_title(title):
    title = title.lower().strip()
    title = re.sub(r'[.!?\s]+$', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title

# ========== 📅 ПАРСИНГ ДАТ ==========
def parse_publication_date(news_item):
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        feed = feedparser.parse(feed_url, request_headers=headers)
        source_title = feed.feed.get('title', 'Unknown')
        print(f"   🔍 {source_title} (Status: {getattr(feed, 'status', 'N/A')}): записей {len(feed.entries)}")

        news_list = []
        for entry in feed.entries[:max_items]:
            raw = entry.get('summary', entry.get('description', ''))
            summary = clean_html(raw)
            summary = (summary[:1500] + '...') if len(summary) > 1500 else summary
            date_info = parse_publication_date({'title': entry.title, 'summary': summary})
            news_list.append({
                'title': clean_html(entry.title),
                'summary': summary,
                'link': entry.link,
                'source': source_title,
                'feed_url': feed_url,
                'date_info': date_info,
            })
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка чтения {feed_url}: {e}")
        return []

# ========== 🔬 НАУЧНЫЕ API ==========
def fetch_abstract_from_openalex(doi):
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        resp = requests.get(url, params={"mailto": CONTACT_EMAIL}, timeout=10)
        if resp.status_code != 200:
            return ""
        inv = resp.json().get("abstract_inverted_index")
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
    try:
        url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "filter": f"issn:{issn},type:journal-article",
            "sort": "published", "order": "desc",
            "rows": max_items, "mailto": CONTACT_EMAIL,
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code != 200:
            print(f"   ⚠️ Crossref статус {resp.status_code}")
            return []
        items = resp.json().get("message", {}).get("items", [])
        source_name = "The Lancet" if issn == "0140-6736" else f"Journal {issn}"
        print(f"   🔍 {source_name} (Crossref): записей {len(items)}")

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
            year = date_parts[0] if date_parts and date_parts[0] else None
            current_year = datetime.now().year
            is_future = year and year > current_year

            abstract = re.sub(r'<[^>]+>', '', item.get("abstract", "") or "").strip()
            if not abstract and n < 4 and doi:
                abstract = fetch_abstract_from_openalex(doi)
                time.sleep(0.3)

            if abstract:
                summary = (abstract[:1500] + '...') if len(abstract) > 1500 else abstract
            else:
                summary = f"Научная статья в журнале {source_name}. Тема: {title}. Авторы: {authors_str}."
            summary += f" | Авторы: {authors_str}. Источник: {source_name}."
            if year:
                summary += f" Год: {year}."

            news_list.append({
                'title': title, 'summary': summary, 'link': link,
                'source': source_name, 'feed_url': f"crossref:{issn}",
                'date_info': {'year': year, 'is_future': is_future,
                             'status': 'препринт/в печати' if is_future else 'опубликовано'}
            })
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка Crossref: {e}")
        return []

def get_news_from_pubmed(query, max_items=8):
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": f"({query}) AND (free full text[SB] OR open access[Filter])",
            "retmax": max_items, "sort": "pub_date", "retmode": "json",
            "email": CONTACT_EMAIL,
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"   ⚠️ PubMed статус {resp.status_code}")
            return []
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            print("   🔍 PubMed: записей 0")
            return []
        url_summ = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        params_summ = {"db": "pubmed", "id": ",".join(ids), "retmode": "json", "email": CONTACT_EMAIL}
        resp2 = requests.get(url_summ, params=params_summ, headers=headers, timeout=15)
        if resp2.status_code != 200:
            return []
        docs = resp2.json().get("result", {})
        print(f"   🔍 PubMed: записей {len(ids)}")

        news_list = []
        for pmid in ids:
            doc = docs.get(pmid, {})
            title = doc.get("title", "") if doc else ""
            if not title:
                continue
            authors = ", ".join(a.get("name", "") for a in doc.get("authors", [])[:3]) or "не указаны"
            pubdate = doc.get("pubdate", "")
            year = None
            is_future = False
            if pubdate:
                year_match = re.search(r'\b(20\d{2})\b', pubdate)
                if year_match:
                    year = int(year_match.group(1))
                    is_future = year > datetime.now().year
            summary = f"Научная статья в PubMed. PMID: {pmid}. Авторы: {authors}. Опубликовано: {pubdate}."
            news_list.append({
                'title': title, 'summary': summary,
                'link': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                'source': 'PubMed', 'feed_url': 'pubmed:dermatology',
                'date_info': {'year': year, 'is_future': is_future,
                             'status': 'препринт/в печати' if is_future else 'опубликовано'}
            })
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка PubMed: {e}")
        return []

def get_news_from_semantic_scholar(query, max_items=6):
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query, "limit": max_items,
            "fields": "title,abstract,authors,year,url,tldr,externalIds",
            "year": "2024-2026",
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 429:
            print("   ⚠️ Semantic Scholar: rate limit")
            return []
        if resp.status_code != 200:
            print(f"   ⚠️ Semantic Scholar статус {resp.status_code}")
            return []
        items = resp.json().get("data", [])
        print(f"   🔍 Semantic Scholar: записей {len(items)}")

        news_list = []
        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            abstract = item.get("abstract") or ""
            tldr = (item.get("tldr") or {}).get("text", "")
            authors = ", ".join(a.get("name", "") for a in (item.get("authors") or [])[:3]) or "не указаны"
            year = item.get("year")
            is_future = year and year > datetime.now().year
            doi = (item.get("externalIds") or {}).get("DOI")
            link = f"https://doi.org/{doi}" if doi else (item.get("url") or "")
            summary = tldr or abstract or f"Научная статья. Авторы: {authors}. Год: {year}."
            summary = (summary[:1500] + '...') if len(summary) > 1500 else summary
            summary += f" | Авторы: {authors}. Год: {year}."
            news_list.append({
                'title': title, 'summary': summary, 'link': link,
                'source': 'Semantic Scholar', 'feed_url': 'semanticscholar:dermatology',
                'date_info': {'year': year, 'is_future': is_future,
                             'status': 'препринт/в печати' if is_future else 'опубликовано'}
            })
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка Semantic Scholar: {e}")
        return []

def get_news_from_medrxiv(max_items=6):
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        url = f"https://api.medrxiv.org/details/medrxiv/{start_date}/{end_date}/0"
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            print(f"   ⚠️ medRxiv статус {resp.status_code}")
            return []
        items = resp.json().get("collection", [])
        print(f"   🔍 medRxiv: препринтов {len(items)}")

        skin_keywords = ['skin', 'dermat', 'cosmetic', 'aesthetic', 'acne',
                         'psoriasis', 'eczema', 'hair', 'pigment',
                         'vitiligo', 'melanoma', 'rosacea']
        news_list = []
        for item in items[:max_items * 3]:
            title = item.get("title", "")
            if not title:
                continue
            combined = (title + " " + (item.get("abstract") or "") + " " + (item.get("category") or "")).lower()
            if not any(kw in combined for kw in skin_keywords):
                continue
            doi = item.get("doi", "")
            abstract = item.get("abstract", "") or ""
            authors = item.get("authors", "не указаны")
            pub_date = item.get("date", "")
            year = None
            if pub_date:
                year_match = re.search(r'\b(20\d{2})\b', pub_date)
                if year_match:
                    year = int(year_match.group(1))
            summary = (abstract[:1500] + '...') if len(abstract) > 1500 else abstract
            summary += f" | Авторы: {authors}. Препринт: {pub_date}."
            news_list.append({
                'title': f"[Препринт] {title}", 'summary': summary,
                'link': f"https://doi.org/{doi}" if doi else "",
                'source': 'medRxiv', 'feed_url': 'medrxiv:dermatology',
                'date_info': {'year': year, 'is_future': True, 'status': 'препринт'}
            })
            if len(news_list) >= max_items:
                break
        print(f"   🔍 medRxiv по теме: {len(news_list)}")
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка medRxiv: {e}")
        return []

def get_news_from_europepmc(query, max_items=6):
    try:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": f"({query}) AND (OPEN_ACCESS:y OR FIRST_PDATE:[NOW-90DAYS TO NOW])",
            "format": "json",
            "resultType": "core",
            "pageSize": max_items,
            "sort": "FIRST_PDATE desc",
        }
        headers = {"User-Agent": f"CosmetologyNewsBot/1.0 (mailto:{CONTACT_EMAIL})"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"   ⚠️ Europe PMC статус {resp.status_code}")
            return []
        items = resp.json().get("resultList", {}).get("result", [])
        print(f"   🔍 Europe PMC: записей {len(items)}")

        news_list = []
        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            abstract = item.get("abstractText", "")
            authors = ", ".join(a.get("fullName", "") for a in (item.get("authorList", {}).get("author", [])[:3])) or "не указаны"
            year_str = item.get("pubYear", "")
            year = int(year_str) if year_str and year_str.isdigit() else None
            is_future = year and year > datetime.now().year
            pmid = item.get("pmid")
            doi = item.get("doi")
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (f"https://doi.org/{doi}" if doi else "")
            summary = (abstract[:1500] + '...') if len(abstract) > 1500 else abstract
            if not summary:
                summary = f"Научная статья. Авторы: {authors}. Год: {year}."
            summary += f" | Авторы: {authors}. Год: {year}."
            news_list.append({
                'title': title, 'summary': summary, 'link': link,
                'source': 'Europe PMC', 'feed_url': 'europepmc:dermatology',
                'date_info': {'year': year, 'is_future': is_future,
                             'status': 'препринт/в печати' if is_future else 'опубликовано'}
            })
        return news_list
    except Exception as e:
        print(f"   ⚠️ Ошибка Europe PMC: {e}")
        return []

# ========== ДИСПЕТЧЕР ИСТОЧНИКОВ ==========
def fetch_from_feed(feed):
    if feed.startswith('crossref:'):
        parts = feed.split(':', 2)
        return get_news_from_crossref(parts[1], parts[2] if len(parts) > 2 else "dermatology OR skin")
    if feed.startswith('pubmed:'):
        return get_news_from_pubmed(feed.split(':', 1)[1])
    if feed.startswith('semanticscholar:'):
        return get_news_from_semantic_scholar(feed.split(':', 1)[1])
    if feed == 'medrxiv':
        return get_news_from_medrxiv()
    if feed.startswith('europepmc:'):
        return get_news_from_europepmc(feed.split(':', 1)[1])
    return get_news_from_rss(feed, max_items=10)

# ========== 🎯 ФИЛЬТРАЦИЯ ==========
def is_from_telegram(feed_url):
    return 'tg.i-c-a.su' in feed_url or 'rsshub.app/telegram' in feed_url

def is_specialized_source(source):
    source_lower = source.lower()
    return any(spec in source_lower for spec in SPECIALIZED_SOURCES)

def is_relevant(news_item):
    """
    Усиленная логика фильтрации:
    1. Негативные слова → отсев (защита от чужих тем)
    2. Для общих источников: whitelist-слово ОБЯЗАТЕЛЬНО в ЗАГОЛОВКЕ
    3. Для специализированных: whitelist-слово в любом месте
    4. Дополнительная проверка контекста для двусмысленных слов
    """
    title = news_item['title']
    title_lower = title.lower()
    summary_lower = news_item.get('summary', '').lower()
    text = title_lower + ' ' + summary_lower
    source = news_item.get('source', '').lower()

    # 1. ❌ ЖЁСТКИЙ фильтр по негативным словам (первый барьер)
    for neg in NEGATIVE_KEYWORDS:
        if neg.lower() in text:
            print(f"   ❌ Отсеяно (негативное слово '{neg}'): {title[:50]}")
            return False

    # 2. Определяем тип источника
    is_specialized = is_specialized_source(source)
    is_general = any(gen in source for gen in GENERAL_NEWS_SOURCES)
    is_culture_risk = any(cs in source for cs in CULTURE_RISK_SOURCES)

    # 3. ✅ Для ОБЩИХ источников — whitelist-слово ОБЯЗАТЕЛЬНО в ЗАГОЛОВКЕ
    if is_general or is_culture_risk:
        matched_in_title = any(kw.lower() in title_lower for kw in WHITELIST_KEYWORDS)
        if not matched_in_title:
            print(f"   ❌ Отсеяно (нет whitelist в ЗАГОЛОВКЕ, общий источник): {title[:50]}")
            return False
        
        # И дополнительная проверка контекста для двусмысленных слов
        for base_word, context_words in CONTEXT_PAIRS.items():
            if base_word.lower() in text:
                has_medical_context = any(ctx.lower() in text for ctx in context_words)
                if not has_medical_context:
                    print(f"   ❌ Отсеяно (нет мед. контекста для '{base_word}'): {title[:50]}")
                    return False
        
        print(f"   ✅ Прошло (общий источник + whitelist в заголовке): {title[:50]}")
        return True

    # 4. ✅ Для специализированных источников — whitelist в любом месте
    matched_keyword = None
    for kw in WHITELIST_KEYWORDS:
        if kw.lower() in text:
            matched_keyword = kw
            break
    
    if not matched_keyword:
        print(f"   ❌ Отсеяно (нет whitelist-слова): {title[:50]}")
        return False
    
    print(f"   ✅ Прошло по whitelist ('{matched_keyword}'): {title[:50]}")
    return True

def get_feeds_for_category(cat):
    if cat == 'site':
        return SITE_FEEDS
    if cat == 'science':
        return SCIENCE_FEEDS
    return TG_FEEDS

# ========== ПОИСК НОВОСТИ В КАТЕГОРИИ ==========
def find_news_in_category(cat, memory, posted_links, posted_titles):
    feeds = get_feeds_for_category(cat)
    n = len(feeds)
    if n == 0:
        return None, 0
    start = memory.get(f'{cat}_index', 0) % n

    for i in range(n):
        idx = (start + i) % n
        feed = feeds[idx]
        print(f"   📡 [{cat.upper()}] источник #{idx+1}/{n}: {feed}")
        news = fetch_from_feed(feed)

        # 🎯 Адаптивная задержка
        if any(prefix in feed for prefix in ['crossref:', 'pubmed:', 'semanticscholar:', 'europepmc:']):
            time.sleep(2.0)
        elif feed == 'medrxiv':
            time.sleep(1.5)
        else:
            time.sleep(0.5)

        for item in news:
            if item['link'] in posted_links:
                print(f"   ⏭ Пропуск (дубликат ссылки): {item['title'][:50]}")
                continue
            if normalize_title(item['title']) in posted_titles:
                print(f"   ⏭ Пропуск (дубликат заголовка): {item['title'][:50]}")
                continue
            if not is_relevant(item):
                continue
            print(f"   ✅ Найдена новость: {item['title'][:60]}")
            return item, (idx + 1) % n

    print(f"   ❌ В категории {cat.upper()} новостей нет")
    return None, (start + 1) % n

# ========== ПРОМПТ 1: САЙТЫ / НАУКА ==========
def process_site_news(news_item):
    date_info = news_item.get('date_info', {})
    year = date_info.get('year')
    is_future = date_info.get('is_future', False)

    date_hint = ""
    if year and is_future:
        date_hint = f"""
⚠️ ВАЖНО — ДАТА ПУБЛИКАЦИИ:
В тексте указан {year} год, но сейчас {datetime.now().year} год. Это означает, что статья является ПРЕПРИНТОМ или находится "в печати" (еще не опубликована).
- Пиши: "исследование планируется к публикации в {year} году" или "работа находится в стадии препринта"
- НЕ пиши "опубликовано в {year} году" как свершившийся факт
- Используй формулировки: "ожидается публикация", "в печати", "предварительные результаты"
"""

    prompt = f"""Ты — нейтральный научный обозреватель Telegram-канала о косметологии и доказательной медицине.
ИСТОЧНИК: {news_item['source']}
ОРИГИНАЛЬНЫЙ ЗАГОЛОВОК: {news_item['title']}
ТЕКСТ: {news_item['summary']}
{date_hint}
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
                {"role": "system", "content": "Ты нейтральный научный обозреватель. Пиши ТОЛЬКО на русском, БЕЗ иероглифов. Никаких «мы», брендов и призывов. Строго соблюдай пустые строки между заголовком, текстом и хэштегами. Если дата в будущем — указывай что это препринт."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Ошибка Groq (сайт/наука): {e}")
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

# ========== ГЛАВНЫЙ ЦИКЛ ==========
def main():
    print("🚀 Запуск агрегатора (Косметология и Медицина)...\n")

    memory = load_memory()
    posted_links = memory['posted_links']
    posted_titles = memory['posted_titles']

    print(f"🧠 В памяти: {len(posted_links)} ссылок, {len(posted_titles)} заголовков")
    print(f"🔁 Цикл категорий: САЙТ → НАУКА → TG → по кругу")
    print(f"📌 Указатели: сайт=#{memory['site_index']+1}, наука=#{memory['science_index']+1}, тг=#{memory['tg_index']+1}")
    print(f"📂 Следующая категория: {memory['next_category'].upper()}\n")

    start_pos = CATEGORIES.index(memory['next_category'])

    chosen_item = None
    chosen_cat = None

    for step in range(3):
        cat = CATEGORIES[(start_pos + step) % 3]
        print(f"📰 Проверяем категорию: {cat.upper()}")
        item, new_index = find_news_in_category(cat, memory, posted_links, posted_titles)
        memory[f'{cat}_index'] = new_index
        if item:
            chosen_item = item
            chosen_cat = cat
            break
        print()

    if not chosen_item:
        print("❌ Новостей нет ни в одной категории. Пропускаем этот час.")
        memory['next_category'] = CATEGORIES[(start_pos + 1) % 3]
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

    if chosen_cat == 'tg':
        print("→ Промпт: TELEGRAM (рерайт + антиреклама + обезличивание)")
        post_text = process_tg_news(chosen_item)
    else:
        print("→ Промпт: САЙТ/НАУКА (перевод + нейтральный обзор)")
        post_text = process_site_news(chosen_item)

    if not post_text:
        print("⏭ Пропущено (реклама или ошибка Groq).")
        posted_links.append(chosen_item['link'])
        posted_titles.append(normalize_title(chosen_item['title']))
        memory['posted_links'] = posted_links[-1000:]
        memory['posted_titles'] = posted_titles[-1000:]
        memory['next_category'] = chosen_cat
        save_memory(memory)
        return

    post_text = format_post(clean_post_text(post_text))

    print("\n--- ГОТОВЫЙ ПОСТ ---")
    print(post_text)
    print("--------------------\n")

    if post_to_telegram(post_text):
        print("🎉 Успешно опубликовано!")

        posted_links.append(chosen_item['link'])
        posted_titles.append(normalize_title(chosen_item['title']))
        memory['posted_links'] = posted_links[-1000:]
        memory['posted_titles'] = posted_titles[-1000:]

        memory['next_category'] = CATEGORIES[(CATEGORIES.index(chosen_cat) + 1) % 3]

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
