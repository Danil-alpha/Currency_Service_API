from fastapi import FastAPI
from app.routes import router as currency_router

app = FastAPI(
    title="Финансовый API Сервис",
    description="Бэкенд для получения курсов валют, кэширования в PostgreSQL и аналитики",
    version="1.0"
)


@app.get("/")
async def health_check():
    return {"status": "working", "message": "Сервер успешно запущен"}


app.include_router(currency_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
