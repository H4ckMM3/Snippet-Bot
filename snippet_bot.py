import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters, ConversationHandler
import json
import hashlib
import math
from datetime import datetime

import os
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

# Создаем директорию для данных, если её нет
if not os.path.exists('data'):
    os.makedirs('data')


# Настройки
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
GET_NAME, GET_CODE, GET_LANGUAGE, GET_TAGS = range(4)
SNIPPETS_FILE = 'data/shared_snippets.json'
USERS_FILE = 'data/users.json'
ITEMS_PER_PAGE = 10

# Конфигурация языков и достижений
LANGUAGES = {
    'JavaScript': '🟨',
    'PHP': '🐘',
    'CSS': '🎨',
    'HTML': '🌐'
}

CATEGORIES = ['WordPress', 'Bitrix', 'Общее']

USER_LEVELS = {
    0: {'name': 'Junior', 'emoji': '🌱', 'min_snippets': 0, 'min_uses': 0},
    1: {'name': 'Junior+', 'emoji': '🌿', 'min_snippets': 3, 'min_uses': 20},
    2: {'name': 'Middle', 'emoji': '🌳', 'min_snippets': 10, 'min_uses': 100},
    3: {'name': 'Middle+', 'emoji': '🌲', 'min_snippets': 25, 'min_uses': 300},
    4: {'name': 'Senior', 'emoji': '🦅', 'min_snippets': 50, 'min_uses': 1000}
}

ACHIEVEMENTS = {
    'first_snippet': {'name': 'Первый сниппет', 'emoji': '🎉', 'description': 'Добавил первый сниппет'},
    'popular_author': {'name': 'Популярный автор', 'emoji': '⭐', 'description': '100+ использований сниппетов'},
    'code_master': {'name': 'Мастер кода', 'emoji': '🏆', 'description': '500+ использований сниппетов'},
    'multilang': {'name': 'Полиглот', 'emoji': '🌍', 'description': 'Сниппеты на всех языках'},
    'helpful': {'name': 'Помощник', 'emoji': '🤝', 'description': '10+ сниппетов в избранном у других'},
    'active': {'name': 'Активист', 'emoji': '🔥', 'description': '25+ сниппетов'}
}

class UserManager:
    def __init__(self):
        self.users = {}
        self.load_users()

    def load_users(self):
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                self.users = json.load(f)

    def save_users(self):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, indent=4, ensure_ascii=False)

    def get_user(self, user_id):
        user_id = str(user_id)
        if user_id not in self.users:
            self.users[user_id] = {
                'favorites': [],
                'achievements': [],
                'level': 0,
                'total_snippets': 0,
                'total_uses': 0,
                'join_date': datetime.now().isoformat()
            }
            self.save_users()
        return self.users[user_id]

    def update_user_stats(self, user_id, snippets_count, uses_count):
        user = self.get_user(user_id)
        user['total_snippets'] = snippets_count
        user['total_uses'] = uses_count
        
        # Обновляем уровень
        old_level = user['level']
        for level, data in USER_LEVELS.items():
            if snippets_count >= data['min_snippets'] and uses_count >= data['min_uses']:
                user['level'] = level
        
        # Проверяем достижения
        new_achievements = []
        
        if snippets_count >= 1 and 'first_snippet' not in user['achievements']:
            user['achievements'].append('first_snippet')
            new_achievements.append('first_snippet')
            
        if uses_count >= 100 and 'popular_author' not in user['achievements']:
            user['achievements'].append('popular_author')
            new_achievements.append('popular_author')
            
        if uses_count >= 500 and 'code_master' not in user['achievements']:
            user['achievements'].append('code_master')
            new_achievements.append('code_master')
            
        if snippets_count >= 25 and 'active' not in user['achievements']:
            user['achievements'].append('active')
            new_achievements.append('active')

        # Проверяем достижение "Полиглот"
        if snippets_count > 0 and 'multilang' not in user['achievements']:
            user_snippets = [data for data in storage.snippets.values() 
                           if data['author'] == user.get('username', 'Unknown')]
            languages_used = set(snippet['language'] for snippet in user_snippets)
            if len(languages_used) >= len(LANGUAGES):
                user['achievements'].append('multilang')
                new_achievements.append('multilang')
        
        # Проверяем достижение "Помощник"
        if 'helpful' not in user['achievements']:
            user_snippet_names = [name for name, data in storage.snippets.items() 
                                 if data['author'] == user.get('username', 'Unknown')]
            total_favorites = sum(1 for other_user in self.users.values() 
                                for fav in other_user['favorites'] 
                                if fav in user_snippet_names)
            if total_favorites >= 10:
                user['achievements'].append('helpful')
                new_achievements.append('helpful')
        
        self.save_users()
        return old_level != user['level'], new_achievements

    def add_to_favorites(self, user_id, snippet_name):
        user = self.get_user(user_id)
        if snippet_name not in user['favorites']:
            user['favorites'].append(snippet_name)
            self.save_users()
            return True
        return False

    def remove_from_favorites(self, user_id, snippet_name):
        user = self.get_user(user_id)
        if snippet_name in user['favorites']:
            user['favorites'].remove(snippet_name)
            self.save_users()
            return True
        return False

    def is_favorite(self, user_id, snippet_name):
        user = self.get_user(user_id)
        return snippet_name in user['favorites']

