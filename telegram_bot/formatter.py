"""
Модуль форматирования постов с AI-анализом.
- HTML-разметка (без Markdown).
- Краткое содержание (summary) выводится, только если есть и >20 символов.
- AI-комментарий должен быть передан в статье под ключом 'ai_comment'.
- Эмодзи определяются по содержанию новости (тема/страна/сфера), а не по источнику.
"""

import html


def _escape_html(text: str) -> str:
    """Экранирует спецсимволы HTML для безопасной вставки в Telegram HTML."""
    if not text:
        return ""
    return html.escape(text)


RU = chr(127479) + chr(127482)
US = chr(127482) + chr(127480)
CN = chr(127464) + chr(127475)
EU = chr(127466) + chr(127482)
UA = chr(127482) + chr(127462)
IL = chr(127470) + chr(127473)
IR = chr(127470) + chr(127479)
IN_ = chr(127470) + chr(127475)
JP = chr(127471) + chr(127477)
DE = chr(127465) + chr(127466)
FR = chr(127467) + chr(127479)
GB = chr(127468) + chr(127463)
TR = chr(127481) + chr(127479)
BR = chr(127463) + chr(127479)
KR = chr(127472) + chr(127479)
SA = chr(127480) + chr(127462)
AE = chr(127462) + chr(127466)
CA = chr(127464) + chr(127462)
AU = chr(127462) + chr(127481)
CH = chr(127464) + chr(127469)


