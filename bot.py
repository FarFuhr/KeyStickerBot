# encoding: utf-8
import asyncio
import logging
import uuid

from aiogram import Dispatcher, Bot, executor, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ContentType

from config import BOT_TOKEN, QUERY_CACHE_TIME
from database import DatabaseConnection

logging.basicConfig(level=logging.INFO)


db: DatabaseConnection = asyncio.get_event_loop().run_until_complete(DatabaseConnection.create())

storage = RedisStorage2(db=5, prefix='keysticker_fsm')
bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)


class StickerBinding(StatesGroup):
    sticker = State()
    keywords = State()


class StickerKeysInfo(StatesGroup):
    selection = State()


class RemoveSticker(StatesGroup):
    remove_sticker = State()
    confirm_removal = State()
    check_confirm = State()


@dp.message_handler(commands=['start', 'help'], state='*')
async def _(message: types.Message):
    await bot.send_message(
        message.chat.id,
        f'Я помогу вам сохранять и искать стикеры по ключевым словам и фразам. '
        f'с моей помощью стикер, Откройте любой чат и введите "@{(await bot.me).username} <запрос>"\n\n'
        f'Доступные команды:\n'
        f'/add, /bind — привязать стикер к ключевым словам и/или фразам. В случае, если стикер уже был сохранён, '
        f'список ключей можно заменить или дополнить\n'
        f'/remove — удалить стикер\n'
        f'/info — получить список ключей для стикера\n'
        f'/cancel — прекратить текущую операцию'
    )


async def check_and_finish(state: FSMContext) -> bool:
    if state and await state.get_state():
        await state.finish()
        return True
    return False


@dp.message_handler(commands=['remove'], state='*')
async def _(message: types.Message, state: FSMContext = None):
    await check_and_finish(state)
    await RemoveSticker.remove_sticker.set()
    await bot.send_message(message.chat.id, 'Отправьте стикер, который хотите удалить из моей базы')


@dp.message_handler(content_types=ContentType.STICKER, state=RemoveSticker.remove_sticker)
async def _(message: types.Message, state: FSMContext):
    await state.update_data(file_id=message.sticker.file_id)
    await RemoveSticker.next()
    await bot.send_message(
        message.chat.id,
        'Вы уверены?',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton('Да',     callback_data='confirm_removal'),
            types.InlineKeyboardButton('Отмена', callback_data='cancel')
        ]])
    )


