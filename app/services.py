import io
import httpx
from datetime import datetime, timedelta

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


class CurrencyService:
    @staticmethod
    def get_cbr_url() -> str:
        return "https://www.cbr-xml-daily.ru/daily_json.js"

    async def fetch_live_rates(self) -> dict:
        headers = {
            "User-Agent": "Open-Source-Currency-Analytics-Bot/1.0"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.get_cbr_url(), headers=headers, timeout=10.0, follow_redirects=True)

                if response.status_code == 200:
                    return response.json()
                raise Exception(f"Ошибка ЦБ: Статус-код {response.status_code}")
            except httpx.RequestError as exc:
                raise Exception(f"Ошибка сети при запросе к ЦБ: {exc}")

    async def process_and_save_rates(self, db_session) -> list:
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
        from sqlalchemy import select
        from app.models import CurrencyRate

        start_date = datetime.now().date() - timedelta(days=days)

        query = (
            select(CurrencyRate)
            .where(CurrencyRate.currency_code == code.upper(), CurrencyRate.date >= start_date)
            .order_by(CurrencyRate.date.asc())
        )
        result = await db_session.execute(query)
        records = result.scalars().all()

        if not records:
            return None

        dates = [r.date for r in records]
        rates = [float(r.rate) for r in records]

        fig, ax = plt.subplots(figsize=(11, 5), dpi=100)

        ax.plot(dates, rates, marker='o', markersize=6, linestyle='-',
                color='#1a73e8', linewidth=2.5, label=f'Курс {code.upper()} к RUB')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days // 6)))
        fig.autofmt_xdate()
        ax.set_title(f"Аналитика динамики курса {code.upper()} за {days} дней", fontsize=14, fontweight='bold', pad=15)
        ax.set_xlabel("Дата операции", fontsize=11, labelpad=10)
        ax.set_ylabel("Стоимость единицы валюты (руб)", fontsize=11, labelpad=10)

        ax.grid(True, linestyle='--', alpha=0.6, color='#cccccc')
        ax.legend(loc="upper left", frameon=True, facecolor='#ffffff', edgecolor='#eeeeee')

        for spine in ['top', 'right']:
            ax.spines[spine].set_visible(False)

        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)

        plt.close(fig)

        return buffer
