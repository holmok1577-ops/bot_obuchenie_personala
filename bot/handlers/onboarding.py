import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards import cancel_keyboard, remove_keyboard
from config import Settings
from database import TrainingResultRepository
from schemas import TrainingSessionDraft
from services import AITrainingService, TrainingService

logger = logging.getLogger(__name__)
router = Router()


class TrainingStates(StatesGroup):
    active = State()


def build_assistant_message(ai_turn) -> str:
    reply = ai_turn.reply.strip()
    next_question = (ai_turn.next_question or "").strip()

    if ai_turn.phase != "testing" or not next_question:
        return reply

    if next_question in reply:
        return reply

    if ai_turn.latest_answer_evaluated:
        return f"{reply}\n\nСледующий вопрос: {next_question}"

    return next_question


@router.message(Command("start"))
async def handle_start(message: Message, state: FSMContext, settings: Settings, training_service: TrainingService) -> None:
    await state.clear()
    await state.set_state(TrainingStates.active)
    await state.update_data(
        draft=training_service.start_session(
            total_questions=settings.quiz_question_count,
            material=settings.get_training_material(),
        ).model_dump(),
        result_id=None,
        name_collected=False,
    )
    await message.answer(
        "Здравствуйте! Я помогу быстро и без занудства разобрать тему, а потом проведу короткое тестирование.\n\n"
        "Напишите имя сотрудника, которого нужно обучить.",
        reply_markup=cancel_keyboard(),
    )


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активной сессии обучения.", reply_markup=remove_keyboard())
        return

    await state.clear()
    await message.answer(
        "Остановил сессию. Если захотите начать заново, просто отправьте /start.",
        reply_markup=remove_keyboard(),
    )


@router.message(TrainingStates.active, F.text)
async def process_ai_training(
    message: Message,
    state: FSMContext,
    settings: Settings,
    training_service: TrainingService,
    ai_training_service: AITrainingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    state_data = await state.get_data()
    draft = TrainingSessionDraft.model_validate(state_data.get("draft", {}))
    name_collected = bool(state_data.get("name_collected"))
    user_text = message.text or ""

    try:
        if not name_collected:
            updated_draft = training_service.register_employee_name(draft=draft, employee_name=user_text)
            updated_draft = training_service.move_to_waiting_ready(updated_draft)
            await state.update_data(draft=updated_draft.model_dump())

            await message.answer(
                training_service.build_section_intro(updated_draft),
                reply_markup=cancel_keyboard(),
            )
            await state.update_data(name_collected=True)
            return

        if draft.phase == "waiting_ready":
            if training_service.is_ready_for_quiz(user_text):
                quiz_draft = training_service.reset_quiz_progress(draft)
                ai_turn = await ai_training_service.generate_turn(
                    draft=quiz_draft,
                    user_message="Сотрудник готов к мини-тесту по текущему разделу.",
                    is_new_dialogue=False,
                )
                updated_draft = training_service.apply_ai_turn(quiz_draft, ai_turn)
                await state.update_data(draft=updated_draft.model_dump())
                await message.answer(build_assistant_message(ai_turn), reply_markup=cancel_keyboard())
                return

            learning_draft = TrainingSessionDraft.model_validate(draft.model_dump())
            learning_draft.phase = "learning"
            ai_turn = await ai_training_service.generate_turn(
                draft=learning_draft,
                user_message=user_text,
                is_new_dialogue=False,
            )
            updated_draft = training_service.move_to_waiting_ready(learning_draft)
            await state.update_data(draft=updated_draft.model_dump())
            await message.answer(
                f"{ai_turn.reply}\n\nКогда будете готовы, напишите «готов», и я запущу мини-тест по этому разделу.",
                reply_markup=cancel_keyboard(),
            )
            return

        ai_turn = await ai_training_service.generate_turn(
            draft=draft,
            user_message=user_text,
            is_new_dialogue=False,
        )
        updated_draft = training_service.apply_ai_turn(draft, ai_turn)
        await state.update_data(draft=updated_draft.model_dump())

        if updated_draft.questions_answered >= updated_draft.total_questions:
            section_passed = updated_draft.correct_answers >= training_service.PASS_THRESHOLD

            async with session_factory() as session:
                repository = TrainingResultRepository(session)
                await training_service.create_result(
                    repository=repository,
                    draft=updated_draft,
                    topic=settings.training_topic,
                    telegram_user_id=message.from_user.id if message.from_user else 0,
                    telegram_chat_id=message.chat.id,
                    passed_to_next_section=section_passed,
                    course_completed=section_passed and updated_draft.current_section_index + 1 >= len(updated_draft.sections),
                )

            updated_draft, section_message, should_finish_course = training_service.handle_section_result(updated_draft)
            await state.update_data(draft=updated_draft.model_dump())

            if not should_finish_course:
                await message.answer(section_message, reply_markup=cancel_keyboard())
                return

            await state.clear()
            await message.answer(
                f"{section_message}\n\n"
                f"Результат сохранен в Postgres.\n"
                f"Итог по всему курсу: {updated_draft.overall_correct_answers}/{updated_draft.overall_questions_answered} "
                f"({updated_draft.overall_score_percent()}%).",
                reply_markup=remove_keyboard(),
            )
            return

        await message.answer(build_assistant_message(ai_turn), reply_markup=cancel_keyboard())
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=cancel_keyboard())
    except Exception:
        logger.exception("Failed to process AI training")
        await message.answer(
            "Что-то пошло не так при обработке сообщения. Попробуйте еще раз или отправьте /cancel.",
            reply_markup=cancel_keyboard(),
        )


@router.message(TrainingStates.active)
async def handle_invalid_collecting_input(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте ответ текстом.", reply_markup=cancel_keyboard())


@router.message(F.text)
async def handle_text_without_flow(message: Message) -> None:
    await message.answer("Чтобы начать обучение и тестирование, отправьте /start.")


@router.message()
async def handle_unsupported_input(message: Message) -> None:
    await message.answer("Пожалуйста, используйте текстовые сообщения или команду /start.")