@dp.callback_query_handler(lambda q: q.data == 'confirm_removal', state=RemoveSticker.confirm_removal)
async def _(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.finish()
    await query.message.delete_reply_markup()
    if await db.remove_user_sticker(query.message.chat.id, data['file_id']):
        await bot.send_message(query.message.chat.id, 'Успешно удалено')
    else:
        await bot.send_message(query.message.chat.id, 'Произошла неизвестная ошибка. Попробуйте снова')


@dp.message_handler(commands=['info'], state='*')
async def _(message: types.Message, state: FSMContext = None):
    await check_and_finish(state)
    await StickerKeysInfo.next()
    await bot.send_message(message.chat.id, 'Отправьте стикер, чтобы получить список ключевых слов и фраз')


@dp.message_handler(content_types=ContentType.STICKER, state=StickerKeysInfo.selection)
async def _(message: types.Message, state: FSMContext):
    keys = await db.get_keys(message.from_user.id, message.sticker.file_id)
    if keys:
        keys_str = "\n".join(keys)
        await bot.send_message(
            message.chat.id,
            'Для выбранного стикера сохранены следующие ключи:'
        )
        while len(keys_str) > 4096:
            await bot.send_message(message.chat.id, keys_str[:4096])
            keys_str = keys_str[4096:]
        await bot.send_message(message.chat.id, keys_str)
        await state.finish()
        await bot.send_message(message.chat.id, 'Список ключей:')
        await bot.send_message(message.chat.id, '\n'.join(keys))
    else:
        await bot.send_message(message.chat.id, 'Записей не найдено')


@dp.message_handler(commands=['cancel'], state='*')
async def _(message: types.Message, state: FSMContext = None):
    if await check_and_finish(state):
        await bot.send_message(message.chat.id, 'Отменено')
    else:
        await bot.send_message(message.chat.id, 'Нет начатых действий')


@dp.message_handler(commands=['add', 'bind'], state='*')
async def _(message: types.Message, state: FSMContext = None):
    await check_and_finish(state)
    await StickerBinding.sticker.set()
    await bot.send_message(message.chat.id, 'Отправьте мне стикер, к которому хотите привязать ключевые слова')


@dp.message_handler(content_types=ContentType.STICKER, state=StickerBinding.sticker)
async def _(message: types.Message, state: FSMContext):
    await state.update_data(file_id=message.sticker.file_id)
    await StickerBinding.next()
    await bot.send_message(message.chat.id,
                           'Теперь отправьте список ключевых слов или ключевую фразу для этого стикера. '
                           'Все слова и фразы следует поместить на отдельной строке.')


@dp.message_handler(lambda m: m.text, state=StickerBinding.keywords)
async def _(message: types.Message, state: FSMContext):
    await state.update_data(keys=message.text.splitlines())
    data = await state.get_data()
    old_keys = await db.get_keys(message.from_user.id, data['file_id'])
    if old_keys:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('Заменить', callback_data='bind|replace'))
        markup.add(types.InlineKeyboardButton('Объединить', callback_data='bind|join'))
        markup.add(types.InlineKeyboardButton('Отмена', callback_data='cancel'))
        old_keys_str = "\n".join(old_keys)
        await bot.send_message(
            message.chat.id,
            'Для выбранного стикера уже сохранены следующие ключи:\n\n'
        )
        while len(old_keys_str) > 4096:
            await bot.send_message(message.chat.id, old_keys_str[:4096])
            old_keys_str = old_keys_str[:4096]
        await bot.send_message(message.chat.id, old_keys_str)
        await bot.send_message(
            message.chat.id,
            'Объединить оба списка, заменить старый на новый или отменить изменения?',
            reply_markup=markup
        )
    else:
        await db.update_keys(message.chat.id, data['file_id'], data['keys'])
        await state.finish()
        await bot.send_message(message.chat.id, 'Готово!')


@dp.callback_query_handler(lambda q: q.data.lower().startswith('bind'), state=StickerBinding.keywords)
async def _(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    replace = query.data.lower().endswith('replace')
    await db.update_keys(query.message.chat.id, data['file_id'], data['keys'], replace=replace)

    await state.finish()
    await query.message.delete_reply_markup()
    await query.message.edit_text('Ключи успешно перезаписаны' if replace else 'Ключи успешно дополнены')


@dp.callback_query_handler(lambda q: q.data is 'cancel', state='*')
async def _(query: types.CallbackQuery, state: FSMContext = None):
    await check_and_finish(state)
    await query.message.delete_reply_markup()
    await query.answer('Отменено')
    await bot.send_message(query.message.chat.id, 'Отменено')


@dp.message_handler(content_types=ContentType.ANY, state='*')
async def _(message: types.Message, state: FSMContext = None):
    await bot.send_message(message.chat.id, 'Чтобы получить информацию о боте, отправьте /help')


@dp.inline_handler(state='*')
async def inline_message(query: types.InlineQuery, *args, **kwargs):
    offset = int(query.offset or '0')
    stickers = await db.find_stickers_with_key(query.from_user.id, query.query, offset=offset)
    results = [
        types.InlineQueryResultCachedSticker(id=uuid.uuid4().hex, sticker_file_id=sticker)
        for sticker in stickers
    ]
    await bot.answer_inline_query(
        query.id, results=results, is_personal=True,
        next_offset=str(offset + len(results)),
        cache_time=QUERY_CACHE_TIME
    )


if __name__ == '__main__':
    executor.start_polling(dp)
