# Shelf Audit Telegram Bot (FotoBot)

Полностью runnable backend+ML проект для аудита полки/холодильника (напитки/пиво):
- Telegram-бот (aiogram v3)
- YOLO инференс (ultralytics)
- активное обучение через `/review`
- сохранение разметки в YOLO-формате
- PostgreSQL в отдельной схеме `shelf_ai.*`
- TLS-подключение к внешней БД с проверкой сертификата (verify-full эквивалент)
- Docker/Compose для Timeweb Cloud

## Важные гарантии
1. Секреты **не хардкодятся** (только `.env`).
2. Внешний PostgreSQL подключается через `ssl.create_default_context(cafile=SSL_ROOT_CERT)` и `asyncpg(..., ssl=ssl_context)`.
3. Таблицы создаются **только** в схеме `shelf_ai`.
4. `class_id` фиксируется навсегда (0..79 и далее только добавление в конец).
5. На сервере без GPU: только инференс + сбор датасета. Обучение вынесено наружу.

## Структура

```text
shelf-bot/
  app/
  scripts/
  dataset/
  models/
  certs/
  Dockerfile
  docker-compose.prod.yml
  docker-compose.dev.yml
  requirements.txt
  .env.example
```

## Команды бота
- `/start` — инструкция по фото
- `/products` — список `code → class_id → name`
- `/add_product CODE|Название|class_id|our(1/0)` — только admin из `ADMIN_IDS`
- `/review` — обзор pending детекций (минимальный `conf` сначала)
- `/stats` — агрегированная статистика
- `/help`
- `/weak CODE QTY` — weak labels (когда модель не установлена)

## Поведение при фото
1. Фото сохраняется в `DATASET_IMAGES` как UUID.jpg.
2. Пишется запись в `shelf_ai.photos`.
3. Если есть модель (`MODEL_PATH`):
   - YOLO predict,
   - каждая детекция пишется в `shelf_ai.detections` (`pending`),
   - если `conf >= CONF_AUTO_ACCEPT`, запись сразу подтверждается и bbox пишется в YOLO label файл.
4. Если модели нет:
   - бот сообщает про режим сбора датасета,
   - можно сохранять weak labels командой `/weak CODE QTY`.

## REVIEW flow
`/review`:
- берётся `pending` с наименьшим `conf`
- делается crop в `dataset/review/<det_id>.jpg`
- кнопки:
  - ✅ подтвердить predicted
  - ✏️ другое: ввести `CODE`
  - ⏭ пропустить

При подтверждении/исправлении bbox добавляется в `dataset/labels/<image>.txt` (YOLO normalized format).

## БД
Схема и таблицы создаются автоматически при старте:
- `shelf_ai.products`
- `shelf_ai.photos`
- `shelf_ai.detections`
- `shelf_ai.weak_labels`

## Деплой на Timeweb Cloud (prod)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# перелогиньтесь
```

```bash
git clone <your_repo_url> FotoBot
cd FotoBot
cp .env.example .env
```

1) Заполните `.env`: `BOT_TOKEN`, `DB_PASSWORD`, `ADMIN_IDS`.

2) Положите корневой сертификат:
```bash
mkdir -p certs
# скопируйте root.crt от провайдера БД
# файл должен быть: ./certs/root.crt
```

3) Запуск:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4) Импорт продуктов:
```bash
docker compose -f docker-compose.prod.yml exec bot python scripts/import_products.py
```

5) Генерация `data.yaml`:
```bash
docker compose -f docker-compose.prod.yml exec bot python scripts/make_data_yaml.py
```

6) Установка весов:
```bash
./scripts/install_weights.sh /path/to/best.pt prod
```

## Локальная разработка (dev)

```bash
cp .env.example .env
# для локального postgres без TLS
sed -i 's/DB_SSL_REQUIRED=1/DB_SSL_REQUIRED=0/' .env

docker compose -f docker-compose.dev.yml up -d --build
```

## Экспорт датасета (для внешнего обучения)

```bash
docker compose -f docker-compose.prod.yml exec bot python scripts/export_dataset.py
# пример: /app/dataset_export_20261010_1530.tar.gz
```

Скачать архив с сервера:
```bash
scp user@server:/path/to/FotoBot/dataset_export_YYYYMMDD_HHMM.tar.gz .
```

## Внешнее обучение (GPU/Colab)
1. Забрать архив.
2. Доразметить/почистить при необходимости.
3. Обучить YOLO на внешней машине.
4. Вернуть `best.pt` на сервер.
5. Обновить через `install_weights.sh`.

## Принятые допущения
- Для первого запуска можно использовать стартовые веса YOLO; без них доступен только weak-label поток.
- Weak labels не заменяют bbox-разметку; для качественной модели нужна bbox-разметка (Label Studio/Roboflow/ручная).
- `/add_product` делает upsert по `code`; ответственность за неизменность class_id лежит на администраторе процесса каталога.

## Этап 2 (план): ценники
Подготовлен каркас `app/price.py`:
- детектор `price_tag`
- OCR цены
- геометрическая привязка ценника к SKU (ценник ниже товара)
- будущая команда `/price`

Реализация OCR в текущем этапе осознанно не включена.
