"""
Base of knowledge about current world leaders and administrations.
Used by AI for correct mentioning of positions and context.
Update date: 2026-05-18
"""

# === USA (Trump 2.0) ===
USA_ADMINISTRATION = {
    "president": {
        "name_ru": "Donald Trump",
        "name_en": "Donald Trump",
        "title_ru": "President of the USA",
        "title_en": "President of the United States",
        "since": "2025-01-20",
        "note": "47th president, second non-consecutive term",
    },
    "vice_president": {
        "name_ru": "J.D. Vance",
        "name_en": "J.D. Vance",
        "title_ru": "Vice President of the USA",
        "title_en": "Vice President",
    },
    "secretary_of_state": {
        "name_ru": "Marco Rubio",
        "name_en": "Marco Rubio",
        "title_ru": "Secretary of State of the USA",
        "title_en": "Secretary of State",
    },
    "secretary_defense": {
        "name_ru": "Pete Hegseth",
        "name_en": "Pete Hegseth",
        "title_ru": "Secretary of Defense of the USA",
        "title_en": "Secretary of Defense",
    },
    "treasury_secretary": {
        "name_ru": "Scott Bessent",
        "name_en": "Scott Bessent",
        "title_ru": "Secretary of the Treasury of the USA",
        "title_en": "Secretary of the Treasury",
    },
    "national_security_advisor": {
        "name_ru": "Mike Waltz",
        "name_en": "Mike Waltz",
        "title_ru": "National Security Advisor",
        "title_en": "National Security Advisor",
    },
    "press_secretary": {
        "name_ru": "Karoline Leavitt",
        "name_en": "Karoline Leavitt",
        "title_ru": "White House Press Secretary",
        "title_en": "White House Press Secretary",
    },
    "federal_reserve_chair": {
        "name_ru": "Jerome Powell",
        "name_en": "Jerome Powell",
        "title_ru": "Chair of the Federal Reserve of the USA",
        "title_en": "Federal Reserve Chair",
        "note": "Independent position",
    },
    "trade_representative": {
        "name_ru": "Jamieson Greer",
        "name_en": "Jamieson Greer",
        "title_ru": "U.S. Trade Representative",
        "title_en": "U.S. Trade Representative",
    },
    "homeland_security": {
        "name_ru": "Kristi Noem",
        "name_en": "Kristi Noem",
        "title_ru": "Secretary of Homeland Security of the USA",
        "title_en": "Secretary of Homeland Security",
    },
    "attorney_general": {
        "name_ru": "Pam Bondi",
        "name_en": "Pam Bondi",
        "title_ru": "Attorney General of the USA",
        "title_en": "Attorney General",
    },
    "energy_secretary": {
        "name_ru": "Chris Wright",
        "name_en": "Chris Wright",
        "title_ru": "Secretary of Energy of the USA",
        "title_en": "Secretary of Energy",
    },
    "commerce_secretary": {
        "name_ru": "Howard Lutnick",
        "name_en": "Howard Lutnick",
        "title_ru": "Secretary of Commerce of the USA",
        "title_en": "Secretary of Commerce",
    },
    "cia_director": {
        "name_ru": "John Ratcliffe",
        "name_en": "John Ratcliffe",
        "title_ru": "Director of the CIA",
        "title_en": "CIA Director",
    },
    "epa_administrator": {
        "name_ru": "Lee Zeldin",
        "name_en": "Lee Zeldin",
        "title_ru": "EPA Administrator",
        "title_en": "EPA Administrator",
    },
}

