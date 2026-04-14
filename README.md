# bot_obuchenie_personala

Telegram-бот для обучения сотрудников по тематическим разделам с мини-тестами после каждого блока, сохранением прогресса в PostgreSQL и поддержкой LLM-диалога.

## Что умеет проект

- спрашивает имя сотрудника и открывает обучение по разделам;
- показывает учебный материал по одному разделу за раз;
- отвечает на уточняющие вопросы по текущему разделу;
- запускает мини-тест только после явного сигнала пользователя;
- после каждого раздела сохраняет результат в PostgreSQL;
- переводит к следующему разделу только при результате `4/5` или выше;
- при слабом результате мягко отправляет на повтор текущего раздела;
- в конце курса показывает общий итог по всем разделам.

## Сценарий работы

1. Пользователь отправляет `/start`.
2. Бот просит имя сотрудника.
3. Бот показывает первый учебный раздел.
4. Пользователь может задавать вопросы по текущему разделу.
5. После сообщения `готов` бот запускает мини-тест на 5 вопросов.
6. Если результат `4/5` или `5/5`, бот открывает следующий раздел.
7. Если результат ниже `4/5`, бот повторно показывает тот же раздел.
8. После каждого раздела бот сохраняет отдельную запись в `training_results`.
9. После последнего раздела бот сохраняет финальный прогресс и завершает курс.

## Стек

- Python 3.11
- aiogram 3
- SQLAlchemy 2 + asyncpg
- PostgreSQL 16
- httpx
- pydantic / pydantic-settings
- Docker Compose
- OpenAI-compatible Chat Completions API

## Структура проекта

```text
bot/
  handlers/        # Telegram-хендлеры и сценарий диалога
  keyboards/       # Клавиатуры
  middlewares/     # Логирование и вспомогательная инфраструктура
config/
  settings.py      # Настройки из .env
database/
  db.py            # Инициализация движка, сессий и схемы БД
  models.py        # SQLAlchemy-модели
  repository.py    # Репозиторий сохранения результатов
schemas/
  training.py      # Pydantic-схемы сессии и результата
services/
  ai_training_prompts.py   # Системный промпт для модели
  ai_training_service.py   # Запросы к LLM
  training_service.py      # Бизнес-логика обучения и переходов
material.txt       # Учебный материал по разделам
main.py            # Точка входа
docker-compose.yml # Запуск бота и PostgreSQL
```

## Переменные окружения

Создайте `.env` на основе `.env.example`.

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/onboarding
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_BASE_URL=https://api.openai.com/v1
TRAINING_TOPIC=Правила работы с клиентами
TRAINING_MATERIAL=Базовые правила работы с клиентами описаны в файле material.txt.
TRAINING_MATERIAL_FILE=./material.txt
QUIZ_QUESTION_COUNT=5
LOG_LEVEL=INFO
```

Если указан `TRAINING_MATERIAL_FILE`, бот берёт материал из файла. Это удобно для быстрой смены темы обучения без правок кода.

## Локальный запуск без Docker

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

Для локального Postgres без Docker нужно заменить `db` в `DATABASE_URL` на `localhost` или другой актуальный хост.

## Запуск через Docker

1. Заполните `.env`.
2. Выполните:

```powershell
docker compose up --build
```

База будет доступна с хоста на порту `55432`.

## Подключение через DBeaver

Параметры подключения:

- Host: `localhost`
- Port: `55432`
- Database: `onboarding`
- Username: `postgres`
- Password: `postgres`

Пример JDBC URL:

```text
jdbc:postgresql://localhost:55432/onboarding
```

## Что хранится в PostgreSQL

Таблица `training_results` хранит прогресс по каждому завершённому разделу:

- `employee_name`
- `telegram_user_id`
- `telegram_chat_id`
- `topic`
- `section_index`
- `total_sections`
- `section_title`
- `section_attempt`
- `total_questions`
- `correct_answers`
- `score_percent`
- `passed_to_next_section`
- `course_completed`
- `final_summary`
- `created_at`

Это позволяет видеть не только финальный итог, но и путь сотрудника по каждому учебному блоку.

## Как изменить тему обучения

1. Обновите `TRAINING_TOPIC` в `.env`.
2. Измените содержимое `material.txt`.
3. При необходимости скорректируйте стиль ответов в `services/ai_training_prompts.py`.
4. Перезапустите проект:

```powershell
docker compose up --build
```

Лучше всего разбивать материал на нумерованные разделы:

```text
1. Название раздела.
Текст раздела...

2. Следующий раздел.
Текст раздела...
```

Тогда бот автоматически построит по ним учебные блоки.

## Пример диалога

```text
Пользователь: /start
Бот: Напишите имя сотрудника, которого нужно обучить.
Пользователь: Стас
Бот: Начинаем раздел 1 из 5...
Пользователь: А если клиент злится?
Бот: Важно не спорить и держать спокойный тон...
Пользователь: готов
Бот: Вопрос 1/5 ...
...
Бот: Отличный результат: 4/5. Этот раздел засчитан.
Бот: Начинаем раздел 2 из 5...
```

## Безопасность

- `.env` уже исключён из git через `.gitignore`.
- Не публикуйте реальные токены Telegram и API-ключи в репозитории.
- Если секреты уже были где-то отправлены или показаны, лучше перевыпустить их.

## Идеи для развития

- добавить отдельную таблицу пользователей и сессий;
- вынести учебные программы в админ-панель;
- добавить статистику по ошибкам по разделам;
- сохранять историю вопросов и ответов;
- сделать web-интерфейс для HR или руководителя.
