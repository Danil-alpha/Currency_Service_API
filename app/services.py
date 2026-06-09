import io
import httpx
from datetime import datetime, timedelta

# Настройка Matplotlib для работы на бэкенд-серверах (БЕЗ открытия окон на ПК)
import matplotlib

matplotlib.use('Agg')  # Включаем headless-режим отрисовки в память
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


class CurrencyService:
    @staticmethod
    def get_cbr_url() -> str:
        # Прямой путь до конкретного файла. Никаких редиректов тут быть не может!
        return "https://www.cbr-xml-daily.ru/daily_json.js"

    async def fetch_live_rates(self) -> dict:
        """Асинхронно скачивает свежий JSON курсов валют с сайта ЦБ"""
        headers = {
            "User-Agent": "Open-Source-Currency-Analytics-Bot/1.0"
        }
        async with httpx.AsyncClient() as client:
            try:
                # Обязательно оставляем follow_redirects=True для обхода сетевых шлюзов
                response = await client.get(self.get_cbr_url(), headers=headers, timeout=10.0, follow_redirects=True)

                if response.status_code == 200:
                    return response.json()
                raise Exception(f"Ошибка ЦБ: Статус-код {response.status_code}")
            except httpx.RequestError as exc:
                raise Exception(f"Ошибка сети при запросе к ЦБ: {exc}")

    async def process_and_save_rates(self, db_session) -> list:
        """Скачивает JSON, парсит мультивалютный список и сохраняет в базу Docker"""
        from app.models import CurrencyRate
        from sqlalchemy import select

        raw_data = await self.fetch_live_rates()

        cbr_date_str = raw_data["Date"][:10]
        cbr_date = datetime.strptime(cbr_date_str, "%Y-%m-%d").date()

        # Наша богатая база данных отслеживает топ мировых валют
        target_currencies = ["USD", "EUR", "CNY", "TRY", "AED", "KZT", "BYN", "GBP"]
        saved_records = []

        for code in target_currencies:
            if code in raw_data["Valute"]:
                valute_info = raw_data["Valute"][code]
                # Учитываем номинал (некоторые валюты, например KZT, идут за 100 единиц)
                nominal = float(valute_info["Nominal"])
                current_rate = float(valute_info["Value"]) / nominal

                query = select(CurrencyRate).where(
                    CurrencyRate.currency_code == code,
                    CurrencyRate.date == cbr_date
                )
                result = await db_session.execute(query)
                existing_rate = result.scalar_one_or_none()

                if not existing_rate:
                    new_rate = CurrencyRate(
                        currency_code=code,
                        rate=current_rate,
                        date=cbr_date
                    )
                    db_session.add(new_rate)
                    saved_records.append(new_rate)

        if saved_records:
            await db_session.commit()

        return saved_records

    async def generate_chart(self, db_session, code: str, days: int) -> io.BytesIO:
        """Достает историю из PostgreSQL в Docker и генерирует PNG-график в памяти"""
        from sqlalchemy import select
        from app.models import CurrencyRate

        # 1. Вычисляем дату старта выборки
        start_date = datetime.now().date() - timedelta(days=days)

        # 2. Запрашиваем историю из базы PostgreSQL (сортируем от старых дат к свежим)
        query = (
            select(CurrencyRate)
            .where(CurrencyRate.currency_code == code.upper(), CurrencyRate.date >= start_date)
            .order_by(CurrencyRate.date.asc())
        )
        result = await db_session.execute(query)
        records = result.scalars().all()

        # Если в базе нет записей за этот период — график построить нельзя
        if not records:
            return None

        # 3. Раскладываем объекты БД в чистые списки для осей X и Y
        dates = [r.date for r in records]
        rates = [float(r.rate) for r in records]

        # 4. РИСУЕМ КРАСИВЫЙ ГРАФИК
        # Создаем холст
        fig, ax = plt.subplots(figsize=(11, 5), dpi=100)

        # Строим стильную сглаженную линию с маркерами на точках
        ax.plot(dates, rates, marker='o', markersize=6, linestyle='-',
                color='#1a73e8', linewidth=2.5, label=f'Курс {code.upper()} к RUB')

        # Красиво форматируем даты на оси X
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days // 6)))
        fig.autofmt_xdate()  # Наклоняем даты под угол 45 градусов, чтобы не пересекались

        # Добавляем стили, сетку и подписи
        ax.set_title(f"Аналитика динамики курса {code.upper()} за {days} дней", fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel("Дата операции", fontsize=11, labelpad=10)
        ax.set_ylabel("Стоимость единицы валюты (руб.)", fontsize=11, labelpad=10)

        # Включаем мягкую аккуратную сетку
        ax.grid(True, linestyle='--', alpha=0.6, color='#cccccc')
        ax.legend(loc="upper left", frameon=True, facecolor='#ffffff', edgecolor='#eeeeee')

        # Убираем лишние рамки графика для современного плоского дизайна
        for spine in ['top', 'right']:
            ax.spines[spine].set_visible(False)

        # 5. Сохраняем картинку в буфер памяти
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)

        # Очищаем холст, чтобы не забивать оперативную память сервера
        plt.close(fig)

        return buffer
