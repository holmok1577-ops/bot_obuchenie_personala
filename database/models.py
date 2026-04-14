from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TrainingResult(Base):
    __tablename__ = "training_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_sections: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    section_title: Mapped[str] = mapped_column(String(255), nullable=False, default="Общий результат")
    section_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_to_next_section: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    course_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    final_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
