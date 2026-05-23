"""
Тестирование AI-провайдера
"""
import asyncio
import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

from ai_core import analyze_news, get_ai_stats

def test_ai():
    print("=" * 60)
    print("ТЕСТ AI-ПРОВАЙДЕРА")
    print("=" * 60)
    
    # Проверяем статус
    stats = get_ai_stats()
    print(f"\n📊 Доступность:")
    for provider, available in stats['available'].items():
        status = "✅" if available else "❌"
        print(f"  {status} {provider}")
    
    # Тестовая новость
    test_news = {
        'title': 'Bitcoin ETF одобрен SEC',
        'summary': 'Комиссия по ценным бумагам США одобрила заявку на запуск спотового Bitcoin ETF от BlackRock. Это первый одобренный спотовый ETF в истории. Ожидается приток институциональных инвестиций.',
        'score': 9
    }
    
    print(f"\n📝 Тестовая новость: {test_news['title']}")
    print(f"⭐ Важность: {test_news['score']}/10")
    print("-" * 60)
    
    # Запускаем анализ
    try:
        result = analyze_news(
            title=test_news['title'],
            summary=test_news['summary'],
            score=test_news['score']
        )
        
        print(f"\n🤖 РЕЗУЛЬТАТ АНАЛИЗА:\n")
        print(result)
        print("\n" + "=" * 60)
        print("✅ Тест завершен успешно!")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        print("=" * 60)

if __name__ == "__main__":
    test_ai()