# === Russia ===
RUSSIA_ADMINISTRATION = {
    "president": {
        "name_ru": "Vladimir Putin",
        "name_en": "Vladimir Putin",
        "title_ru": "President of Russia",
        "title_en": "President of Russia",
        "since": "2024-05-07",
        "term": "5th term",
    },
    "prime_minister": {
        "name_ru": "Mikhail Mishustin",
        "name_en": "Mikhail Mishustin",
        "title_ru": "Prime Minister of the Russian Federation",
        "title_en": "Prime Minister",
    },
    "foreign_minister": {
        "name_ru": "Sergey Lavrov",
        "name_en": "Sergey Lavrov",
        "title_ru": "Minister of Foreign Affairs of the Russian Federation",
        "title_en": "Minister of Foreign Affairs",
    },
    "defense_minister": {
        "name_ru": "Andrey Belousov",
        "name_en": "Andrey Belousov",
        "title_ru": "Minister of Defense of the Russian Federation",
        "title_en": "Minister of Defense",
        "note": "Appointed in 2024",
    },
    "central_bank_chair": {
        "name_ru": "Elvira Nabiullina",
        "name_en": "Elvira Nabiullina",
        "title_ru": "Chair of the Central Bank of the Russian Federation",
        "title_en": "Central Bank Chair",
    },
    "security_council_secretary": {
        "name_ru": "Sergey Shoigu",
        "name_en": "Sergey Shoigu",
        "title_ru": "Secretary of the Security Council of the Russian Federation",
        "title_en": "Security Council Secretary",
    },
    "finance_minister": {
        "name_ru": "Anton Siluanov",
        "name_en": "Anton Siluanov",
        "title_ru": "Minister of Finance of the Russian Federation",
        "title_en": "Minister of Finance",
    },
    "economy_minister": {
        "name_ru": "Maxim Reshetnikov",
        "name_en": "Maxim Reshetnikov",
        "title_ru": "Minister of Economic Development of the Russian Federation",
        "title_en": "Minister of Economic Development",
    },
}

