from __future__ import annotations

import asyncio
import logging
from collections import Counter
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from asyncpg import Pool
from dotenv import load_dotenv

from app.config import Settings, load_settings
from app.dataset import append_label_line
from app.db import connect_db
from app.infer import Inferencer
from app.review import make_detection_crop
from app.utils import image_size, yolo_line

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
LOGGER = logging.getLogger(__name__)


class ReviewStates(StatesGroup):
    waiting_correct_code = State()


class ShelfBot:
    def __init__(self, settings: Settings, pool: Pool, inferencer: Inferencer) -> None:
        self.settings = settings
        self.pool = pool
        self.inferencer = inferencer
        self.bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher(storage=MemoryStorage())
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.dp.message.register(self.cmd_start, Command('start'))
        self.dp.message.register(self.cmd_help, Command('help'))
        self.dp.message.register(self.cmd_products, Command('products'))
        self.dp.message.register(self.cmd_add_product, Command('add_product'))
        self.dp.message.register(self.cmd_stats, Command('stats'))
        self.dp.message.register(self.cmd_review, Command('review'))
        self.dp.message.register(self.cmd_weak, Command('weak'))
        self.dp.callback_query.register(self.review_yes, F.data.startswith('review_yes:'))
        self.dp.callback_query.register(self.review_other, F.data.startswith('review_other:'))
        self.dp.callback_query.register(self.review_skip, F.data.startswith('review_skip:'))
        self.dp.message.register(self.review_code_input, ReviewStates.waiting_correct_code)
        self.dp.message.register(self.handle_photo, F.photo)

    async def cmd_start(self, message: Message) -> None:
        text = (
            'Привет! Я бот аудита полки/холодильника.\n\n'
            'Как снимать:\n'
            '1) Фото перпендикулярно полке, без сильного наклона.\n'
            '2) Хороший свет, без бликов.\n'
            '3) Полка целиком в кадре.\n\n'
            'Я распознаю SKU, считаю фейсы и отправляю на доразметку сомнительные детекции.\n'
            'Команды: /products, /review, /stats, /help'
        )
        await message.answer(text)

    async def cmd_help(self, message: Message) -> None:
        await message.answer(
            '/products — список SKU\n'
            '/add_product CODE|Название|class_id|our(1/0) — только для админов\n'
            '/review — разбор сомнительных детекций\n'
            '/stats — статистика\n'
            '/weak CODE QTY — weak labels, если модель не установлена'
        )

    async def cmd_products(self, message: Message) -> None:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT code, class_id, name, is_our FROM shelf_ai.products ORDER BY class_id'
            )
        if not rows:
            await message.answer('Справочник товаров пуст.')
            return
        lines = [f"{r['code']} → {r['class_id']} → {r['name']} ({'our' if r['is_our'] else 'competitor'})" for r in rows]
        chunk = 30
        for i in range(0, len(lines), chunk):
            await message.answer('\n'.join(lines[i : i + chunk]))

    async def cmd_add_product(self, message: Message) -> None:
        if message.from_user is None or message.from_user.id not in self.settings.admin_ids:
            await message.answer('Недостаточно прав.')
            return
        payload = (message.text or '').replace('/add_product', '', 1).strip()
        try:
            code, name, class_id_s, our_s = [p.strip() for p in payload.split('|')]
            class_id = int(class_id_s)
            is_our = our_s in {'1', 'true', 'True'}
        except Exception:
            await message.answer('Формат: /add_product CODE|Название|class_id|our(1/0)')
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO shelf_ai.products(code, name, class_id, is_our)
                VALUES($1, $2, $3, $4)
                ON CONFLICT (code)
                DO UPDATE SET name=EXCLUDED.name, class_id=EXCLUDED.class_id, is_our=EXCLUDED.is_our
                """,
                code,
                name,
                class_id,
                is_our,
            )
        await message.answer('Товар добавлен/обновлён.')

    async def cmd_stats(self, message: Message) -> None:
        async with self.pool.acquire() as conn:
            photos = await conn.fetchval('SELECT count(*) FROM shelf_ai.photos')
            det_total = await conn.fetchval('SELECT count(*) FROM shelf_ai.detections')
            rows = await conn.fetch('SELECT status, count(*) as c FROM shelf_ai.detections GROUP BY status')
            auto = await conn.fetchval(
                "SELECT count(*) FROM shelf_ai.detections WHERE status='confirmed' AND true_class_id = predicted_class_id"
            )
        lines = [f'Фото: {photos}', f'Детекций: {det_total}']
        for r in rows:
            lines.append(f"{r['status']}: {r['c']}")
        auto_pct = (auto / det_total * 100) if det_total else 0.0
        lines.append(f'Auto-accept: {auto_pct:.2f}%')
        await message.answer('\n'.join(lines))

    async def cmd_review(self, message: Message, state: FSMContext) -> None:
        await state.clear()
        await self._send_next_pending(message)

    async def cmd_weak(self, message: Message) -> None:
        payload = (message.text or '').replace('/weak', '', 1).strip()
        try:
            code, qty_s = payload.split()
            qty = int(qty_s)
        except Exception:
            await message.answer('Формат: /weak CODE QTY')
            return

        async with self.pool.acquire() as conn:
            product = await conn.fetchrow('SELECT code FROM shelf_ai.products WHERE code=$1', code)
            photo_id = await conn.fetchval('SELECT id FROM shelf_ai.photos ORDER BY id DESC LIMIT 1')
            if not product or photo_id is None:
                await message.answer('Нет товара в products или нет загруженных фото.')
                return
            await conn.execute(
                'INSERT INTO shelf_ai.weak_labels(photo_id, product_code, qty) VALUES($1, $2, $3)',
                photo_id,
                code,
                qty,
            )
        await message.answer('Сохранил weak label.')

    async def handle_photo(self, message: Message) -> None:
        if not message.photo:
            return
        photo = message.photo[-1]
        image_stem = str(uuid4())
        image_path = self.settings.dataset_images / f'{image_stem}.jpg'

        file = await self.bot.get_file(photo.file_id)
        await self.bot.download_file(file.file_path, destination=image_path)

        async with self.pool.acquire() as conn:
            photo_id = await conn.fetchval(
                'INSERT INTO shelf_ai.photos(tg_user_id, file_path) VALUES($1, $2) RETURNING id',
                message.from_user.id if message.from_user else 0,
                str(image_path),
            )

            if not self.inferencer.enabled:
                await message.answer(
                    'Модель не установлена, включён режим сбора разметки. '\
                    'Можно сохранить weak labels через /weak CODE QTY и вернуться к /review после установки модели.'
                )
                return

            detections = self.inferencer.predict(image_path)
            products = {
                r['class_id']: r
                for r in await conn.fetch('SELECT class_id, code, name FROM shelf_ai.products')
            }
            counts: Counter[str] = Counter()
            width, height = image_size(image_path)

            for det in detections:
                prod = products.get(det.class_id)
                predicted_name = prod['name'] if prod else f'class_{det.class_id}'
                det_id = await conn.fetchval(
                    """
                    INSERT INTO shelf_ai.detections(
                        photo_id, x1, y1, x2, y2, predicted_class_id, predicted_name, conf, status
                    ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,'pending') RETURNING id
                    """,
                    photo_id,
                    det.x1,
                    det.y1,
                    det.x2,
                    det.y2,
                    det.class_id,
                    predicted_name,
                    det.confidence,
                )
                counts[predicted_name] += 1
                if det.confidence >= self.settings.conf_auto_accept:
                    line = yolo_line(det.class_id, det.x1, det.y1, det.x2, det.y2, width, height)
                    append_label_line(self.settings.dataset_labels, image_stem, line)
                    await conn.execute(
                        """
                        UPDATE shelf_ai.detections
                        SET status='confirmed', true_class_id=predicted_class_id, true_name=predicted_name
                        WHERE id=$1
                        """,
                        det_id,
                    )

        if counts:
            summary = '\n'.join(f'{k}: {v}' for k, v in counts.items())
            await message.answer(f'Готово. Подсчёт фейсов:\n{summary}')
        else:
            await message.answer('Объекты не обнаружены.')

    async def _send_next_pending(self, message: Message) -> None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT d.id, d.photo_id, d.x1, d.y1, d.x2, d.y2, d.conf, d.predicted_name,
                       d.predicted_class_id, p.file_path
                FROM shelf_ai.detections d
                JOIN shelf_ai.photos p ON p.id=d.photo_id
                WHERE d.status='pending'
                ORDER BY d.conf ASC, d.id ASC
                LIMIT 1
                """
            )
        if not row:
            await message.answer('Pending-детекций нет.')
            return

        crop_path = self.settings.dataset_review / f"{row['id']}.jpg"
        make_detection_crop(
            Path(row['file_path']),
            crop_path,
            row['x1'],
            row['y1'],
            row['x2'],
            row['y2'],
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"✅ Да, это {row['predicted_name']}",
                        callback_data=f"review_yes:{row['id']}",
                    )
                ],
                [InlineKeyboardButton(text='✏️ Другое (ввести код)', callback_data=f"review_other:{row['id']}")],
                [InlineKeyboardButton(text='⏭ Пропустить', callback_data=f"review_skip:{row['id']}")],
            ]
        )
        caption = f"det_id={row['id']} conf={row['conf']:.3f} predicted={row['predicted_name']}"
        await message.answer_photo(FSInputFile(crop_path), caption=caption, reply_markup=kb)

    async def review_yes(self, callback: CallbackQuery) -> None:
        det_id = int(callback.data.split(':')[1])
        await self._finalize_detection(det_id, use_predicted=True)
        await callback.answer('Подтверждено')
        if callback.message:
            await self._send_next_pending(callback.message)

    async def review_other(self, callback: CallbackQuery, state: FSMContext) -> None:
        det_id = int(callback.data.split(':')[1])
        await state.set_state(ReviewStates.waiting_correct_code)
        await state.update_data(det_id=det_id)
        await callback.answer()
        if callback.message:
            await callback.message.answer('Введите CODE товара из /products')

    async def review_skip(self, callback: CallbackQuery) -> None:
        det_id = int(callback.data.split(':')[1])
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE shelf_ai.detections SET status='skipped' WHERE id=$1", det_id)
        await callback.answer('Пропущено')
        if callback.message:
            await self._send_next_pending(callback.message)

    async def review_code_input(self, message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        det_id = int(data['det_id'])
        code = (message.text or '').strip()

        async with self.pool.acquire() as conn:
            prod = await conn.fetchrow('SELECT class_id, name FROM shelf_ai.products WHERE code=$1', code)
            if not prod:
                await message.answer('Код не найден, попробуйте ещё раз.')
                return
            await self._finalize_detection(det_id, class_id=prod['class_id'], true_name=prod['name'], conn=conn)

        await state.clear()
        await message.answer('Сохранено как corrected.')
        await self._send_next_pending(message)

    async def _finalize_detection(
        self,
        det_id: int,
        use_predicted: bool = False,
        class_id: int | None = None,
        true_name: str | None = None,
        conn=None,
    ) -> None:
        own_conn = conn is None
        if own_conn:
            conn = await self.pool.acquire()
        try:
            row = await conn.fetchrow(
                """
                SELECT d.id, d.photo_id, d.x1, d.y1, d.x2, d.y2, d.predicted_class_id, d.predicted_name,
                       p.file_path
                FROM shelf_ai.detections d JOIN shelf_ai.photos p ON p.id=d.photo_id
                WHERE d.id=$1
                """,
                det_id,
            )
            if not row:
                return
            if use_predicted:
                class_id = row['predicted_class_id']
                true_name = row['predicted_name']
                status = 'confirmed'
            else:
                status = 'corrected'

            width, height = image_size(Path(row['file_path']))
            image_stem = Path(row['file_path']).stem
            line = yolo_line(class_id, row['x1'], row['y1'], row['x2'], row['y2'], width, height)
            append_label_line(self.settings.dataset_labels, image_stem, line)
            await conn.execute(
                """
                UPDATE shelf_ai.detections
                SET status=$2, true_class_id=$3, true_name=$4
                WHERE id=$1
                """,
                det_id,
                status,
                class_id,
                true_name,
            )
        finally:
            if own_conn:
                await self.pool.release(conn)

    async def run(self) -> None:
        await self.dp.start_polling(self.bot)


async def main() -> None:
    load_dotenv()
    settings = load_settings()
    pool = await connect_db(settings)
    inferencer = Inferencer(settings.model_path)
    bot = ShelfBot(settings, pool, inferencer)
    await bot.run()


if __name__ == '__main__':
    asyncio.run(main())