class SharedSnippetStorage:
    def __init__(self):
        self.snippets = {}
        self.load_snippets()

    def load_snippets(self):
        if os.path.exists(SNIPPETS_FILE):
            with open(SNIPPETS_FILE, 'r', encoding='utf-8') as f:
                self.snippets = json.load(f)

    def save_snippets(self):
        with open(SNIPPETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.snippets, f, indent=4, ensure_ascii=False)

    def add_snippet(self, name, code, language, author, tags=None):
        if name not in self.snippets:
            self.snippets[name] = {
                'code': code,
                'language': language,
                'author': author,
                'uses': 0,
                'tags': tags or [],
                'created_date': datetime.now().isoformat()
            }
            self.save_snippets()
            return True
        return False

    def get_snippet(self, name):
        if name in self.snippets:
            self.snippets[name]['uses'] += 1
            self.save_snippets()
            return self.snippets[name]
        return None

    def delete_snippet(self, name):
        if name in self.snippets:
            del self.snippets[name]
            self.save_snippets()
            return True
        return False

    def search_snippets(self, query):
        return {name: data for name, data in self.snippets.items() if query.lower() in name.lower()}

    def filter_by_language(self, language):
        return {name: data for name, data in self.snippets.items() if data['language'] == language}

    def filter_by_tag(self, tag):
        return {name: data for name, data in self.snippets.items() if tag in data.get('tags', [])}

    def get_user_snippets_stats(self, author):
        user_snippets = [data for data in self.snippets.values() if data['author'] == author]
        total_snippets = len(user_snippets)
        total_uses = sum(snippet['uses'] for snippet in user_snippets)
        return total_snippets, total_uses

storage = SharedSnippetStorage()
user_manager = UserManager()

def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📥 Добавить"), KeyboardButton("🔍 Поиск"), KeyboardButton("📋 Все")],
        [KeyboardButton("🗑️ Удалить"), KeyboardButton("⭐ Избранное"), KeyboardButton("🎯 Фильтры")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("📊 Статистика"), KeyboardButton("ℹ️ Помощь")]
    ], resize_keyboard=True)

