from sqlalchemy import String, Numeric, Date
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date
from app.database import Base


class CurrencyRate(Base):
    __tablename__ = "currency_rates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    currency_code: Mapped[str] = mapped_column(String(3), index=True, nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