def _detect_topic_emoji(title, summary, source):
    text = (title + " " + summary).lower()
    if any(w in text for w in ["россия", "рф", "москва", "путин", "кремль", "российск"]):
        return RU
    if any(
        w in text
        for w in [
            "сша",
            "америка",
            "байден",
            "трамп",
            "вашингтон",
            "белый дом",
            "congress",
            "senate",
            "federal reserve",
            "fed ",
            "treasury",
            "pentagon",
            "biden",
            "trump",
            "white house",
            "us ",
            "u.s.",
        ]
    ):
        return US
    if any(
        w in text
        for w in [
            "китай",
            "пекин",
            "си цзиньпин",
            "china",
            "beijing",
            "кндр",
            "северная корея",
            "north korea",
            "pyongyang",
            "kim jong",
        ]
    ):
        return CN
    if any(
        w in text
        for w in ["украина", "киев", "зеленский", "украинск", "ukraine", "kyiv", "zelensky"]
    ):
        return UA
    if any(
        w in text
        for w in [
            "евросоюз",
            "европа",
            "европейск",
            "брюссель",
            "ecb",
            "european central bank",
            "european union",
            "eurozone",
            "eu ",
            "e.u.",
        ]
    ):
        return EU
    if any(
        w in text
        for w in [
            "израиль",
            "израильск",
            "иерусалим",
            "нетаньяху",
            "israel",
            "jerusalem",
            "netanyahu",
            "gaza",
            "hamas",
            "idf",
        ]
    ):
        return IL
    if any(w in text for w in ["иран", "тегеран", "иранск", "iran", "tehran"]):
        return IR
    if any(w in text for w in ["индия", "индийск", "нью-дели", "india", "new delhi", "modi"]):
        return IN_
    if any(
        w in text
        for w in ["япония", "токио", "японск", "japan", "tokyo", "nikkei", "bank of japan", "boj"]
    ):
        return JP
    if any(w in text for w in ["герман", "берлин", "germany", "berlin", "bundesbank", "deutsche"]):
        return DE
    if any(w in text for w in ["франц", "париж", "macron", "france", "paris", "ecb"]):
        return FR
    if any(
        w in text
        for w in [
            "британ",
            "лондон",
            "великобритан",
            "england",
            "uk ",
            "u.k.",
            "britain",
            "london",
            "bank of england",
            "boe",
            "sunak",
            "starmer",
        ]
    ):
        return GB
    if any(
        w in text for w in ["турц", "стамбул", "эрдоган", "turkey", "istanbul", "ankara", "erdogan"]
    ):
        return TR
    if any(
        w in text for w in ["бразил", "бразили", "brazil", "brasilia", "rio", "sao paulo", "lula"]
    ):
        return BR
    if any(w in text for w in ["коре", "сеул", "south korea", "seoul", "samsung", "hyundai"]):
        return KR
    if any(
        w in text
        for w in ["саудовск", "саудиты", "саудовская аравия", "saudi", "riyadh", "mbs", "opec"]
    ):
        return SA
    if any(
        w in text for w in ["оаэ", "дубай", "абу-таби", "uae", "dubai", "abu dhabi", "emirates"]
    ):
        return AE
    if any(
        w in text
        for w in ["канада", "канадск", "оттава", "canada", "ottawa", "trudeau", "bank of canada"]
    ):
        return CA
    if any(
        w in text
        for w in [
            "австрал",
            "канберра",
            "australia",
            "canberra",
            "rba",
            "reserve bank of australia",
        ]
    ):
        return AU
    if any(w in text for w in ["швейцар", "берн", "switzerland", "bern", "swiss", "snb"]):
        return CH
    if any(
        w in text
        for w in [
            "война",
            "конфликт",
            "атака",
            "удар",
            "обстрел",
            "ракет",
            "беспилотник",
            "дрон",
            "террор",
            "взрыв",
            "боев",
            "армия",
            "военн",
            "мобилизац",
            "nato",
            "n.a.t.o.",
            "nato ",
            "war",
            "conflict",
            "attack",
            "strike",
            "missile",
            "drone",
            "terror",
            "explosion",
            "military",
            "army",
            "defense",
            "defence",
            "invasion",
            "ceasefire",
            "truce",
        ]
    ):
        return "⚔️"
    if any(
        w in text
        for w in [
            "ставк",
            "инфляц",
            "дефолт",
            "рецесс",
            "кризис",
            "эконом",
            "финанс",
            "бюджет",
            "налог",
            "долг",
            "gdp",
            "ввп",
            "macro",
            "fiscal",
            "monetary",
            "recession",
            "inflation",
            "interest rate",
            "crisis",
            "economy",
            "economic",
            "finance",
            "budget",
            "tax",
            "debt",
            "deficit",
            "surplus",
            "austerity",
            "stimulus",
        ]
    ):
        return "💰"
    if any(
        w in text
        for w in [
            "цб",
            "центробанк",
            "банк россии",
            "банк англии",
            "банк японии",
            "central bank",
            "fed ",
            "federal reserve",
            "ecb",
            "boe",
            "boj",
            "snb",
            "rate hike",
            "rate cut",
            "monetary policy",
            "benchmark rate",
            "key rate",
        ]
    ):
        return "🏦"
    if any(
        w in text
        for w in [
            "биткоин",
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "криптовалют",
            "крипто",
            "блокчейн",
            "blockchain",
            "token",
            "altcoin",
            "defi",
            "nft",
            "mining",
            "crypto",
            "cryptocurrency",
            "binance",
            "coinbase",
            "wallet",
            "stablecoin",
            "satoshi",
            "halving",
            "etf bitcoin",
            "bitcoin etf",
            "spot bitcoin",
        ]
    ):
        return "₿"
    if any(
        w in text
        for w in [
            "нефт",
            "газ",
            "opec",
            "опек",
            "энерг",
            "топлив",
            "бензин",
            "уран",
            "атом",
            "oil",
            "gas",
            "petrol",
            "energy",
            "uranium",
            "nuclear",
            "renewable",
            "solar",
            "wind power",
            "electricity",
            "power grid",
            "lng",
            "shale",
            "exxon",
            "shell",
            "bp ",
            "chevron",
            "aramco",
            "total",
        ]
    ):
        return "🛢️"
    if any(
        w in text
        for w in [
            "золот",
            "серебр",
            "платин",
            "медь",
            "никел",
            "алюмини",
            "сталь",
            "руда",
            "gold",
            "silver",
            "platinum",
            "copper",
            "nickel",
            "aluminum",
            "aluminium",
            "steel",
            "iron ore",
            "commodity",
            "commodities",
            "precious metal",
            "bullion",
        ]
    ):
        return "🏅"
    if any(
        w in text
        for w in [
            "искусственный интеллект",
            "нейросет",
            "машинное обучение",
            "chatgpt",
            "gpt",
            "openai",
            "google",
            "microsoft",
            "apple",
            "meta",
            "nvidia",
            "tesla",
            "amazon",
            "artificial intelligence",
            "ai ",
            "machine learning",
            "deep learning",
            "llm",
            "neural",
            "algorithm",
            "chip",
            "semiconductor",
            "quantum",
            "cyber",
            "hacking",
            "data breach",
            "ransomware",
            "tech",
            "technology",
            "startup",
            "unicorn",
            "ipo",
            "big tech",
            "silicon valley",
            "cloud",
            "saas",
        ]
    ):
        return "🤖"
    if any(
        w in text
        for w in [
            "кибер",
            "хакер",
            "взлом",
            "ddos",
            "фишинг",
            "malware",
            "ransomware",
            "cyber",
            "hacker",
            "hack",
            "breach",
            "leak",
            "zero-day",
            "exploit",
            "phishing",
            "spyware",
            "trojan",
            "virus",
            "firewall",
            "encryption",
        ]
    ):
        return "🔒"
    if any(
        w in text
        for w in [
            "бирж",
            "акци",
            "облигац",
            "форекс",
            "трейдинг",
            "индекс",
            "s&p",
            "nasdaq",
            "dow jones",
            "ftse",
            "dax",
            "moex",
            "rts",
            "stock",
            "bond",
            "equity",
            "share price",
            "dividend",
            "yield",
            "bull market",
            "bear market",
            "rally",
            "sell-off",
            "correction",
            "volatility",
            "vix",
            "margin",
            "leverage",
            "short squeeze",
            "ipo",
            "spac",
            "merger",
            "acquisition",
            "takeover",
        ]
    ):
        return "📈"
    if any(
        w in text
        for w in [
            "недвижим",
            "жильё",
            "ипотек",
            "аренд",
            "строительств",
            "застройщик",
            "real estate",
            "property",
            "housing",
            "mortgage",
            "rent",
            "construction",
            "developer",
            "commercial real estate",
            "cre",
            "home price",
            "building",
        ]
    ):
        return "🏠"
    if any(
        w in text
        for w in [
            "санкц",
            "ограничен",
            "эмбарго",
            "тариф",
            "торговая война",
            "sanction",
            "embargo",
            "tariff",
            "trade war",
            "restriction",
            "ban ",
            "banned",
            "blacklist",
            "export control",
            "import ban",
            "antitrust",
            "monopoly",
        ]
    ):
        return "🚫"
    if any(
        w in text
        for w in [
            "выборы",
            "голосован",
            "избирательн",
            "референдум",
            "парламент",
            "election",
            "vote",
            "voting",
            "ballot",
            "polling",
            "campaign",
            "candidate",
            "parliament",
            "congress",
            "senate",
            "legislation",
            "bill ",
            "law ",
            "regulation",
        ]
    ):
        return "🗳️"
    if any(
        w in text
        for w in [
            "землетрясен",
            "наводнен",
            "ураган",
            "цунами",
            "пожар",
            "извержен",
            "earthquake",
            "flood",
            "hurricane",
            "typhoon",
            "tsunami",
            "wildfire",
            "volcano",
            "eruption",
            "drought",
            "climate",
            "global warming",
            "co2",
            "carbon",
            "greenhouse",
            "extreme weather",
            "natural disaster",
        ]
    ):
        return "🌊"
    if any(
        w in text
        for w in [
            "ковид",
            "пандем",
            "вакцин",
            "вирус",
            "эпидем",
            "медицин",
            "здравоохран",
            "covid",
            "pandemic",
            "vaccine",
            "virus",
            "epidemic",
            "medicine",
            "health",
            "pharma",
            "pharmaceutical",
            "fda",
            "clinical trial",
            "treatment",
            "cure",
            "disease",
            "outbreak",
            "who ",
            "world health",
        ]
    ):
        return "🏥"
    if any(
        w in text
        for w in [
            "космос",
            "ракет",
            "спутник",
            "марс",
            "луна",
            "iss",
            "мкс",
            "space",
            "rocket",
            "satellite",
            "mars",
            "moon",
            "nasa",
            "spacex",
            "launch",
            "orbit",
            "astronaut",
            "cosmonaut",
            "space station",
        ]
    ):
        return "🚀"
    if any(
        w in text
        for w in [
            "авто",
            "машин",
            "транспорт",
            "авиа",
            "самолёт",
            "жд ",
            "поезд",
            "car ",
            "auto ",
            "automotive",
            "vehicle",
            "ev ",
            "electric vehicle",
            "tesla",
            "byd",
            "aviation",
            "airline",
            "aircraft",
            "boeing",
            "airbus",
            "railway",
            "train",
            "shipping",
            "logistics",
            "supply chain",
        ]
    ):
        return "🚗"
    if any(
        w in text
        for w in [
            "сельскохозяйственн",
            "урожай",
            "пшеница",
            "кукуруза",
            "соев",
            "рис",
            "agriculture",
            "farm",
            "farming",
            "crop",
            "wheat",
            "corn",
            "soybean",
            "rice",
            "grain",
            "food security",
            "famine",
            "harvest",
            "drought",
        ]
    ):
        return "🌾"
    source_emoji = {
        "Habr": "💻",
        "VC": "💻",
        "Science": "🔬",
        "Security": "🔒",
        "Interfax": "📰",
        "RT": "📰",
        "RIA": "📰",
        "CoinDesk": "₿",
        "Investing": "📊",
        "CoinTelegraph": "₿",
        "CNBC_World": "📰",
        "NYT_Business": "📰",
        "NYT_Economy": "📰",
        "NYT_Tech": "💻",
        "NYT_DealBook": "🤝",
    }
    return source_emoji.get(source, "📰")