# === China ===
CHINA_ADMINISTRATION = {
    "president": {
        "name_ru": "Xi Jinping",
        "name_en": "Xi Jinpin",
        "title_ru": "President of China",
        "title_en": "President of China",
        "since": "2023-03-10",
        "note": "Third term"
    },
    "premier": {
        "name_ru": "Li Chang",
        "name_en": "Li Chang",
        "title_ru": "Premier of the State Council of China",
        "title_en": "Premier of the State Council",
    },
    "foreign_minister": {
        "name_ru": "Wang Yi",
        "name_en": "Wang Yi",
        "title_ru": "Minister of Foreign Affairs of China",
        "title_en": "Minister of Foreign Affairs",
    },
    "central_bank_governor": {
        "name_ru": "Pan Gongsheng",
        "name_en": "Pan Gongsheng",
        "title_ru": "Governor of the Peoples Bank of China",
        "title_en": "Governor of the Peoples Bank of China",
    },
}
# === European Union ===
EU_LEADERS = {
    "commission_president": {
        "name_ru": "Ursula von der Layen",
        "name_en": "Ursula von der Layen",
        "title_ru": "President of the European Commission",
        "title_en": "President of the European Commission",
    },
    "council_president": {
        "name_ru": "Antonio Costa",
        "name_en": "Antonio Costa",
        "title_ru": "President of the European Council",
        "title_en": "President of the European Council",
    },
    "ecb_chair": {
        "name_ru": "Christine Lagarde",
        "name_en": "Christine Lagarde",
        "title_ru": "President of the European Central Bank",
        "title_en": "President of the European Central Bank",
    },
    "high_representative": {
        "name_ru": "Kaja Kalas",
        "name_en": "Kaja Kalas",
        "title_ru": "High Representative for Foreign Affairs and Security Policy of the EU",
        "title_en": "High Representative for Foreign Affairs and Security Policy",
    },
}
# === United Kingdom ===
UK_ADMINISTRATION = {
    "prime_minister": {
        "name_ru": "Keir Starmer",
        "name_en": "Keir Starmer",
        "title_ru": "Prime Minister of the United Kingdom",
        "title_en": "Prime Minister of the United Kingdom",
        "since": "2024-07-05",
        "note": "Leader of the Labour Party"
    },
    "chancellor": {
        "name_ru": "Rachel Reeves",
        "name_en": "Rachel Reeves",
        "title_ru": "Chancellor of the Exchequer",
        "title_en": "Chancellor of the Exchequer",
    },
    "foreign_secretary": {
        "name_ru": "David Lammy",
        "name_en": "David Lammy",
        "title_ru": "Secretary of State for Foreign Affairs, Commonwealth and Development Affairs",
        "title_en": "Secretary of State for Foreign Affairs, Commonwealth and Development Affairs",
    },
    "boe_of_england_governor": {
        "name_ru": "Andrew Bailey",
        "name_en": "Andrew Bailey",
        "title_ru": "Governor of the Bank of England",
        "title_en": "Governor of the Bank of England",
    },
}
# === India ===
INDIA_ADMINISTRATION = {
    "prime_minister": {
        "name_ru": "Narendra Modi",
        "name_en": "Narendra Modi",
        "title_ru": "Prime Minister of India",
        "title_en": "Prime Minister of India",
        "since": "2014-05-26",
        "note": "Third term"
    },
    "foreign_minister": {
        "name_ru": "Subramaniam Jaishankar",
        "name_en": "Subramaniam Jaishankar",
        "title_ru": "Minister of External Affairs of India",
        "title_en": "Minister of External Affairs",
    },
    "finance_minister": {
        "name_ru": "Nirmala Sitharaman",
        "name_en": "Nirmala Sitharaman",
        "title_ru": "Minister of Finance of India",
        "title_en": "Minister of Finance",
    },
    "central_bank_governor": {
        "name_ru": "Shaktikanta Das Gupta",
        "name_en": "Shaktikanta Das Gupta",
        "title_ru": "Governor of the Reserve Bank of India (RBI)",
        "title_en": "Governor of the Reserve Bank of India",
    },
}
# === Ukraine ===
UKRAINE_ADMINISTRATION = {
    "president": {
        "name_ru": "Vlodymyr Zelensky",
        "name_en": "Vlodymyr Zelensky",
        "title_ru": "President of Ukraine",
        "title_en": "President of Ukraine",
        "since": "2019-05-20",
        "note": "Second term"
    },
    "prime_minister": {
        "name_ru": "Denys Shmyhal",
        "name_en": "Denys Shmyhal",
        "title_ru": "Prime Minister of Ukraine",
        "title_en": "Prime Minister of Ukraine",
    },
    "foreign_minister": {
        "name_ru": "Andriy Sybiha",
        "name_en": "Andriy Sybiha",
        "title_ru": "Minister of Foreign Affairs of Ukraine",
        "title_en": "Minister of Foreign Affairs",
    },
    "defense_minister": {
        "name_ru": "Rustem Umerov",
        "name_en": "Rustem Umerov",
        "title_ru": "Minister of Defense of Ukraine",
        "title_en": "Minister of Defense",
    },
    "central_bank_governor": {
        "name_ru": "Andriy Pyshnyi",
        "name_en": "Andriy Pyshnyi",
        "title_ru": "Governor of the National Bank of Ukraine",
        "title_en": "Governor of the National Bank of Ukraine",
    },
}
# === Israel ===
ISRAEL_ADMINISTRATION = {
    "prime_minister": {
        "name_ru": "Benjamin Netanyahu",
        "name_en": "Benjamin Netanyahu",
        "title_ru": "Prime Minister of Israel",
        "title_en": "Prime Minister of Israel",
        "since": "2022-12-29",
        "note": "Sixth term"
    },
    "defense_minister": {
        "name_ru": "Israel Katz",
        "name_en": "Israel Katz",
        "title_ru": "Minister of Defense of Israel",
        "title_en": "Minister of Defense",
    },
    "foreign_minister": {
        "name_ru": "Gadi Eisenkot",
        "name_en": "Gadi Eisenkot",
        "title_ru": "Minister of Foreign Affairs of Israel",
        "title_en": "Minister of Foreign Affairs",
    },
    "finance_minister": {
        "name_ru": "Bezalel Smotrich",
        "name_en": "Bezalel Smotrich",
        "title_ru": "Minister of Finance of Israel",
        "title_en": "Minister of Finance",
    },
    "central_bank_governor": {
        "name_ru": "Amir Yaron",
        "name_en": "Amir Yaron",
        "title_ru": "Governor of the Bank of Israel",
        "title_en": "Governor of the Bank of Israel",
    },
}
# === Japan ===
JAPAN_ADMINISTRATION = {
    "prime_minister": {
        "name_ru": "Shigeru Ishiba",
        "name_en": "Shigeru Ishiba",
        "title_ru": "Prime Minister of Japan",
        "title_en": "Prime Minister of Japan",
        "since": "2024-10-01",
        "note": "Leader of the Liberal Democratic Party"
    },
    "foreign_minister": {
        "name_ru": "Takeshi Iwaya",
        "name_en": "Takeshi Iwaya",
        "title_ru": "Minister of Foreign Affairs of Japan",
        "title_en": "Minister of Foreign Affairs",
    },
    "finance_minister": {
        "name_ru": "Kinenta Kita",
        "name_en": "Kinenta Kita",
        "title_ru": "Minister of Finance of Japan",
        "title_en": "Minister of Finance",
    },
    "bank_of_japan_governor": {
        "name_ru": "Ueda Kazeuo",
        "name_en": "Ueda Kazeuo",
        "title_ru": "Governor of the Bank of Japan",
        "title_en": "Governor of the Bank of Japan",
    },
}
# === Brazil ===
BRASIL_ADMINISTRATION = {
    "president": {
        "name_ru": "Lula da Silva",
        "name_en": "Lula da Silva",
        "title_ru": "President of Brazil",
        "title_en": "President of Brazil",
        "since": "2023-01-01",
        "note": "Second term"
    },
    "foreign_minister": {
        "name_ru": "Mauro Veira",
        "name_en": "Mauro Veira",
        "title_ru": "Minister of Foreign Affairs of Brazil",
        "title_en": "Minister of Foreign Affairs",
    },
    "finance_minister": {
        "name_ru": "Fernando Haddad",
        "name_en": "Fernando Haddad",
        "title_ru": "Minister of Finance of Brazil",
        "title_en": "Minister of Finance",
    },
    "central_bank_governor": {
        "name_ru": "Gabriel Galipolo",
        "name_en": "Gabriel Galipolo",
        "title_ru": "President of the Central Bank of Brazil",
        "title_en": "President of the Central Bank of Brazil",
    },
}
# === Helper functions ===

ALL_LEADERS = {
    "USA": USA_ADMINISTRATION,
    "Russia": RUSSIA_ADMINISTRATION,
    "China": CHINA_ADMINISTRATION,
    "European Union": EU_LEADERS,
    "United Kingdom": UK_ADMINISTRATION,
    "India": INDIA_ADMINISTRATION,
    "Ukraine": UKRAINE_ADMINISTRATION,
    "Israel": ISRAEL_ADMINISTRATION,
    "Japan": JAPAN_ADMINISTRATION,
    "Brazil": BRASIL_ADMINISTRATION,
}

def get_leaders_context() -> str:
    '''
    Generates a compact context string with all leaders for AI prompts.
    '''
    parts = []
    for country, admin in ALL_LEADERS.items():
        parts.append(f"Country: {country}")
        for position, person in admin.items():
            name = person.get("name_ru", person.get("name_en", ""))
            title = person.get("title_ru", person.get("title_en", ""))
            parts.append(f"  - {title}: {name}")
            note = person.get("note")
            if note:
                parts.append(f"    (Note: {note})")
        parts.append("")
    return "\n".join(parts)