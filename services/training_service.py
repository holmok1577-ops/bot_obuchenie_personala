import re

from database.models import TrainingResult
from database.repository import TrainingResultRepository
from schemas import TrainingAssistantTurn, TrainingResultCreate, TrainingSection, TrainingSessionDraft


class TrainingService:
    PASS_THRESHOLD = 4
    NEGATIVE_FEEDBACK_MARKERS = (
        "не совсем",
        "неверно",
        "неправильно",
        "не так",
        "так делать нельзя",
        "это ошибка",
        "ошиб",
        "нужно иначе",
        "нельзя",
    )

    @staticmethod
    def validate_employee_name(value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if len(cleaned) < 2:
            raise ValueError("Укажите имя сотрудника хотя бы из двух символов.")
        return cleaned

    @staticmethod
    def parse_sections(material: str) -> list[TrainingSection]:
        lines = [line.rstrip() for line in material.splitlines()]
        sections: list[TrainingSection] = []
        current_title: str | None = None
        buffer: list[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if re.match(r"^\d+\.\s+", line):
                if current_title and buffer:
                    sections.append(
                        TrainingSection(
                            title=current_title,
                            material=" ".join(buffer).strip(),
                        )
                    )
                current_title = re.sub(r"^\d+\.\s+", "", line)
                buffer = []
                continue

            if current_title is None:
                continue

            buffer.append(line)

        if current_title and buffer:
            sections.append(
                TrainingSection(
                    title=current_title,
                    material=" ".join(buffer).strip(),
                )
            )

        if not sections:
            sections.append(TrainingSection(title="Основной материал", material=material.strip()))

        return sections

    def start_session(self, total_questions: int, material: str) -> TrainingSessionDraft:
        return TrainingSessionDraft(
            total_questions=total_questions,
            sections=self.parse_sections(material),
        )

    def register_employee_name(self, draft: TrainingSessionDraft, employee_name: str) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        updated.employee_name = self.validate_employee_name(employee_name)
        updated.phase = "learning"
        return updated

    def build_section_intro(self, draft: TrainingSessionDraft) -> str:
        section = draft.current_section()
        return (
            f"Отлично, {draft.employee_name}. Начинаем раздел {draft.current_section_index + 1} "
            f"из {len(draft.sections)}: {section.title}.\n\n"
            f"{section.material}\n\n"
            "Когда будете готовы, напишите что-то вроде «готов», и я запущу мини-тест по этому разделу."
        )

    @staticmethod
    def is_ready_for_quiz(user_text: str) -> bool:
        normalized = " ".join(user_text.lower().split())
        ready_markers = {
            "готов",
            "готова",
            "готово",
            "да",
            "поехали",
            "начинаем",
            "начать",
            "можно тест",
            "перейти к тесту",
            "давай тест",
        }
        return normalized in ready_markers

    def reset_quiz_progress(self, draft: TrainingSessionDraft) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        updated.phase = "testing"
        updated.questions_answered = 0
        updated.correct_answers = 0
        updated.current_question = None
        updated.last_answer_feedback = None
        return updated

    def move_to_waiting_ready(self, draft: TrainingSessionDraft) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        updated.phase = "waiting_ready"
        updated.current_question = None
        updated.last_answer_feedback = None
        return updated

    def apply_ai_turn(
        self,
        current: TrainingSessionDraft,
        ai_turn: TrainingAssistantTurn,
    ) -> TrainingSessionDraft:
        updated = TrainingSessionDraft.model_validate(current.model_dump())
        updated.phase = ai_turn.phase
        answer_is_correct = self.normalize_answer_correctness(ai_turn)

        if ai_turn.latest_answer_evaluated and current.phase == "testing" and current.current_question:
            updated.questions_answered += 1
            if answer_is_correct:
                updated.correct_answers += 1

        if ai_turn.answer_feedback is not None:
            updated.last_answer_feedback = ai_turn.answer_feedback

        updated.current_question = ai_turn.next_question

        if ai_turn.final_summary is not None:
            updated.final_summary = ai_turn.final_summary

        return updated

    def normalize_answer_correctness(self, ai_turn: TrainingAssistantTurn) -> bool:
        if not ai_turn.latest_answer_evaluated:
            return False

        feedback = (ai_turn.answer_feedback or ai_turn.reply).lower()
        if any(marker in feedback for marker in self.NEGATIVE_FEEDBACK_MARKERS):
            return False

        return bool(ai_turn.answer_is_correct)

    def handle_section_result(self, draft: TrainingSessionDraft) -> tuple[TrainingSessionDraft, str, bool]:
        updated = TrainingSessionDraft.model_validate(draft.model_dump())
        passed = updated.correct_answers >= self.PASS_THRESHOLD
        updated.overall_questions_answered += updated.questions_answered
        updated.overall_correct_answers += updated.correct_answers

        if passed:
            if updated.current_section_index + 1 < len(updated.sections):
                updated.current_section_index += 1
                updated.section_attempt = 1
                updated.questions_answered = 0
                updated.correct_answers = 0
                updated.current_question = None
                updated.last_answer_feedback = None
                updated.phase = "waiting_ready"
                section_intro = self.build_section_intro(updated)
                message = (
                    f"Отличный результат: {draft.correct_answers}/{draft.total_questions}. "
                    "Этот раздел засчитан.\n\n"
                    f"{section_intro}"
                )
                return updated, message, False

            updated.phase = "completed"
            updated.final_summary = (
                f"Сотрудник прошёл все {len(updated.sections)} раздела(ов). "
                f"Общий результат: {updated.overall_correct_answers}/{updated.overall_questions_answered} "
                f"({updated.overall_score_percent()}%)."
            )
            message = (
                f"Отличная работа. Вы прошли финальный раздел с результатом "
                f"{draft.correct_answers}/{draft.total_questions} и завершили всё обучение."
            )
            return updated, message, True

        updated.section_attempt += 1
        updated.questions_answered = 0
        updated.correct_answers = 0
        updated.current_question = None
        updated.last_answer_feedback = None
        updated.phase = "waiting_ready"
        section_intro = self.build_section_intro(updated)
        message = (
            f"В этом разделе пока {draft.correct_answers}/{draft.total_questions}, а для перехода дальше нужно "
            f"минимум {self.PASS_THRESHOLD}/{draft.total_questions}.\n\n"
            "Вы стараетесь, это уже хорошо. Давайте спокойно повторим этот раздел ещё раз и затем попробуем тест заново.\n\n"
            f"{section_intro}"
        )
        return updated, message, False

    async def create_result(
        self,
        repository: TrainingResultRepository,
        draft: TrainingSessionDraft,
        topic: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        passed_to_next_section: bool,
        course_completed: bool,
    ) -> TrainingResult:
        section = draft.current_section()
        result_in = TrainingResultCreate(
            employee_name=draft.employee_name or "Неизвестный сотрудник",
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            topic=topic,
            section_index=draft.current_section_index + 1,
            total_sections=len(draft.sections),
            section_title=section.title,
            section_attempt=draft.section_attempt,
            total_questions=draft.total_questions,
            correct_answers=draft.correct_answers,
            score_percent=draft.score_percent(),
            passed_to_next_section=passed_to_next_section,
            course_completed=course_completed,
            final_summary=draft.final_summary,
        )
        return await repository.create(result_in)
