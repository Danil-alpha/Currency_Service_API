from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session
from app.services import CurrencyService

router = APIRouter(prefix="/currencies", tags=["Валютный функционал"])
currency_service = CurrencyService()


@router.post("/refresh", summary="Скачать свежие курсы из ЦБ и сохранить в БД")
async def refresh_currency_rates(db: AsyncSession = Depends(get_async_session)):
    try:
        new_records = await currency_service.process_and_save_rates(db)
        if not new_records:
            return {
                "status": "skipped",
                "message": "Курсы на эту дату уже были скачаны ранее. База данных актуальна."
            }
        return {
            "status": "success",
            "message": f"Успешно сохранено новых записей: {len(new_records)}",
            "currencies": [r.currency_code for r in new_records]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chart", summary="Получить готовый PNG-график валюты")
async def get_currency_chart(
        code: str = "USD",
        days: int = 30,
        db: AsyncSession = Depends(get_async_session)
):
    """Генерирует аналитический график курса валюты из PostgreSQL в Docker"""
    chart_buffer = await currency_service.generate_chart(db, code, days)

    if chart_buffer is None:
        raise HTTPException(
            status_code=404,
            detail=f"Нет данных по валюте {code} за последние {days} дней. Пожалуйста, сначала запустите метод /refresh"
        )

    return StreamingResponse(chart_buffer, media_type="image/png")