def get_filter_keyboard():
    keyboard = []
    
    # Языки
    lang_row = []
    for lang, emoji in LANGUAGES.items():
        lang_row.append(KeyboardButton(f"{emoji} {lang}"))
    keyboard.append(lang_row[:2])  # Первые 2 языка
    keyboard.append(lang_row[2:])  # Остальные языки
    
    # Теги
    tag_row = []
    for tag in CATEGORIES:
        tag_row.append(KeyboardButton(f"🏷️ {tag}"))
    keyboard.append(tag_row)
    
    keyboard.append([KeyboardButton("↩️ Главное меню")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_quick_actions_keyboard(snippet_name, user_id, is_author=False):
    keyboard = []
    
    # Первая строка - основные действия
    row1 = [InlineKeyboardButton("📋 Копировать", callback_data=f"copy_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}")]
    
    # Избранное
    if user_manager.is_favorite(user_id, snippet_name):
        row1.append(InlineKeyboardButton("💔 Из избранного", callback_data=f"unfav_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
    else:
        row1.append(InlineKeyboardButton("❤️ В избранное", callback_data=f"fav_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
    
    keyboard.append(row1)
    
    # Вторая строка - навигация и действия автора
    row2 = []
    if is_author:
        row2.append(InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
        row2.append(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
    
    row2.append(InlineKeyboardButton("🔙 Назад", callback_data="back_to_list"))
    keyboard.append(row2)
    
    return InlineKeyboardMarkup(keyboard)

def create_snippets_keyboard(snippets_dict, page=0, callback_prefix="show", extra_data="", show_language=True):
    """Создает клавиатуру со сниппетами с пагинацией"""
    snippet_names = list(snippets_dict.keys())
    total_pages = math.ceil(len(snippet_names) / ITEMS_PER_PAGE)
    
    if page >= total_pages:
        page = 0
    elif page < 0:
        page = total_pages - 1 if total_pages > 0 else 0
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_snippets = snippet_names[start_idx:end_idx]
    
    keyboard = []
    
    # Добавляем кнопки со сниппетами
    for name in page_snippets:
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        data = snippets_dict[name]
        language_emoji = LANGUAGES.get(data['language'], '📄')
        
        if show_language:
            btn_text = f"{language_emoji} {name}"
            if data.get('tags'):
                btn_text += f" 🏷️{'/'.join(data['tags'])}"
            btn_text += f" (👍 {data['uses']})"
        else:
            btn_text = f"{name} (👍 {data['uses']})"
        
        callback_data = f"{callback_prefix}_{snippet_id}{extra_data}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    # Добавляем навигационные кнопки
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Пред", callback_data=f"page_{callback_prefix}_{page-1}{extra_data}"))
        
        nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("След ➡️", callback_data=f"page_{callback_prefix}_{page+1}{extra_data}"))
        
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard), total_pages

async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = user_manager.get_user(user.id)
    level_info = USER_LEVELS[user_data['level']]
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n"
        f"🎖️ Ваш уровень: {level_info['emoji']} {level_info['name']}\n\n"
        f"Я бот для общей библиотеки кода с поддержкой тегов и достижений!\n"
        f"Поддерживаемые языки: {' '.join([f'{emoji} {lang}' for lang, emoji in LANGUAGES.items()])}",
        reply_markup=get_main_keyboard()
    )

async def show_profile(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = user_manager.get_user(user.id)
    level_info = USER_LEVELS[user_data['level']]
    
    # Получаем статистику пользователя
    snippets_count, uses_count = storage.get_user_snippets_stats(user.username or user.full_name)
    
    # Обновляем статистику и проверяем достижения
    level_up, new_achievements = user_manager.update_user_stats(user.id, snippets_count, uses_count)
    
    profile_text = (
        f"👤 Профиль пользователя {user.first_name}\n\n"
        f"🎖️ Уровень: {level_info['emoji']} {level_info['name']}\n"
        f"📝 Сниппетов создано: {snippets_count}\n"
        f"👍 Общие использования: {uses_count}\n"
        f"⭐ В избранном: {len(user_data['favorites'])}\n\n"
    )
    
    # Показываем достижения
    if user_data['achievements']:
        profile_text += "🏆 Достижения:\n"
        for achievement in user_data['achievements']:
            ach_info = ACHIEVEMENTS[achievement]
            profile_text += f"{ach_info['emoji']} {ach_info['name']}: {ach_info['description']}\n"
    else:
        profile_text += "🏆 Достижений пока нет\n"
    
    # Показываем прогресс до следующего уровня
    if user_data['level'] < 4:  # Если не максимальный уровень
        next_level = USER_LEVELS[user_data['level'] + 1]
        profile_text += f"\n📈 До уровня {next_level['emoji']} {next_level['name']}:\n"
        profile_text += f"   Сниппетов: {snippets_count}/{next_level['min_snippets']}\n"
        profile_text += f"   Использований: {uses_count}/{next_level['min_uses']}\n"
    
    await update.message.reply_text(profile_text, reply_markup=get_main_keyboard())
    
    # Уведомления о новых достижениях
    if new_achievements:
        for achievement in new_achievements:
            ach_info = ACHIEVEMENTS[achievement]
            await update.message.reply_text(
                f"🎉 Новое достижение!\n{ach_info['emoji']} {ach_info['name']}\n{ach_info['description']}"
            )
    
    if level_up:
        await update.message.reply_text(
            f"🎊 Поздравляем! Вы достигли уровня {level_info['emoji']} {level_info['name']}!"
        )

async def show_filters(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🎯 Выберите фильтр для поиска сниппетов:",
        reply_markup=get_filter_keyboard()
    )

async def show_favorites(update: Update, context: CallbackContext, page=0):
    user_data = user_manager.get_user(update.effective_user.id)
    favorites = user_data['favorites']
    
    if not favorites:
        await update.message.reply_text(
            "⭐ У вас пока нет избранных сниппетов.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Фильтруем существующие сниппеты
    favorite_snippets = {name: storage.snippets[name] for name in favorites if name in storage.snippets}
    
    if not favorite_snippets:
        await update.message.reply_text(
            "⭐ Ваши избранные сниппеты были удалены.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Сохраняем данные о сниппетах в контексте пользователя
    for name in favorite_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data[f'snippet_{snippet_id}'] = name

    keyboard, total_pages = create_snippets_keyboard(favorite_snippets, page, "show", "_fav")
    
    text = f"⭐ Избранные сниппеты (стр. {page+1} из {total_pages}):"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)

async def show_statistics(update: Update, context: CallbackContext):
    total_snippets = len(storage.snippets)
    total_uses = sum(snippet['uses'] for snippet in storage.snippets.values())
    
    # Статистика по языкам
    lang_stats = {}
    for snippet in storage.snippets.values():
        lang = snippet['language']
        if lang not in lang_stats:
            lang_stats[lang] = {'count': 0, 'uses': 0}
        lang_stats[lang]['count'] += 1
        lang_stats[lang]['uses'] += snippet['uses']
    
    # Статистика по тегам
    tag_stats = {}
    for snippet in storage.snippets.values():
        for tag in snippet.get('tags', []):
            if tag not in tag_stats:
                tag_stats[tag] = 0
            tag_stats[tag] += 1
    
    # Топ-3 авторов
    author_stats = {}
    for snippet in storage.snippets.values():
        author = snippet['author']
        if author not in author_stats:
            author_stats[author] = {'snippets': 0, 'uses': 0}
        author_stats[author]['snippets'] += 1
        author_stats[author]['uses'] += snippet['uses']
    
    top_authors = sorted(author_stats.items(), key=lambda x: x[1]['uses'], reverse=True)[:3]
    
    stats_text = (
        f"📊 Статистика бота\n\n"
        f"📝 Всего сниппетов: {total_snippets}\n"
        f"👍 Общие использования: {total_uses}\n"
        f"👥 Активных пользователей: {len(user_manager.users)}\n\n"
    )
    
    if lang_stats:
        stats_text += "📈 По языкам:\n"
        for lang, stats in lang_stats.items():
            emoji = LANGUAGES.get(lang, '📄')
            stats_text += f"{emoji} {lang}: {stats['count']} шт. ({stats['uses']} исп.)\n"
        stats_text += "\n"
    
    if tag_stats:
        stats_text += "🏷️ По тегам:\n"
        for tag, count in tag_stats.items():
            stats_text += f"• {tag}: {count} шт.\n"
        stats_text += "\n"
    
    if top_authors:
        stats_text += "🏆 Топ авторов:\n"
        for i, (author, stats) in enumerate(top_authors, 1):
            medals = ['🥇', '🥈', '🥉']
            medal = medals[i-1] if i <= 3 else '🏅'
            stats_text += f"{medal} {author}: {stats['snippets']} сниппетов ({stats['uses']} исп.)\n"
    
    await update.message.reply_text(stats_text, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: CallbackContext):
    help_text = (
        "ℹ️ Помощь по боту:\n\n"
        "📥 Добавить - добавить новый сниппет\n"
        "🔍 Поиск - найти код по названию\n"
        "📋 Все - просмотреть всю библиотеку\n"
        "🗑️ Удалить - удалить свой сниппет\n"
        "⭐ Избранное - ваша личная коллекция\n"
        "🎯 Фильтры - поиск по языкам и тегам\n"
        "👤 Профиль - ваша статистика и достижения\n"
        "📊 Статистика - общая статистика бота\n\n"
        f"Поддерживаемые языки: {' '.join([f'{emoji} {lang}' for lang, emoji in LANGUAGES.items()])}\n"
        f"Доступные теги: {', '.join(CATEGORIES)}\n\n"
        "🏆 Система уровней:\n"
    )
    
    for level, info in USER_LEVELS.items():
        help_text += f"{info['emoji']} {info['name']} - {info['min_snippets']}+ сниппетов, {info['min_uses']}+ использований\n"
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Действие отменено", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def add_snippet_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "📝 Введите название для нового сниппета:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Отмена")]], resize_keyboard=True)
    )
    return GET_NAME

async def get_snippet_name(update: Update, context: CallbackContext) -> int:
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    
    context.user_data['snippet_name'] = update.message.text
    
    # Создаем клавиатуру с языками и их эмодзи
    lang_buttons = []
    for lang, emoji in LANGUAGES.items():
        lang_buttons.append(KeyboardButton(f"{emoji} {lang}"))
    
    keyboard = [lang_buttons[:2], lang_buttons[2:], [KeyboardButton("↩️ Отмена")]]
    
    await update.message.reply_text(
        "🔤 Выберите язык программирования:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return GET_LANGUAGE

async def get_snippet_language(update: Update, context: CallbackContext) -> int:
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    
    # Извлекаем язык из текста с эмодзи
    selected_language = None
    for lang, emoji in LANGUAGES.items():
        if update.message.text == f"{emoji} {lang}":
            selected_language = lang
            break
    
    if not selected_language:
        # Создаем клавиатуру с языками и их эмодзи
        lang_buttons = []
        for lang, emoji in LANGUAGES.items():
            lang_buttons.append(KeyboardButton(f"{emoji} {lang}"))
        
        keyboard = [lang_buttons[:2], lang_buttons[2:], [KeyboardButton("↩️ Отмена")]]
        
        await update.message.reply_text(
            "❌ Пожалуйста, выберите один из поддерживаемых языков:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return GET_LANGUAGE
    
    context.user_data['language'] = selected_language
    
    # Клавиатура для выбора тегов
    tag_buttons = []
    for tag in CATEGORIES:
        tag_buttons.append(KeyboardButton(f"🏷️ {tag}"))
    
    keyboard = [
        tag_buttons,
        [KeyboardButton("⏭️ Пропустить теги")],
        [KeyboardButton("↩️ Отмена")]
    ]
    
    await update.message.reply_text(
        "🏷️ Выберите категорию/тег (или пропустите):",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return GET_TAGS

async def get_snippet_tags(update: Update, context: CallbackContext) -> int:
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    
    if update.message.text == "⏭️ Пропустить теги":
        context.user_data['tags'] = []
    else:
        # Извлекаем тег из текста с эмодзи
        selected_tag = None
        for tag in CATEGORIES:
            if update.message.text == f"🏷️ {tag}":
                selected_tag = tag
                break
        
        if selected_tag:
            context.user_data['tags'] = [selected_tag]
        else:
            context.user_data['tags'] = []
    
    await update.message.reply_text(
        f"💾 Введите код для сниппета '{context.user_data['snippet_name']}':\n"
        "(Можно отправить несколько сообщений, завершите командой /done)",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Отмена")]], resize_keyboard=True)
    )
    return GET_CODE

async def get_snippet_code(update: Update, context: CallbackContext) -> int:
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    
    if 'code' not in context.user_data:
        context.user_data['code'] = update.message.text
    else:
        context.user_data['code'] += "\n" + update.message.text
    
    return GET_CODE

async def done_adding_code(update: Update, context: CallbackContext) -> int:
    snippet_name = context.user_data['snippet_name']
    code = context.user_data['code']
    language = context.user_data['language']
    tags = context.user_data.get('tags', [])
    author = update.effective_user.username or update.effective_user.full_name

    if storage.add_snippet(snippet_name, code, language, author, tags):
        # Обновляем статистику пользователя
        snippets_count, uses_count = storage.get_user_snippets_stats(author)
        level_up, new_achievements = user_manager.update_user_stats(update.effective_user.id, snippets_count, uses_count)
        
        tag_text = f" с тегами {', '.join(tags)}" if tags else ""
        language_emoji = LANGUAGES.get(language, '📄')
        
        await update.message.reply_text(
            f"✅ Сниппет '{snippet_name}' добавлен!\n"
            f"{language_emoji} Язык: {language}\n"
            f"🏷️ Теги: {', '.join(tags) if tags else 'Без тегов'}\n"
            f"👤 Автор: {author}",
            reply_markup=get_main_keyboard()
        )
        
        # Уведомления о новых достижениях
        if new_achievements:
            for achievement in new_achievements:
                ach_info = ACHIEVEMENTS[achievement]
                await update.message.reply_text(
                    f"🎉 Новое достижение!\n{ach_info['emoji']} {ach_info['name']}\n{ach_info['description']}"
                )
        
        if level_up:
            user_data = user_manager.get_user(update.effective_user.id)
            level_info = USER_LEVELS[user_data['level']]
            await update.message.reply_text(
                f"🎊 Поздравляем! Вы достигли уровня {level_info['emoji']} {level_info['name']}!"
            )
    else:
        await update.message.reply_text(
            f"❌ Сниппет с названием '{snippet_name}' уже существует!",
            reply_markup=get_main_keyboard()
        )
    
    # Очищаем временные данные
    context.user_data.clear()
    return ConversationHandler.END

async def search_snippets(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        await update.message.reply_text(
            "🔍 Введите поисковый запрос после команды:\n/search название_сниппета",
            reply_markup=get_main_keyboard()
        )
        return

    query = ' '.join(context.args)
    results = storage.search_snippets(query)
    
    if not results:
        await update.message.reply_text(
            f"❌ Сниппеты с запросом '{query}' не найдены.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Сохраняем результаты поиска в контексте пользователя
    for name in results.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data[f'snippet_{snippet_id}'] = name

    keyboard, total_pages = create_snippets_keyboard(results, 0, "show", "_search")
    
    await update.message.reply_text(
        f"🔍 Найдено {len(results)} сниппетов по запросу '{query}':",
        reply_markup=keyboard
    )

async def show_all_snippets(update: Update, context: CallbackContext, page=0):
    if not storage.snippets:
        await update.message.reply_text(
            "📋 Библиотека пуста. Добавьте первый сниппет!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Сохраняем все сниппеты в контексте пользователя
    for name in storage.snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data[f'snippet_{snippet_id}'] = name
    
    # Сохраняем контекст для навигации
    context.user_data['current_list'] = 'all'
    context.user_data['current_snippets'] = storage.snippets
    context.user_data['current_page'] = page

    keyboard, total_pages = create_snippets_keyboard(storage.snippets, page, "show")
    
    text = f"📋 Все сниппеты (стр. {page+1} из {total_pages}):"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)

async def show_snippet(update: Update, context: CallbackContext, snippet_id, source=""):
    # Получаем имя сниппета по ID
    snippet_name = context.user_data.get(f'snippet_{snippet_id}')
    if not snippet_name:
        await update.callback_query.answer("❌ Сниппет не найден")
        return
    
    snippet = storage.get_snippet(snippet_name)
    if not snippet:
        await update.callback_query.answer("❌ Сниппет не найден")
        return
    
    # Сохраняем контекст для возврата
    context.user_data['current_source'] = source
    context.user_data['current_page'] = context.user_data.get('current_page', 0)
    
    language_emoji = LANGUAGES.get(snippet['language'], '📄')
    is_author = snippet['author'] == (update.effective_user.username or update.effective_user.full_name)
    is_favorite = user_manager.is_favorite(update.effective_user.id, snippet_name)
    
    # Формируем текст сниппета
    snippet_text = (
        f"{language_emoji} **{snippet_name}**\n"
        f"👤 Автор: {snippet['author']}\n"
        f"📅 Создан: {snippet.get('created_date', 'Неизвестно')[:10]}\n"
        f"👍 Использований: {snippet['uses']}\n"
    )
    
    if snippet.get('tags'):
        snippet_text += f"🏷️ Теги: {', '.join(snippet['tags'])}\n"
    
    snippet_text += f"\n```{snippet['language'].lower()}\n{snippet['code']}\n```"
    
    # Создаем клавиатуру с быстрыми действиями
    keyboard = get_quick_actions_keyboard(snippet_name, update.effective_user.id, is_author)
    
    await update.callback_query.edit_message_text(
        snippet_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def delete_snippet_start(update: Update, context: CallbackContext):
    author = update.effective_user.username or update.effective_user.full_name
    user_snippets = {name: data for name, data in storage.snippets.items() if data['author'] == author}
    
    if not user_snippets:
        await update.message.reply_text(
            "❌ У вас нет сниппетов для удаления.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Сохраняем сниппеты пользователя в контексте
    for name in user_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data[f'snippet_{snippet_id}'] = name

    keyboard, total_pages = create_snippets_keyboard(user_snippets, 0, "delete")
    
    await update.message.reply_text(
        f"🗑️ Выберите сниппет для удаления (всего: {len(user_snippets)}):",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text == "📥 Добавить":
        return await add_snippet_start(update, context)
    elif text == "📋 Все":
        return await show_all_snippets(update, context)
    elif text == "🔍 Поиск":
        await update.message.reply_text(
            "🔍 Введите название сниппета для поиска:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Главное меню")]], resize_keyboard=True)
        )
        context.user_data['waiting_for_search'] = True
    elif text == "🗑️ Удалить":
        return await delete_snippet_start(update, context)
    elif text == "⭐ Избранное":
        return await show_favorites(update, context)
    elif text == "🎯 Фильтры":
        return await show_filters(update, context)
    elif text == "👤 Профиль":
        return await show_profile(update, context)
    elif text == "📊 Статистика":
        return await show_statistics(update, context)
    elif text == "ℹ️ Помощь":
        return await help_command(update, context)
    elif text == "↩️ Главное меню":
        await update.message.reply_text("🏠 Главное меню", reply_markup=get_main_keyboard())
        context.user_data.clear()
    elif context.user_data.get('waiting_for_search'):
        # Обработка поиска
        results = storage.search_snippets(text)
        context.user_data.pop('waiting_for_search', None)
        
        if not results:
            await update.message.reply_text(
                f"❌ Сниппеты с запросом '{text}' не найдены.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Сохраняем результаты поиска
        for name in results.keys():
            snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
            context.user_data[f'snippet_{snippet_id}'] = name
        
        # Сохраняем контекст для навигации
        context.user_data['current_list'] = 'search'
        context.user_data['current_snippets'] = results
        context.user_data['current_page'] = 0
        context.user_data['search_query'] = text

        keyboard, total_pages = create_snippets_keyboard(results, 0, "show", "_search")
        
        await update.message.reply_text(
            f"🔍 Найдено {len(results)} сниппетов по запросу '{text}':",
            reply_markup=keyboard
        )
    # Обработка фильтров по языкам
    elif text.startswith("🟨 JavaScript"):
        filtered = storage.filter_by_language("JavaScript")
        await show_filtered_results(update, context, filtered, "JavaScript")
    elif text.startswith("🐘 PHP"):
        filtered = storage.filter_by_language("PHP")
        await show_filtered_results(update, context, filtered, "PHP")
    elif text.startswith("🎨 CSS"):
        filtered = storage.filter_by_language("CSS")
        await show_filtered_results(update, context, filtered, "CSS")
    elif text.startswith("🌐 HTML"):
        filtered = storage.filter_by_language("HTML")
        await show_filtered_results(update, context, filtered, "HTML")
    # Обработка фильтров по тегам
    elif text.startswith("🏷️ WordPress"):
        filtered = storage.filter_by_tag("WordPress")
        await show_filtered_results(update, context, filtered, "тегу WordPress")
    elif text.startswith("🏷️ Bitrix"):
        filtered = storage.filter_by_tag("Bitrix")
        await show_filtered_results(update, context, filtered, "тегу Bitrix")
    elif text.startswith("🏷️ Общее"):
        filtered = storage.filter_by_tag("Общее")
        await show_filtered_results(update, context, filtered, "тегу Общее")
    else:
        await update.message.reply_text(
            "❓ Не понимаю команду. Используйте меню ниже:",
            reply_markup=get_main_keyboard()
        )

async def show_filtered_results(update: Update, context: CallbackContext, filtered_snippets, filter_name):
    if not filtered_snippets:
        await update.message.reply_text(
            f"❌ Сниппеты по {filter_name} не найдены.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Сохраняем отфильтрованные сниппеты
    for name in filtered_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data[f'snippet_{snippet_id}'] = name
    
    # Сохраняем контекст для навигации
    context.user_data['current_list'] = 'filtered'
    context.user_data['current_snippets'] = filtered_snippets
    context.user_data['current_page'] = 0
    context.user_data['filter_name'] = filter_name

    keyboard, total_pages = create_snippets_keyboard(filtered_snippets, 0, "show", "_filtered")
    
    await update.message.reply_text(
        f"🎯 Найдено {len(filtered_snippets)} сниппетов по {filter_name}:",
        reply_markup=keyboard
    )

async def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("show_"):
        snippet_id = data.replace("show_", "").replace("_search", "").replace("_fav", "").replace("_filtered", "")
        await show_snippet(update, context, snippet_id)
    
    elif data.startswith("copy_"):
        snippet_id = data.replace("copy_", "")
        snippet_name = context.user_data.get(f'snippet_{snippet_id}')
        if snippet_name and snippet_name in storage.snippets:
            snippet = storage.snippets[snippet_name]
            await query.answer(f"📋 Код скопирован в буфер обмена!")
            # Отправляем код отдельным сообщением для удобного копирования
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"```{snippet['language'].lower()}\n{snippet['code']}\n```",
                parse_mode='Markdown'
            )
    
    elif data.startswith("fav_"):
        snippet_id = data.replace("fav_", "")
        snippet_name = context.user_data.get(f'snippet_{snippet_id}')
        if snippet_name:
            if user_manager.add_to_favorites(query.from_user.id, snippet_name):
                await query.answer("❤️ Добавлено в избранное!")
                # Обновляем клавиатуру
                snippet = storage.snippets.get(snippet_name)
                if snippet:
                    is_author = snippet['author'] == (query.from_user.username or query.from_user.full_name)
                    keyboard = get_quick_actions_keyboard(snippet_name, query.from_user.id, is_author)
                    await query.edit_message_reply_markup(reply_markup=keyboard)
            else:
                await query.answer("⚠️ Уже в избранном!")
    
    elif data.startswith("unfav_"):
        snippet_id = data.replace("unfav_", "")
        snippet_name = context.user_data.get(f'snippet_{snippet_id}')
        if snippet_name:
            if user_manager.remove_from_favorites(query.from_user.id, snippet_name):
                await query.answer("💔 Удалено из избранного!")
                # Обновляем клавиатуру
                snippet = storage.snippets.get(snippet_name)
                if snippet:
                    is_author = snippet['author'] == (query.from_user.username or query.from_user.full_name)
                    keyboard = get_quick_actions_keyboard(snippet_name, query.from_user.id, is_author)
                    await query.edit_message_reply_markup(reply_markup=keyboard)
            else:
                await query.answer("⚠️ Не было в избранном!")
    
    elif data.startswith("delete_"):
        snippet_id = data.replace("delete_", "")
        snippet_name = context.user_data.get(f'snippet_{snippet_id}')
        if snippet_name:
            snippet = storage.snippets.get(snippet_name)
            if snippet and snippet['author'] == (query.from_user.username or query.from_user.full_name):
                # Создаем подтверждающую клавиатуру
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{snippet_id}"),
                        InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")
                    ]
                ])
                await query.edit_message_text(
                    f"⚠️ Вы уверены, что хотите удалить сниппет '{snippet_name}'?\n"
                    f"Это действие нельзя отменить!",
                    reply_markup=keyboard
                )
            else:
                await query.answer("❌ Вы можете удалять только свои сниппеты!")
    
    elif data.startswith("confirm_delete_"):
        snippet_id = data.replace("confirm_delete_", "")
        snippet_name = context.user_data.get(f'snippet_{snippet_id}')
        if snippet_name:
            if storage.delete_snippet(snippet_name):
                await query.edit_message_text(f"✅ Сниппет '{snippet_name}' удален!")
                # Удаляем из контекста
                context.user_data.pop(f'snippet_{snippet_id}', None)
            else:
                await query.answer("❌ Ошибка при удалении!")
    
    elif data == "cancel_delete":
        await query.edit_message_text("❌ Удаление отменено")
    
    elif data == "back_to_list":
        # Возвращаемся к предыдущему списку
        current_list = context.user_data.get('current_list')
        current_page = context.user_data.get('current_page', 0)
        
        if current_list == 'all':
            await show_all_snippets(update, context, current_page)
        elif current_list == 'favorites':
            await show_favorites(update, context, current_page)
        elif current_list == 'search':
            search_query = context.user_data.get('search_query', '')
            results = context.user_data.get('current_snippets', {})
            keyboard, total_pages = create_snippets_keyboard(results, current_page, "show", "_search")
            await query.edit_message_text(
                f"🔍 Найдено {len(results)} сниппетов по запросу '{search_query}' (стр. {current_page+1} из {total_pages}):",
                reply_markup=keyboard
            )
        elif current_list == 'filtered':
            filter_name = context.user_data.get('filter_name', 'фильтру')
            results = context.user_data.get('current_snippets', {})
            keyboard, total_pages = create_snippets_keyboard(results, current_page, "show", "_filtered")
            await query.edit_message_text(
                f"🎯 Найдено {len(results)} сниппетов по {filter_name} (стр. {current_page+1} из {total_pages}):",
                reply_markup=keyboard
            )
        else:
            # Возвращаемся к общему списку по умолчанию
            await show_all_snippets(update, context, 0)
    
    elif data.startswith("page_"):
        # Обработка пагинации
        parts = data.split("_")
        if len(parts) >= 3:
            action = parts[1]  # show, delete и т.д.
            page = int(parts[2])
            
            if action == "show":
                current_list = context.user_data.get('current_list')
                if "_fav" in data or current_list == 'favorites':
                    await show_favorites(update, context, page)
                elif "_search" in data or current_list == 'search':
                    search_query = context.user_data.get('search_query', '')
                    results = context.user_data.get('current_snippets', {})
                    context.user_data['current_page'] = page
                    keyboard, total_pages = create_snippets_keyboard(results, page, "show", "_search")
                    await query.edit_message_text(
                        f"🔍 Найдено {len(results)} сниппетов по запросу '{search_query}' (стр. {page+1} из {total_pages}):",
                        reply_markup=keyboard
                    )
                elif "_filtered" in data or current_list == 'filtered':
                    filter_name = context.user_data.get('filter_name', 'фильтру')
                    results = context.user_data.get('current_snippets', {})
                    context.user_data['current_page'] = page
                    keyboard, total_pages = create_snippets_keyboard(results, page, "show", "_filtered")
                    await query.edit_message_text(
                        f"🎯 Найдено {len(results)} сниппетов по {filter_name} (стр. {page+1} из {total_pages}):",
                        reply_markup=keyboard
                    )
                else:
                    await show_all_snippets(update, context, page)
    
    elif data == "noop":
        # Заглушка для кнопок-индикаторов
        pass

def main():
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик диалога добавления сниппета
    add_snippet_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📥 Добавить$"), add_snippet_start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_name)],
            GET_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_language)],
            GET_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_tags)],
            GET_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_code),
                CommandHandler("done", done_adding_code)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^↩️ Отмена$"), cancel)
        ]
    )
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_snippets))
    application.add_handler(add_snippet_handler)
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    print("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