def format_news_post(article):
    title = _escape_html(article.get("title", "").strip())
    summary = article.get("summary", "") or ""
    link = article.get("link", "")
    source = _escape_html(article.get("source", "News"))
    ai_comment = article.get("ai_comment", "").strip()

    summary_block = ""
    if summary:
        summary = " ".join(summary.split())
        if len(summary) > 20:
            if len(summary) > 500:
                summary = summary[:500].rstrip() + "…"
            summary_block = f"📌 {_escape_html(summary)}\n\n"
    emoji = _detect_topic_emoji(title, summary, source)

    # Извлекаем цитату из summary или ai_comment
    quote_block = ""
    try:
        from utils.quote_extractor import format_quote_for_post, get_best_quote

        combined_text = f"{summary} {ai_comment}"
        quote_data = get_best_quote(combined_text)
        if quote_data:
            quote_block = format_quote_for_post(quote_data)
    except Exception:
        pass

    has_lead = __import__("random").random() > 0.3
    lead_phrases = ["", "", "", "Кратко: ", "Главное: ", "Суть: "]
    lead = __import__("random").choice(lead_phrases) if has_lead else ""

    ai_clean = ai_comment.replace("📌 ", "").replace("📚 ", "").replace("✅ ", "")
    ai_clean = ai_clean.replace("**", "").replace("— ", "• ")
    # Убираем HTML-экранирование из AI-комментария перед экранированием
    ai_clean = (
        ai_clean.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    ai_clean = _escape_html(ai_clean)

    closers = [
        "",
        "",
        "",
        "",
        "Что думаете?",
        "Обсуждаем?",
        "Как считаете — это серьёзно?",
        "Похоже на правду?",
    ]
    closer_raw = __import__("random").choice(closers)
    closer = _escape_html(closer_raw) if closer_raw else ""

    message = f"""{emoji} <b>{title}</b>

{summary_block}{lead}{ai_clean}
{quote_block}{closer}

🔗 <a href="{link}">Читать полностью</a>
🏷 #{source} #новости"""
    return message.strip()
