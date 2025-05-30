import logging
import os
import re
import json
import hashlib
import math
from datetime import datetime
import random
import aiofiles
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from telegram.error import TelegramError

# Constants
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN or not re.match(r'^\d+:[A-Za-z0-9_-]+$', BOT_TOKEN):
    raise ValueError("Некорректный формат BOT_TOKEN")
MAX_CODE_LENGTH = 4000
MAX_NAME_LENGTH = 100
ITEMS_PER_PAGE = 10
MEME_PROBABILITY = 0.2

if not os.path.exists('data'):
    os.makedirs('data')

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# File paths
SNIPPETS_FILE = 'data/shared_snippets.json'
PENDING_SNIPPETS_FILE = 'data/pending_snippets.json'
USERS_FILE = 'data/users.json'
ADMINS_FILE = 'data/admins.json'

# States
GET_NAME, GET_LANGUAGE, GET_TAGS, GET_CODE = range(4)

# Languages and categories
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
    4: {'name': 'Senior', 'emoji': '🦅', 'min_snippets': 50, 'min_uses': 1000},
    5: {'name': 'Кодовый маг', 'emoji': '🧙‍♂️', 'min_snippets': 100, 'min_uses': 2500},
    6: {'name': 'Архитектор кода', 'emoji': '🏛️', 'min_snippets': 200, 'min_uses': 5000},
    7: {'name': 'Кодовый титан', 'emoji': '💪⚡️', 'min_snippets': 350, 'min_uses': 10000},
    8: {'name': 'Легенда кода', 'emoji': '🌟👑', 'min_snippets': 500, 'min_uses': 20000},
    9: {'name': 'Бог кода', 'emoji': '⚜️🔥', 'min_snippets': 1000, 'min_uses': 50000}
}

ACHIEVEMENTS = {
    'first_snippet': {'name': 'Первый сниппет', 'emoji': '🎉', 'description': 'Добавил первый сниппет'},
    'popular_author': {'name': 'Популярный автор', 'emoji': '⭐', 'description': '100+ использований сниппетов'},
    'code_master': {'name': 'Мастер кода', 'emoji': '🏆', 'description': '500+ использований сниппетов'},
    'multilang': {'name': 'Полиглот', 'emoji': '🌍', 'description': 'Сниппеты на всех языках'},
    'helpful': {'name': 'Помощник', 'emoji': '🤝', 'description': '10+ сниппетов в избранном у других'},
    'active': {'name': 'Активист', 'emoji': '🔥', 'description': '25+ сниппетов'},
    'code_comedian': {'name': 'Кодовый комик', 'emoji': '😂', 'description': 'Увидел 10 разных мемов от бота'},
    'reliable_coder': {'name': 'Надёжный кодер', 'emoji': '✅', 'description': 'Сниппет прошёл модерацию и был одобрен'},
    'snippet_marathon': {'name': 'Марафон сниппетов', 'emoji': '🏃', 'description': 'Добавил 5 сниппетов за один день'},
    'code_sensei': {'name': 'Кодовый сенсей', 'emoji': '🥋', 'description': '50+ одобренных сниппетов'},
    'tag_master': {'name': 'Мастер тегов', 'emoji': '🏷️', 'description': 'Использовал все доступные теги'},
    'speed_coder': {'name': 'Скоростной кодер', 'emoji': '⚡', 'description': 'Добавил сниппет менее чем за 1 минуту'},
    'community_star': {'name': 'Звезда сообщества', 'emoji': '🌟', 'description': '25+ пользователей добавили сниппет в избранное'},
    'code_veteran': {'name': 'Ветеран кода', 'emoji': '🛡️', 'description': '100+ сниппетов'},
    'bug_hunter': {'name': 'Охотник за багами', 'emoji': '🕵️', 'description': '10+ отклонённых сниппетов (для админов)'},
    'language_guru': {'name': 'Гуру языка', 'emoji': '📚', 'description': '10+ сниппетов на одном языке'},
    'snippet_savant': {'name': 'Савант сниппетов', 'emoji': '🧠', 'description': '1000+ просмотров всех сниппетов'},
    'early_bird': {'name': 'Ранняя пташка', 'emoji': '🌅', 'description': 'Добавил сниппет с 5:00 до 7:00'},
    'night_owl': {'name': 'Ночной кодер', 'emoji': '🦇', 'description': 'Добавил сниппет с 23:00 до 3:00'},
    'code_crafter': {'name': 'Мастер кода', 'emoji': '🔨', 'description': 'Сниппет длиннее 1000 символов'},
    'loyal_coder': {'name': 'Верный кодер', 'emoji': '🤗', 'description': 'Использует бота 30+ дней'},
    'gatekeeper': {'name': 'Страж кода', 'emoji': '🛑', 'description': 'Модерировал 50+ сниппетов (для админов)'},
    'justice_bringer': {'name': 'Вершитель правосудия', 'emoji': '⚖️', 'description': 'Отклонил 25+ сниппетов с подробными причинами (для админов)'},
    'admin_mentor': {'name': 'Наставник админов', 'emoji': '👨‍🏫', 'description': 'Добавил 5+ новых администраторов (для админов)'},
    'swift_moderator': {'name': 'Быстрый модератор', 'emoji': '🏎️', 'description': 'Модерировал 10+ сниппетов за час (для админов)'},
    'code_inspector': {'name': 'Инспектор кода', 'emoji': '🔍', 'description': 'Одобрил 25+ сниппетов без жалоб (для админов)'}
}

CODE_MEMES = [
    "Твой код настолько чистый, что его можно подавать на CodePen! 😎",
    "Скопировал код? Не забудь убрать console.log! 😉",
    "PHP? Это же слонячий код! 🐘",
    "CSS: когда ты хотел быть дизайнером, но стал кодером! 🎨",
    "JavaScript: потому что var всё ещё живёт в наших сердцах! 🟨",
    "HTML: тег <br> — лучший способ сказать 'я сдаюсь'! 🌐",
    "Код без багов? Это миф, как единорог! 🦄",
    "Ты только что добавил сниппет? Пора за кофе! ☕",
    "Сниппет готов? Проверяй, не сломал ли ты продакшен! 🚨",
    "Код работает? Не трогай, оно само! 😅",
    "Когда твой код работает с первого раза... Подозрительно! 🤔",
    "CSS: 99% времени — это борьба с margin! 😤",
    "JavaScript: async/await или как я перестал бояться и полюбил промисы! 🥳",
    "PHP: echo 'Я всё ещё здесь!'; 🐘",
    "Код без комментариев? Это как лабиринт без карты! 🗺️",
    "HTML: <div> внутри <div> внутри <div>... Погружение началось! 🌊",
    "Твой сниппет настолько хорош, что его лайкнул даже продакшен! 🚀"
]

class AdminManager:
    def __init__(self):
        self.admins = []

    async def initialize(self):
        await self.load_admins()

    async def load_admins(self):
        if os.path.exists(ADMINS_FILE):
            try:
                async with aiofiles.open(ADMINS_FILE, 'r', encoding='utf-8') as f:
                    self.admins = json.loads(await f.read())
                logger.info(f"Загружено {len(self.admins)} администраторов")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка при загрузке админов: {e}")
                self.admins = []
        else:
            logger.warning(f"Файл {ADMINS_FILE} не найден, список админов пуст")
            self.admins = []

    async def save_admins(self):
        try:
            async with aiofiles.open(ADMINS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.admins, indent=2, ensure_ascii=False))
        except IOError as e:
            logger.error(f"Ошибка при сохранении админов: {e}")

    def is_admin(self, user_id):
        return str(user_id) in self.admins

    async def add_admin(self, user_id):
        user_id = str(user_id)
        if user_id not in self.admins:
            self.admins.append(user_id)
            await self.save_admins()
            return True
        return False

class UserManager:
    def __init__(self):
        self.users = {}

    async def initialize(self):
        await self.load_users()

    async def load_users(self):
        if not os.path.exists(USERS_FILE):
            logger.info(f"Файл {USERS_FILE} не найден, создаём пустой")
            self.users = {}
            try:
                await self.save_users()
            except Exception as e:
                logger.error(f"Ошибка при создании {USERS_FILE}: {e}", exc_info=True)
            return
        try:
            async with aiofiles.open(USERS_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    self.users = json.loads(content)
                    logger.info(f"Загружено {len(self.users)} пользователей")
                else:
                    logger.warning(f"Файл {USERS_FILE} пуст, инициализируем пустым")
                    self.users = {}
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка при загрузке пользователей: {e}", exc_info=True)
            backup_file = f"{USERS_FILE}.bak"
            if os.path.exists(backup_file):
                logger.info(f"Попытка восстановления из резервной копии {backup_file}")
                try:
                    async with aiofiles.open(backup_file, 'r', encoding='utf-8') as f:
                        self.users = json.loads(await f.read())
                        await self.save_users()
                        logger.info("Пользователи восстановлены из резервной копии")
                except Exception as e:
                    logger.error(f"Ошибка восстановления пользователей: {e}", exc_info=True)
                    self.users = {}
            else:
                self.users = {}

    async def save_users(self):
        try:
            os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
            if os.path.exists(USERS_FILE):
                import shutil
                shutil.copy(USERS_FILE, f"{USERS_FILE}.bak")
                logger.info(f"Создана резервная копия {USERS_FILE}.bak")
            async with aiofiles.open(USERS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.users, indent=2, ensure_ascii=False))
            logger.info(f"Сохранено {len(self.users)} пользователей")
        except (IOError, OSError) as e:
            logger.error(f"Ошибка при сохранении пользователей: {e}", exc_info=True)
            raise

    def get_user(self, user_id):
        user_id = str(user_id)
        if user_id not in self.users:
            self.users[user_id] = {
                'favorites': [],
                'achievements': [],
                'level': 0,
                'total_snippets': 0,
                'total_uses': 0,
                'join_date': datetime.now().isoformat(),
                'seen_memes': [],
                'username': None,
                'last_submission_date': None,
                'submissions_today': 0
            }
        return self.users[user_id]

    async def update_user_stats(self, user_id, snippets_count, uses_count):
        user = self.get_user(user_id)
        user['total_snippets'] = snippets_count
        user['total_uses'] = uses_count
        
        old_level = user['level']
        for level, data in USER_LEVELS.items():
            if snippets_count >= data['min_snippets'] and uses_count >= data['min_uses']:
                user['level'] = level
        
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

        if snippets_count > 0 and 'multilang' not in user['achievements']:
            user_snippets = [data for data in storage.snippets.values() 
                            if data['author'] == user.get('username', '')]
            languages_used = set(snippet['language'] for snippet in user_snippets)
            if len(languages_used) >= len(LANGUAGES):
                user['achievements'].append('multilang')
                new_achievements.append('multilang')
        
        if 'helpful' not in user['achievements']:
            user_snippet_names = [name for name, data in storage.snippets.items() 
                                 if data['author'] == user.get('username', '')]
            total_favorites = sum(1 for other_user in self.users.values() 
                                 for fav in other_user['favorites'] 
                                 if fav in user_snippet_names)
            if total_favorites >= 10:
                user['achievements'].append('helpful')
                new_achievements.append('helpful')
        
        if user.get('submissions_today', 0) >= 5 and 'snippet_marathon' not in user['achievements']:
            user['achievements'].append('snippet_marathon')
            new_achievements.append('snippet_marathon')

        if snippets_count >= 50 and 'code_sensei' not in user['achievements']:
            user['achievements'].append('code_sensei')
            new_achievements.append('code_sensei')

        if snippets_count > 0 and 'tag_master' not in user['achievements']:
            user_snippets = [data for data in storage.snippets.values() 
                            if data['author'] == user.get('username', '')]
            tags_used = set(tag for snippet in user_snippets for tag in snippet.get('tags', []))
            if len(tags_used) >= len(CATEGORIES):
                user['achievements'].append('tag_master')
                new_achievements.append('tag_master')

        if 'community_star' not in user['achievements']:
            user_snippet_names = [name for name, data in storage.snippets.items() 
                                 if data['author'] == user.get('username', '')]
            favorite_users = set(user_id for user_id, other_user in self.users.items() 
                                for fav in other_user['favorites'] if fav in user_snippet_names)
            if len(favorite_users) >= 25:
                user['achievements'].append('community_star')
                new_achievements.append('community_star')

        if snippets_count >= 100 and 'code_veteran' not in user['achievements']:
            user['achievements'].append('code_veteran')
            new_achievements.append('code_veteran')

        if 'bug_hunter' not in user['achievements'] and admin_manager.is_admin(user_id):
            rejected_count = user.get('rejected_snippets', 0)
            if rejected_count >= 10:
                user['achievements'].append('bug_hunter')
                new_achievements.append('bug_hunter')

        if snippets_count > 0 and 'language_guru' not in user['achievements']:
            user_snippets = [data for data in storage.snippets.values() 
                            if data['author'] == user.get('username', '')]
            lang_counts = {}
            for snippet in user_snippets:
                lang = snippet['language']
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
                if lang_counts[lang] >= 10:
                    user['achievements'].append('language_guru')
                    new_achievements.append('language_guru')
                    break

        if uses_count >= 1000 and 'snippet_savant' not in user['achievements']:
            user['achievements'].append('snippet_savant')
            new_achievements.append('snippet_savant')

        if 'loyal_coder' not in user['achievements']:
            join_date = datetime.fromisoformat(user['join_date'])
            days_active = (datetime.now() - join_date).days
            if days_active >= 30:
                user['achievements'].append('loyal_coder')
                new_achievements.append('loyal_coder')

        if 'gatekeeper' not in user['achievements'] and admin_manager.is_admin(user_id):
            moderated_count = user.get('approved_snippets', 0) + user.get('rejected_snippets', 0)
            if moderated_count >= 50:
                user['achievements'].append('gatekeeper')
                new_achievements.append('gatekeeper')

        if 'code_inspector' not in user['achievements'] and admin_manager.is_admin(user_id):
            approved_count = user.get('approved_snippets', 0)
            complaints = user.get('complaints', 0)
            if approved_count >= 25 and complaints == 0:
                user['achievements'].append('code_inspector')
                new_achievements.append('code_inspector')

        await self.save_users()
        return old_level != user['level'], new_achievements

    async def add_to_favorites(self, user_id, snippet_name):
        user = self.get_user(user_id)
        if snippet_name not in user['favorites']:
            user['favorites'].append(snippet_name)
            await self.save_users()
            return True
        return False

    async def remove_from_favorites(self, user_id, snippet_name):
        user = self.get_user(user_id)
        if snippet_name in user['favorites']:
            user['favorites'].remove(snippet_name)
            await self.save_users()
            return True
        return False

    def is_favorite(self, user_id, snippet_name):
        user = self.get_user(user_id)
        return snippet_name in user['favorites']

class SharedSnippetStorage:
    def __init__(self):
        self.snippets = {}
        self.pending_snippets = {}

    async def initialize(self):
        await self.load_snippets()
        await self.load_pending_snippets()

    async def load_snippets(self):
        if os.path.exists(SNIPPETS_FILE):
            try:
                async with aiofiles.open(SNIPPETS_FILE, 'r', encoding='utf-8') as f:
                    self.snippets = json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Ошибка при загрузке сниппетов: {e}")
                self.snippets = {}

    async def load_pending_snippets(self):
        if not os.path.exists(PENDING_SNIPPETS_FILE):
            logger.info(f"Файл {PENDING_SNIPPETS_FILE} не найден, создаём пустой")
            self.pending_snippets = {}
            try:
                await self.save_pending_snippets()
            except Exception as e:
                logger.error(f"Ошибка при создании {PENDING_SNIPPETS_FILE}: {e}", exc_info=True)
            return
        try:
            async with aiofiles.open(PENDING_SNIPPETS_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    self.pending_snippets = json.loads(content)
                    logger.info(f"Загружено {len(self.pending_snippets)} ожидающих сниппетов")
                else:
                    logger.warning(f"Файл {PENDING_SNIPPETS_FILE} пуст, инициализируем пустым")
                    self.pending_snippets = {}
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка при загрузке ожидающих сниппетов: {e}", exc_info=True)
            backup_file = f"{PENDING_SNIPPETS_FILE}.bak"
            if os.path.exists(backup_file):
                logger.info(f"Попытка восстановления из резервной копии {backup_file}")
                try:
                    async with aiofiles.open(backup_file, 'r', encoding='utf-8') as f:
                        self.pending_snippets = json.loads(await f.read())
                        await self.save_pending_snippets()
                        logger.info("Ожидающие сниппеты восстановлены из резервной копии")
                except Exception as e:
                    logger.error(f"Ошибка восстановления ожидающих сниппетов: {e}", exc_info=True)
                    self.pending_snippets = {}
            else:
                self.pending_snippets = {}

    async def save_pending_snippets(self):
        try:
            os.makedirs(os.path.dirname(PENDING_SNIPPETS_FILE), exist_ok=True)
            if os.path.exists(PENDING_SNIPPETS_FILE):
                import shutil
                shutil.copy(PENDING_SNIPPETS_FILE, f"{PENDING_SNIPPETS_FILE}.bak")
                logger.info(f"Создана резервная копия {PENDING_SNIPPETS_FILE}.bak")
            async with aiofiles.open(PENDING_SNIPPETS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.pending_snippets, indent=2, ensure_ascii=False))
            logger.info(f"Сохранено {len(self.pending_snippets)} ожидающих сниппетов")
        except (IOError, OSError) as e:
            logger.error(f"Ошибка при сохранении ожидающих сниппетов: {e}", exc_info=True)
            raise

    async def save_snippets(self):
        try:
            async with aiofiles.open(SNIPPETS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.snippets, indent=2, ensure_ascii=False))
        except IOError as e:
            logger.error(f"Ошибка при сохранении сниппетов: {e}")

    async def add_snippet(self, name, code, language, author, tags=None):
        if name not in self.snippets:
            self.snippets[name] = {
                'code': code,
                'language': language,
                'author': author,
                'uses': 0,
                'tags': tags or [],
                'created_date': datetime.now().isoformat()
            }
            await self.save_snippets()
            return True
        return False

    async def add_pending_snippet(self, name, code, language, author, author_id, tags=None):
        if len(name) > MAX_NAME_LENGTH or len(code) > MAX_CODE_LENGTH:
            return False
        if name not in self.pending_snippets:
            self.pending_snippets[name] = {
                'code': code,
                'language': language,
                'author': author,
                'tags': tags or [],
                'created_date': datetime.now().isoformat(),
                'user_id': str(author_id)
            }
            await self.save_pending_snippets()
            return True
        return False

    async def approve_snippet(self, name):
        if name in self.pending_snippets:
            snippet = self.pending_snippets[name]
            success = await self.add_snippet(name, snippet['code'], snippet['language'], snippet['author'], snippet['tags'])
            if success:
                del self.pending_snippets[name]
                await self.save_pending_snippets()
                return True
        return False

    async def reject_snippet(self, name):
        if name in self.pending_snippets:
            del self.pending_snippets[name]
            await self.save_pending_snippets()
            return True
        return False

    async def get_snippet(self, name):
        if name in self.snippets:
            self.snippets[name]['uses'] += 1
            await self.save_snippets()
            return self.snippets[name]
        return None

    async def delete_snippet(self, name):
        if name in self.snippets:
            del self.snippets[name]
            await self.save_snippets()
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
admin_manager = AdminManager()

def get_main_keyboard(is_admin=False):
    keyboard = [
        [KeyboardButton("📥 Добавить"), KeyboardButton("🔍 Поиск"), KeyboardButton("📋 Все")],
        [KeyboardButton("🗑️ Удалить"), KeyboardButton("⭐ Избранное"), KeyboardButton("🎯 Фильтры")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("📊 Статистика"), KeyboardButton("ℹ️ Помощь")],
        [KeyboardButton("📂 FTP BackUp")]
    ]
    if is_admin:
        keyboard.insert(0, [KeyboardButton("🔧 Админ-меню")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_filter_keyboard():
    keyboard = []
    lang_row = []
    for lang, emoji in LANGUAGES.items():
        lang_row.append(KeyboardButton(f"{emoji} {lang}"))
    keyboard.append(lang_row[:2])
    keyboard.append(lang_row[2:])
    tag_row = []
    for tag in CATEGORIES:
        tag_row.append(KeyboardButton(f"🏗️ {tag}"))
    keyboard.append(tag_row)
    keyboard.append([KeyboardButton("↩️ Главное меню")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Сниппеты на модерации", callback_data="admin_pending")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
    ])

def get_quick_actions_keyboard(snippet_name, user_id, is_author=False):
    keyboard = []
    row1 = [InlineKeyboardButton("📜 Копировать", callback_data=f"copy_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}")]
    if user_manager.is_favorite(user_id, snippet_name):
        row1.append(InlineKeyboardButton("💔 Из избранного", callback_data=f"unfav_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
    else:
        row1.append(InlineKeyboardButton("❤️ В избранное", callback_data=f"fav_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
    keyboard.append(row1)
    row2 = []
    if is_author:
        row2.append(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{hashlib.md5(snippet_name.encode()).hexdigest()[:16]}"))
    row2.append(InlineKeyboardButton("🔙 Назад", callback_data="back_to_list"))
    keyboard.append(row2)
    return InlineKeyboardMarkup(keyboard)

def get_pending_snippets_keyboard(page=0):
    pending_snippets = storage.pending_snippets
    total_pages = math.ceil(len(pending_snippets) / ITEMS_PER_PAGE)
    if page >= total_pages:
        page = 0
    elif page < 0:
        page = total_pages - 1 if total_pages > 0 else 0
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_snippets = list(pending_snippets.keys())[start_idx:end_idx]
    keyboard = []
    for name in page_snippets:
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        data = pending_snippets[name]
        language_emoji = LANGUAGES.get(data['language'], '📜')
        btn_text = f"{language_emoji} {name}"
        if data.get('tags'):
            btn_text += f" 🗂️{'/'.join(data['tags'])}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"review_{snippet_id}")])
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Пред", callback_data=f"page_pending_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"📖 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("След ➡️", callback_data=f"page_pending_{page+1}"))
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔙 Админ-меню", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(keyboard), total_pages

def get_users_keyboard(page=0):
    users = list(user_manager.users.keys())
    total_pages = math.ceil(len(users) / ITEMS_PER_PAGE)
    if page >= total_pages:
        page = 0
    elif page < 0:
        page = total_pages - 1 if total_pages > 0 else 0
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_users = users[start_idx:end_idx]
    keyboard = []
    for user_id in page_users:
        user = user_manager.get_user(user_id)
        username = user.get('username', f"User {user_id}")
        btn_text = f"👤 {username}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_user_{user_id}")])
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Пред", callback_data=f"page_users_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"📖 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("След ➡️", callback_data=f"page_users_{page+1}"))
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔙 Админ-меню", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(keyboard), total_pages

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    if not admin_manager.is_admin(update.effective_user.id):
        await update_or_send_message(update, context, "❌ Эта команда только для администраторов!", reply_markup=get_main_keyboard())
        return
    if not user_manager.users:
        await update_or_send_message(update, context, "👥 Нет зарегистрированных пользователей.", reply_markup=get_admin_keyboard())
        return
    context.user_data['navigation'] = context.user_data.get('navigation', {})
    context.user_data['navigation']['current_list'] = 'users'
    context.user_data['navigation']['current_page'] = page
    keyboard, total_pages = get_users_keyboard(page)
    await update_or_send_message(
        update,
        context,
        f"👥 Список пользователей (стр. {page+1}/{total_pages}):",
        reply_markup=keyboard
    )

async def show_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if not admin_manager.is_admin(update.effective_user.id):
        await update.callback_query.answer("❌ Только администраторы могут просматривать профили!")
        return
    user_data = user_manager.get_user(user_id)
    if not user_data:
        await update.callback_query.answer("❌ Пользователь не найден!")
        return
    level_info = USER_LEVELS[user_data['level']]
    snippets_count, uses_count = storage.get_user_snippets_stats(user_data.get('username', ''))
    profile_text = (
        f"👨‍🎤 Профиль пользователя {user_data.get('username', f'User {user_id}')}\n\n"
        f"📖 Уровень: {level_info['emoji']} {level_info['name']}\n"
        f"📩 Сниппетов: {snippets_count}\n"
        f"👍 Общие просмотры: {uses_count}\n"
        f"⭐ В избранном: {len(user_data['favorites'])}\n"
        f"📅 Дата регистрации: {user_data['join_date'][:10]}\n\n"
    )
    if admin_manager.is_admin(user_id):
        profile_text += "🔧 Статус: Администратор\n\n"
    if user_data.get('achievements'):
        profile_text += "📖 Достижения:\n"
        for achievement in user_data['achievements']:
            ach_info = ACHIEVEMENTS[achievement]
            profile_text += f"{ach_info['emoji']} {ach_info['name']}: {ach_info['description']}\n"
    else:
        profile_text += "❌ Достижений пока нет\n"
    if user_data['level'] < 9:
        next_level = USER_LEVELS[user_data['level'] + 1]
        profile_text += f"\n📈 До уровня {next_level['emoji']} {next_level['name']}:\n"
        profile_text += f"   Сниппеты: {snippets_count}/{next_level['min_snippets']}\n"
        profile_text += f"   Просмотры: {uses_count}/{next_level['min_uses']}\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 К списку пользователей", callback_data="back_to_users")]
    ])
    await update_or_send_message(
        update,
        context,
        profile_text,
        reply_markup=keyboard
    )

def create_snippets_keyboard(snippets_dict, page=0, callback_prefix="show", extra_data="", show_language=True):
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
    for name in page_snippets:
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        data = snippets_dict[name]
        language_emoji = LANGUAGES.get(data['language'], '📜')
        if show_language:
            btn_text = f"{language_emoji} {name}"
            if data.get('tags'):
                btn_text += f" 🗂️{'/'.join(data['tags'])}"
            btn_text += f" (👍 {data['uses']})"
        else:
            btn_text = f"{name} (👍 {data['uses']})"
        callback_data = f"{callback_prefix}_{snippet_id}{extra_data}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Пред", callback_data=f"page_{callback_prefix}_{page-1}{extra_data}"))
        nav_buttons.append(InlineKeyboardButton(f"📖 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("След ➡️", callback_data=f"page_{callback_prefix}_{page+1}{extra_data}"))
        keyboard.append(nav_buttons)
    return InlineKeyboardMarkup(keyboard), total_pages

async def update_or_send_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text, reply_markup=None, parse_mode=None):
    chat_id = update.effective_chat.id
    last_message_id = context.user_data.get('last_message_id')

    # Пытаемся удалить предыдущее сообщение, если оно существует
    if last_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_message_id)
            logger.debug(f"Удалено предыдущее сообщение с ID {last_message_id}")
        except TelegramError as e:
            logger.warning(f"Не удалось удалить сообщение {last_message_id}: {e}")

    # Отправляем новое сообщение
    try:
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        context.user_data['last_message_id'] = message.message_id
        logger.debug(f"Отправлено новое сообщение с ID {message.message_id}")
        return message.message_id
    except TelegramError as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        raise

async def send_random_meme(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    user = user_manager.get_user(user_id)
    available_memes = [meme for meme in CODE_MEMES if meme not in user.get('seen_memes', [])]
    if not available_memes:
        user['seen_memes'] = []
        available_memes = CODE_MEMES
    meme = random.choice(available_memes)
    user['seen_memes'].append(meme)
    if len(user['seen_memes']) >= 10 and 'code_comedian' not in user['achievements']:
        user['achievements'].append('code_comedian')
        await update_or_send_message(
            update,
            context,
            f"🎉 Новое достижение!\n😂 Кодовый комедиант\nУвидел 10 разных мемов от бота"
        )
    await user_manager.save_users()
    await update_or_send_message(
        update,
        context,
        meme
    )

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, snippet_name, snippet_data):
    language_emoji = LANGUAGES.get(snippet_data.get('language', ''), '📜')
    for admin_id in admin_manager.admins:
        try:
            tags = snippet_data.get('tags', [])
            tags_text = ', '.join(tags) if tags else 'Без тегов'
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🖋 Новый сниппет на модерацию: '{snippet_name}'\n"
                     f"{language_emoji} Язык: {snippet_data.get('language', 'Неизвестно')}\n"
                     f"👨‍🎤 Автор: {snippet_data.get('author', 'Неизвестно')}\n"
                     f"🗂️ Теги: {tags_text}\n"
                     f"📜 Код:\n```{snippet_data.get('language', '').lower()}\n{snippet_data.get('code', '')}\n```",
                parse_mode='Markdown'
            )
        except TelegramError as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    user_data = user_manager.get_user(user.id)
    level_info = USER_LEVELS[user_data['level']]
    is_admin = admin_manager.is_admin(user.id)
    text = (
        f"👋 Привет, {user.first_name}!\n"
        f"🎖️ Ваш уровень: {level_info['emoji']} {level_info['name']}\n\n"
        f"Я бот для общей библиотеки кода с поддержкой тегов и достижений!\n"
        f"Поддерживаемые языки: {' '.join([f'{emoji} {lang}' for lang, emoji in LANGUAGES.items()])}"
    )
    if is_admin:
        text += "\n\n🔧 Вы администратор! Используйте кнопку 'Админ-меню' или /pending для управления."
    await update_or_send_message(update, context, text, reply_markup=get_main_keyboard(is_admin))

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_manager.is_admin(update.effective_user.id):
        await update_or_send_message(update, context, "❌ Эта команда только для администраторов!", reply_markup=get_main_keyboard())
        return
    await update_or_send_message(
        update,
        context,
        "🔧 Админ-меню:\nВыберите действие:",
        reply_markup=get_admin_keyboard()
    )

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_manager.is_admin(update.effective_user.id):
        await update_or_send_message(update, context, "❌ Только администраторы могут добавлять новых администраторов!", reply_markup=get_main_keyboard())
        return
    if len(context.args) != 1:
        await update_or_send_message(update, context, "❌ Используйте: /addadmin <user_id>", reply_markup=get_main_keyboard())
        return
    try:
        new_admin_id = context.args[0]
        user = user_manager.get_user(update.effective_user.id)
        if await admin_manager.add_admin(new_admin_id):
            user['added_admins'] = user.get('added_admins', 0) + 1
            if user['added_admins'] >= 5 and 'admin_mentor' not in user['achievements']:
                user['achievements'].append('admin_mentor')
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🎉 Новое достижение!\n{ACHIEVEMENTS['admin_mentor']['emoji']} {ACHIEVEMENTS['admin_mentor']['name']}\n"
                         f"{ACHIEVEMENTS['admin_mentor']['description']}"
                )
            await user_manager.save_users()
            await update_or_send_message(update, context, f"✅ Пользователь {new_admin_id} добавлен в администраторы!", reply_markup=get_main_keyboard(True))
        else:
            await update_or_send_message(update, context, f"⚠️ Пользователь {new_admin_id} уже администратор!", reply_markup=get_main_keyboard(True))
    except TelegramError as e:
        logger.error(f"Ошибка при добавлении администратора: {e}")
        await update_or_send_message(update, context, "❌ Ошибка при добавлении администратора!", reply_markup=get_main_keyboard(True))

async def pending_snippets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_manager.is_admin(update.effective_user.id):
        await update_or_send_message(update, context, "❌ Эта команда только для администраторов!", reply_markup=get_main_keyboard())
        return
    if not storage.pending_snippets:
        await update_or_send_message(update, context, "🖋 Очередь модерации пустая.", reply_markup=get_admin_keyboard())
        return
    context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
    for name in storage.pending_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data['snippets_map'][f'pending_snippet_{snippet_id}'] = name
    keyboard, total_pages = get_pending_snippets_keyboard(page=0)
    await update_or_send_message(update, context, f"🖋 Сниппеты на модерации (стр. 1/{total_pages}):", reply_markup=keyboard)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_data = user_manager.get_user(user.id)
        user_data['username'] = user.username or user.full_name or f"User {user.id}"
        await user_manager.save_users()
        level_info = USER_LEVELS[user_data['level']]
        snippets_count, uses_count = storage.get_user_snippets_stats(user_data['username'])
        level_up, new_achievements = await user_manager.update_user_stats(user.id, snippets_count, uses_count)
        profile_text = (
            f"👨‍🎤 Профиль пользователя {user_data['username']}\n\n"
            f"📖 Уровень: {level_info['emoji']} {level_info['name']}\n"
            f"📩 Сниппетов: {snippets_count}\n"
            f"👍 Общие просмотры: {uses_count}\n"
            f"⭐ В избранном: {len(user_data['favorites'])}\n\n"
        )
        is_admin = admin_manager.is_admin(user.id)
        if is_admin:
            profile_text += "🔧 Статус: Администратор\n\n"
        if user_data.get('achievements'):
            profile_text += "📖 Достижения:\n"
            for achievement in user_data['achievements']:
                ach_info = ACHIEVEMENTS.get(achievement, {'emoji': '❓', 'name': 'Неизвестно', 'description': ''})
                profile_text += f"{ach_info['emoji']} {ach_info['name']}: {ach_info['description']}\n"
        else:
            profile_text += "❌ Достижений пока нет\n"
        if user_data['level'] < 9:
            next_level = USER_LEVELS[user_data['level'] + 1]
            profile_text += f"\n📈 До уровня {next_level['emoji']} {next_level['name']}:\n"
            profile_text += f"   Сниппеты: {snippets_count}/{next_level['min_snippets']}\n"
            profile_text += f"   Просмотры: {uses_count}/{next_level['min_uses']}\n"
        await update_or_send_message(update, context, profile_text, reply_markup=get_main_keyboard(is_admin))
        if new_achievements:
            for achievement in new_achievements:
                ach_info = ACHIEVEMENTS.get(achievement, {'emoji': '❓', 'name': 'Неизвестно', 'description': ''})
                await update_or_send_message(
                    update,
                    context,
                    f"🎉 Новое достижение!\n{ach_info['emoji']} {ach_info['name']}\n{ach_info['description']}"
                )
        if level_up:
            await update_or_send_message(
                update,
                context,
                f"🎊 Поздравляем! Вы достигли уровня {level_info['emoji']} {level_info['name']}!"
            )
        if random.random() < MEME_PROBABILITY:
            await send_random_meme(update, context, user.id)
    except Exception as e:
        logger.error(f"Ошибка в show_profile: {e}", exc_info=True)
        is_admin = admin_manager.is_admin(update.effective_user.id)
        await update_or_send_message(
            update,
            context,
            "❌ Ошибка при отображении профиля. Попробуйте снова.",
            reply_markup=get_main_keyboard(is_admin)
        )

async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update_or_send_message(
        update,
        context,
        text="🎯 Выберите фильтр для поиска сниппетов:",
        reply_markup=get_filter_keyboard()
    )

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    user_data = user_manager.get_user(update.effective_user.id)
    favorites = user_data.get('favorites', [])
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if not favorites:
        await update_or_send_message(
            update,
            context,
            text="⭐ У вас нет избранных сниппетов.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    favorite_snippets = {name: storage.snippets[name] for name in favorites if name in storage.snippets}
    if not favorite_snippets:
        await update_or_send_message(
            update,
            context,
            text="⭐ Ваши избранные сниппеты были удалены.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
    for name in favorite_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data['snippets_map'][snippet_id] = name
    context.user_data['navigation'] = context.user_data.get('navigation', {})
    context.user_data['navigation']['current_list'] = 'favorites'
    context.user_data['navigation']['current_page'] = page
    keyboard, total_pages = create_snippets_keyboard(favorite_snippets, page, "show", "_fav")
    text = f"📖 Избранные сниппеты (стр. {page+1}/{total_pages}):"
    await update_or_send_message(update, context, text=text, reply_markup=keyboard)

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_snippets = len(storage.snippets)
    total_uses = sum(snippet.get('uses', 0) for snippet in storage.snippets.values())
    lang_stats = {}
    for snippet in storage.snippets.values():
        lang = snippet.get('language')
        if lang not in lang_stats:
            lang_stats[lang] = {'snippets': 0, 'uses': 0}
        lang_stats[lang]['snippets'] += 1
        lang_stats[lang]['uses'] += snippet.get('uses', 0)
    tag_stats = {}
    for snippet in storage.snippets.values():
        for tag in snippet.get('tags', []):
            if tag not in tag_stats:
                tag_stats[tag] = 0
            tag_stats[tag] += 1
    author_stats = {}
    for snippet in storage.snippets.values():
        author = snippet['author']
        if author not in author_stats:
            author_stats[author] = {'snippets': 0, 'uses': 0}
        author_stats[author]['snippets'] += 1
        author_stats[author]['uses'] += snippet.get('uses', 0)
    top_authors = sorted(author_stats.items(), key=lambda x: x[1]['uses'], reverse=True)[:3]
    stats_text = (
        f"📊 Статистика бота:\n\n"
        f"📝 Всего сниппетов: {total_snippets}\n"
        f"🖍️ Ожидают модерации: {len(storage.pending_snippets)}\n"
        f"👍 Общие просмотры: {total_uses}\n"
        f"👥 Пользователи: {len(user_manager.users)}\n\n"
    )
    if lang_stats:
        stats_text += "📈 По языкам:\n"
        for lang, stats in lang_stats.items():
            emoji = LANGUAGES.get(lang, '📜')
            stats_text += f"{emoji} {lang}: {stats['snippets']} шт. ({stats['uses']} просмотров)\n"
        stats_text += "\n"
    if tag_stats:
        stats_text += "🗂️ По тегам:\n"
        for tag, count in tag_stats.items():
            stats_text += f"• {tag}: {count} шт.\n"
        stats_text += "\n"
    if top_authors:
        stats_text += "🏆 Топ авторов:\n"
        for i, (author, stats) in enumerate(top_authors, 1):
            medals = ['🥇', '🥈', '🥉']
            medal = medals[i-1] if i <= 3 else '🏅'
            stats_text += f"{medal} {author}: {stats['snippets']} snippets ({stats['uses']} views)\n"
    is_admin = admin_manager.is_admin(update.effective_user.id)
    await update_or_send_message(update, context, stats_text, reply_markup=get_main_keyboard(is_admin))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ℹ Помощь по боту:\n\n"
        "📥 Добавить - Добавить новый сниппет (требуется модерация)\n"
        "🔍 Поиск - Найти код по названию\n"
        "📖 Все - Просмотреть все сниппеты\n"
        "🗑️ Удалить - Удалить свой сниппет\n"
        "⭐ Избранное - Ваша коллекция\n"
        "🎯 Фильтры - Поиск по языкам и тегам\n"
        "👤 Профиль - Ваша статистика и достижения\n"
        "📊 Статистика - Общая статистика бота\n"
    )
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if is_admin:
        help_text += (
            "\n📋 Администраторские команды:\n"
            "🔧 Кнопка 'Админ-меню' - Открыть админ-меню\n"
            "/pending - Просмотр сниппетов на модерации\n"
            "/addadmin <user_id> - Добавить администратора\n"
        )
    help_text += (
        f"\n📚 Поддерживаемые языки: {' '.join([f'{emoji} {lang}' for lang, emoji in LANGUAGES.items()])}\n"
        f"📌 Доступные теги: {', '.join(CATEGORIES)}\n\n"
        "🏆 Система уровней:\n"
    )
    for level, info in USER_LEVELS.items():
        help_text += f"{info['emoji']} {info['name']} - {info['min_snippets']}+ сниппетов, {info['min_uses']}+ просмотров\n"
    await update_or_send_message(update, context, help_text, reply_markup=get_main_keyboard(is_admin))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_admin = admin_manager.is_admin(update.effective_user.id)
    await update_or_send_message(update, context, "Действие отменено!", reply_markup=get_main_keyboard(is_admin))
    context.user_data.clear()
    return ConversationHandler.END

async def add_snippet_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    user_data = user_manager.get_user(user_id)
    today = datetime.now().date().isoformat()
    if 'last_submission_date' in user_data and user_data['last_submission_date'] == today:
        if user_data.get('submissions_today', 0) >= 5:
            is_admin = admin_manager.is_admin(update.effective_user.id)
            await update_or_send_message(
                update,
                context,
                text="❌ Вы достигли лимита отправки сниппетов на сегодня (5)!",
                reply_markup=get_main_keyboard(is_admin)
            )
            return ConversationHandler.END
        user_data['submissions_today'] += 1
    else:
        user_data['last_submission_date'] = today
        user_data['submissions_today'] = 1
    await user_manager.save_users()
    
    try:
        if update.message:
            await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    context.user_data['snippet_start_time'] = datetime.now()
    await update_or_send_message(
        update,
        context,
        "📖 Введите название для нового сниппета:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Отмена")]], resize_keyboard=True)
    )
    return GET_NAME

async def get_snippet_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message:
            await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    context.user_data['snippet_name'] = update.message.text
    lang_buttons = []
    for lang, emoji in LANGUAGES.items():
        lang_buttons.append(KeyboardButton(f"{emoji} {lang}"))
    keyboard = [lang_buttons[:2], lang_buttons[2:], [KeyboardButton("↩️ Отмена")]]
    await update_or_send_message(
        update,
        context,
        "🔍 Выберите язык программирования:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return GET_LANGUAGE

async def get_snippet_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message:
            await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    selected_language = None
    for lang, emoji in LANGUAGES.items():
        if update.message.text == f"{emoji} {lang}":
            selected_language = lang
            break
    if selected_language:
        context.user_data['language'] = selected_language
        tag_buttons = []
        for tag in CATEGORIES:
            tag_buttons.append(KeyboardButton(f"🗂️ {tag}"))
        keyboard = [
            tag_buttons,
            [KeyboardButton("⏩ Пропустить")],
            [KeyboardButton("↩️ Отмена")]
        ]
        await update_or_send_message(
            update,
            context,
            text="🗂️ Выберите категорию/тег (или пропустите):",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return GET_TAGS
    else:
        lang_buttons = []
        for lang, emoji in LANGUAGES.items():
            lang_buttons.append(KeyboardButton(f"{emoji} {lang}"))
        keyboard = [lang_buttons[:2], lang_buttons[2:], [KeyboardButton("↩️ Отмена")]]
        await update_or_send_message(
            update,
            context,
            text="❌ Пожалуйста, выберите один из поддерживаемых языков.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return GET_LANGUAGE

async def get_snippet_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message:
            await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    if update.message.text == "⏩ Пропустить":
        context.user_data['tags'] = []
    else:
        selected_tag = None
        for tag in CATEGORIES:
            if update.message.text == f"🗂️ {tag}":
                selected_tag = tag
                break
        if selected_tag:
            context.user_data['tags'] = [selected_tag]
        else:
            context.user_data['tags'] = []
    await update_or_send_message(
        update,
        context,
        f"💾 Введите код для сниппета '{context.user_data['snippet_name']}':\n"
        "(Можно отправить несколько сообщений, завершите кнопкой 'Готово')",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("✅ Готово")],
            [KeyboardButton("↩️ Отмена")]
        ], resize_keyboard=True)
    )
    return GET_CODE

async def get_snippet_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message:
            await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    if update.message.text == "↩️ Отмена":
        return await cancel(update, context)
    if update.message.text == "✅ Готово":
        return await done_adding_code(update, context)
    if 'code' not in context.user_data:
        context.user_data['code'] = update.message.text
    else:
        context.user_data['code'] += "\n" + update.message.text
    if len(context.user_data['code']) > MAX_CODE_LENGTH:
        await update_or_send_message(
            update,
            context,
            text="❌ Код слишком длинный! Максимум 4000 символов.",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("✅ Готово")],
                [KeyboardButton("↩️ Отмена")]
            ], resize_keyboard=True)
        )
        return GET_CODE
    return GET_CODE

async def done_adding_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        snippet_name = context.user_data.get('snippet_name')
        code = context.user_data.get('code')
        language = context.user_data.get('language')
        tags = context.user_data.get('tags', [])
        author = update.effective_user.username or update.effective_user.full_name or f"User {update.effective_user.id}"
        author_id = update.effective_user.id
        start_time = context.user_data.get('snippet_start_time')

        if not all([snippet_name, code, language, author_id]):
            is_admin = admin_manager.is_admin(update.effective_user.id)
            await update_or_send_message(
                update,
                context,
                "❌ Ошибка: неполные данные для сниппета!",
                reply_markup=get_main_keyboard(is_admin)
            )
            context.user_data.clear()
            return ConversationHandler.END

        if await storage.add_pending_snippet(snippet_name, code, language, author, author_id, tags):
            is_admin = admin_manager.is_admin(update.effective_user.id)
            await update_or_send_message(
                update,
                context,
                f"✅ Сниппет '{snippet_name}' отправлен на модерацию!\n"
                f"{LANGUAGES.get(language, '📜')} Язык: {language}\n"
                f"🗂️ Теги: {', '.join(tags) if tags else 'Без тегов'}\n"
                f"👤 Автор: {author}",
                reply_markup=get_main_keyboard(is_admin)
            )
            try:
                await notify_admins(context, snippet_name, storage.pending_snippets[snippet_name])
            except Exception as e:
                logger.error(f"Ошибка в notify_admins: {e}", exc_info=True)

            # Проверка достижений
            user = user_manager.get_user(author_id)
            current_time = datetime.now()
            current_hour = current_time.hour
            new_achievements = []

            if start_time:
                elapsed_time = (current_time - start_time).total_seconds()
                if elapsed_time < 60 and 'speed_coder' not in user['achievements']:
                    user['achievements'].append('speed_coder')
                    new_achievements.append('speed_coder')
            if 5 <= current_hour < 7 and 'early_bird' not in user['achievements']:
                user['achievements'].append('early_bird')
                new_achievements.append('early_bird')
            if (23 <= current_hour or current_hour < 3) and 'night_owl' not in user['achievements']:
                user['achievements'].append('night_owl')
                new_achievements.append('night_owl')
            if len(code) > 1000 and 'code_crafter' not in user['achievements']:
                user['achievements'].append('code_crafter')
                new_achievements.append('code_crafter')

            if new_achievements:
                try:
                    await user_manager.save_users()
                    for achievement in new_achievements:
                        ach_info = ACHIEVEMENTS.get(achievement, {'emoji': '❓', 'name': 'Неизвестно', 'description': ''})
                        await update_or_send_message(
                            update,
                            context,
                            f"🎉 Новое достижение!\n{ach_info['emoji']} {ach_info['name']}\n{ach_info['description']}"
                        )
                except Exception as e:
                    logger.error(f"Ошибка при сохранении или отправке достижений: {e}", exc_info=True)

            if random.random() < MEME_PROBABILITY:
                try:
                    await send_random_meme(update, context, author_id)
                except Exception as e:
                    logger.error(f"Ошибка в send_random_meme: {e}", exc_info=True)
        else:
            is_admin = admin_manager.is_admin(update.effective_user.id)
            await update_or_send_message(
                update,
                context,
                f"❌ Ошибка: Сниппет с именем '{snippet_name}' уже существует или превышены лимиты длины!",
                reply_markup=get_main_keyboard(is_admin)
            )
    except Exception as e:
        logger.error(f"Ошибка в done_adding_code: {e}", exc_info=True)
        is_admin = admin_manager.is_admin(update.effective_user.id)
        await update_or_send_message(
            update,
            context,
            "❌ Произошла ошибка при добавлении сниппета. Попробуйте снова.",
            reply_markup=get_main_keyboard(is_admin)
        )
    finally:
        context.user_data.clear()
    return ConversationHandler.END

async def review_snippet(update: Update, context: ContextTypes.DEFAULT_TYPE, snippet_id):
    if not admin_manager.is_admin(update.effective_user.id):
        await update.callback_query.answer("❌ Только администраторы могут выполнять это действие!")
        return
    snippet_name = context.user_data.get('snippets_map', {}).get(f'pending_snippet_{snippet_id}')
    if not snippet_name or snippet_name not in storage.pending_snippets:
        await update.callback_query.answer("❌ Сниппет не найден!")
        return
    snippet = storage.pending_snippets[snippet_name]
    language_emoji = LANGUAGES.get(snippet['language'], '📜')
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{snippet_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{snippet_id}")
        ],
        [InlineKeyboardButton("🔍 Назад", callback_data="back_to_pending")]
    ])
    await update_or_send_message(
        update,
        context,
        f"📋 Сниппет на модерации: '{snippet_name}'\n"
        f"{language_emoji} Язык: {snippet['language']}\n"
        f"👤 Автор: {snippet['author']}\n"
        f"🗂️ Теги: {', '.join(snippet['tags']) if snippet['tags'] else 'Без тегов'}\n"
        f"📜 Код:\n```{snippet['language'].lower()}\n{snippet['code']}\n```",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def approve_snippet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    snippet_id = query.data.replace("approve_", "")
    snippet_name = context.user_data.get('snippets_map', {}).get(f'pending_snippet_{snippet_id}')
    if not snippet_name or not admin_manager.is_admin(update.effective_user.id):
        await query.answer("❌ Ошибка или недостаточно прав!")
        return
    snippet = storage.pending_snippets.get(snippet_name)
    if not snippet:
        await query.answer("❌ Сниппет не найден!")
        return
    user = user_manager.get_user(update.effective_user.id)
    user['approved_snippets'] = user.get('approved_snippets', 0) + 1
    if await storage.approve_snippet(snippet_name):
        logger.info(f"Сниппет '{snippet_name}' одобрен администратором {update.effective_user.id}")
        user_id = snippet['user_id']
        user_author = user_manager.get_user(user_id)
        if 'reliable_coder' not in user_author['achievements']:
            user_author['achievements'].append('reliable_coder')
            await user_manager.save_users()
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Новое достижение!\n{ACHIEVEMENTS['reliable_coder']['emoji']} {ACHIEVEMENTS['reliable_coder']['name']}\n"
                     f"{ACHIEVEMENTS['reliable_coder']['description']}"
            )
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Ваш сниппет '{snippet_name}' одобрен и добавлен в библиотеку!"
        )
        await update_or_send_message(update, context, f"✅ Сниппет '{snippet_name}' одобрен!")
        snippets_count, uses_count = storage.get_user_snippets_stats(snippet['author'])
        level_up, new_achievements = await user_manager.update_user_stats(user_id, snippets_count, uses_count)
        if new_achievements:
            for achievement in new_achievements:
                ach_info = ACHIEVEMENTS[achievement]
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Новое достижение!\n{ach_info['emoji']} {ach_info['name']}\n{ach_info['description']}"
                )
        if level_up:
            user_data = user_manager.get_user(user_id)
            level_info = USER_LEVELS[user_data['level']]
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎊 Поздравляем! Вы достигли уровня {level_info['emoji']} {level_info['name']}!"
            )
        # Обновление статистики для swift_moderator
        if 'last_moderation_time' not in user:
            user['last_moderation_time'] = datetime.now().isoformat()
            user['moderations_in_hour'] = 0
        last_time = datetime.fromisoformat(user['last_moderation_time'])
        current_time = datetime.now()
        if (current_time - last_time).total_seconds() <= 3600:
            user['moderations_in_hour'] = user.get('moderations_in_hour', 0) + 1
        else:
            user['moderations_in_hour'] = 1
            user['last_moderation_time'] = current_time.isoformat()
        if user['moderations_in_hour'] >= 10 and 'swift_moderator' not in user['achievements']:
            user['achievements'].append('swift_moderator')
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🎉 Новое достижение!\n{ACHIEVEMENTS['swift_moderator']['emoji']} {ACHIEVEMENTS['swift_moderator']['name']}\n"
                     f"{ACHIEVEMENTS['swift_moderator']['description']}"
            )
        await user_manager.save_users()
    else:
        await query.answer("❌ Ошибка при одобрении!")

async def reject_snippet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    snippet_id = query.data.replace("reject_", "")
    snippet_name = context.user_data.get('snippets_map', {}).get(f'pending_snippet_{snippet_id}')
    if not snippet_name or not admin_manager.is_admin(update.effective_user.id):
        await query.answer("❌ Ошибка или недостаточно прав!")
        return
    snippet = storage.pending_snippets.get(snippet_name)
    if not snippet:         
        await query.answer("❌ Сниппет не найден!")
        return
    context.user_data['reject_snippet_id'] = snippet_id
    user = user_manager.get_user(update.effective_user.id)
    user['rejected_snippets'] = user.get('rejected_snippets', 0) + 1
    await user_manager.save_users()
    await update_or_send_message(
        update,
        context,
        f"⚠️ Укажите причину отклонения сниппета '{snippet_name}':",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="cancel_reject")]])
    )
    context.user_data['waiting_for_reject_reason'] = True

async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_reject_reason'):
        return
    try:
        if update.message:
            await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    reason = update.message.text
    snippet_id = context.user_data.get('reject_snippet_id')
    snippet_name = context.user_data.get('snippets_map', {}).get(f'pending_snippet_{snippet_id}')
    if not snippet_name or not storage.pending_snippets.get(snippet_name):
        is_admin = admin_manager.is_admin(update.effective_user.id)
        await update_or_send_message(update, context, "❌ Сниппет не найден!", reply_markup=get_main_keyboard(is_admin))
        context.user_data.pop('waiting_for_reject_reason', None)
        context.user_data.pop('reject_snippet_id', None)
        return
    snippet = storage.pending_snippets[snippet_name]
    user = user_manager.get_user(update.effective_user.id)
    if await storage.reject_snippet(snippet_name):
        logger.info(f"Сниппет '{snippet_name}' отклонён администратором {update.effective_user.id} по причине: {reason}")
        await context.bot.send_message(
            chat_id=snippet['user_id'],
            text=f"❌ Ваш сниппет '{snippet_name}' отклонён.\nПричина: {reason}"
        )
        is_admin = admin_manager.is_admin(update.effective_user.id)
        await update_or_send_message(update, context, f"✅ Сниппет '{snippet_name}' отклонён по причине: {reason}", reply_markup=get_main_keyboard(is_admin))
        # Обновление статистики для justice_bringer
        if len(reason) > 50:
            user['detailed_rejections'] = user.get('detailed_rejections', 0) + 1
            if user['detailed_rejections'] >= 25 and 'justice_bringer' not in user['achievements']:
                user['achievements'].append('justice_bringer')
                await user_manager.save_users()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🎉 Новое достижение!\n{ACHIEVEMENTS['justice_bringer']['emoji']} {ACHIEVEMENTS['justice_bringer']['name']}\n"
                         f"{ACHIEVEMENTS['justice_bringer']['description']}"
                )
        # Обновление статистики для swift_moderator
        if 'last_moderation_time' not in user:
            user['last_moderation_time'] = datetime.now().isoformat()
            user['moderations_in_hour'] = 0
        last_time = datetime.fromisoformat(user['last_moderation_time'])
        current_time = datetime.now()
        if (current_time - last_time).total_seconds() <= 3600:
            user['moderations_in_hour'] = user.get('moderations_in_hour', 0) + 1
        else:
            user['moderations_in_hour'] = 1
            user['last_moderation_time'] = current_time.isoformat()
        if user['moderations_in_hour'] >= 10 and 'swift_moderator' not in user['achievements']:
            user['achievements'].append('swift_moderator')
            await user_manager.save_users()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🎉 Новое достижение!\n{ACHIEVEMENTS['swift_moderator']['emoji']} {ACHIEVEMENTS['swift_moderator']['name']}\n"
                     f"{ACHIEVEMENTS['swift_moderator']['description']}"
            )
        await user_manager.save_users()
    else:
        is_admin = admin_manager.is_admin(update.effective_user.id)
        await update_or_send_message(update, context, "❌ Ошибка при отклонении!", reply_markup=get_main_keyboard(is_admin))
    context.user_data.pop('waiting_for_reject_reason', None)
    context.user_data.pop('reject_snippet_id', None)

async def search_snippets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if len(context.args) == 0:
        await update_or_send_message(
            update,
            context,
            "🔍 Введите запрос после команды: /search название_сниппета",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    query = ' '.join(context.args)
    results = storage.search_snippets(query)
    if not results:
        await update_or_send_message(
            update,
            context,
            f"❌ Сниппеты по запросу '{query}' не найдены.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
    for name in results.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data['snippets_map'][snippet_id] = name
    context.user_data['navigation'] = context.user_data.get('navigation', {})
    context.user_data['navigation']['current_list'] = 'search'
    context.user_data['navigation']['current_snippets'] = results
    context.user_data['navigation']['current_page'] = 0
    context.user_data['navigation']['search_query'] = query
    keyboard, total_pages = create_snippets_keyboard(results, 0, "show", "_search")
    await update_or_send_message(
        update,
        context,
        f"🔍 Найдено {len(results)} сниппетов по запросу '{query}':",
        reply_markup=keyboard
    )
    if random.random() < MEME_PROBABILITY:
        await send_random_meme(update, context, update.effective_user.id)

async def show_all_snippets(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if not storage.snippets:
        await update_or_send_message(
            update,
            context,
            "📖 Библиотека пуста. Добавьте первый сниппет!",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
    for name in storage.snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data['snippets_map'][snippet_id] = name
    context.user_data['navigation'] = context.user_data.get('navigation', {})
    context.user_data['navigation']['current_list'] = 'all'
    context.user_data['navigation']['current_snippets'] = storage.snippets
    context.user_data['navigation']['current_page'] = page
    keyboard, total_pages = create_snippets_keyboard(storage.snippets, page, "show")
    text = f"📖 Все сниппеты (стр. {page+1}/{total_pages}):"
    await update_or_send_message(update, context, text, reply_markup=keyboard)

async def show_snippet(update: Update, context: ContextTypes.DEFAULT_TYPE, snippet_id):
    snippets_map = context.user_data.get('snippets_map', {})
    snippet_name = snippets_map.get(snippet_id)
    if not snippet_name:
        await update.callback_query.answer("❌ Сниппет не найден")
        return
    snippet = await storage.get_snippet(snippet_name)
    if not snippet:
        await update.callback_query.answer("❌ Сниппет не найден")
        return
    language_emoji = LANGUAGES.get(snippet['language'], '📜')
    is_author = snippet['author'] == (update.effective_user.username or update.effective_user.full_name or f"User {update.effective_user.id}")
    snippet_text = (
        f"{language_emoji} **{snippet_name}**\n"
        f"👤 Автор: {snippet['author']}\n"
        f"📅 Дата: {snippet.get('created_date', 'Неизвестно')[:10]}\n"
        f"👍 Просмотров: {snippet['uses']}\n"
    )
    if snippet.get('tags'):
        snippet_text += f"🗂️ Теги: {', '.join(snippet['tags'])}\n"
    snippet_text += f"\n\n```{snippet['language'].lower()}\n{snippet['code']}\n```"
    keyboard = get_quick_actions_keyboard(snippet_name, update.effective_user.id, is_author)
    await update_or_send_message(
        update,
        context,
        snippet_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def delete_snippet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    author = update.effective_user.username or update.effective_user.full_name
    user_snippets = {name: data for name, data in storage.snippets.items() if data['author'] == author}
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if not user_snippets:
        await update_or_send_message(
            update,
            context,
            "❌ У вас нет сниппетов для удаления.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
    for name in user_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data['snippets_map'][snippet_id] = name
    keyboard, total_pages = create_snippets_keyboard(user_snippets, 0, "delete")
    await update_or_send_message(
        update,
        context,
        f"🗑 Выберите сниппет для удаления (всего: {len(user_snippets)}):",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        await update.message.delete()
    except TelegramError as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if context.user_data.get('waiting_for_reject_reason'):
        return await handle_reject_reason(update, context)
    if text == "📥 Добавить":
        return await add_snippet_start(update, context)
    elif text == "📋 Все":
        return await show_all_snippets(update, context)
    elif text == "🔍 Поиск":
        await update_or_send_message(
            update,
            context,
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
    elif text == "🔧 Админ-меню" and is_admin:
        await admin_menu(update, context)
    elif text == "📂 FTP BackUp":
        try:
            await update_or_send_message(
                update,
                context,
                "📂 **FTP BackUp**\n"
                "🔗 Ссылка: [https://github.com/H4ckMM3/FTP-Backup](https://github.com/H4ckMM3/FTP-Backup.git)\n"
                "📝 Описание: FTP Backup — мощный плагин для Sublime Text, предназначенный для автоматического создания резервных копий ваших файлов.",
                reply_markup=get_main_keyboard(is_admin),
                parse_mode='Markdown'
            )
        except TelegramError as e:
            logger.error(f"Ошибка при отправке сообщения FTP BackUp: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Ошибка при отправке информации о FTP BackUp. Попробуйте позже."
            )
    elif text == "↩️ Главное меню":
        await update_or_send_message(update, context, "🏠 Главное меню", reply_markup=get_main_keyboard(is_admin))
        context.user_data.clear()
    elif context.user_data.get('waiting_for_search'):
        results = storage.search_snippets(text)
        context.user_data.pop('waiting_for_search', None)
        if not results:
            await update_or_send_message(
                update,
                context,
                f"❌ Сниппеты по запросу '{text}' не найдены.",
                reply_markup=get_main_keyboard(is_admin)
            )
            return
        context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
        for name in results.keys():
            snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
            context.user_data['snippets_map'][snippet_id] = name
        context.user_data['navigation'] = context.user_data.get('navigation', {})
        context.user_data['navigation']['current_list'] = 'search'
        context.user_data['navigation']['current_snippets'] = results
        context.user_data['navigation']['current_page'] = 0
        context.user_data['navigation']['search_query'] = text
        keyboard, total_pages = create_snippets_keyboard(results, 0, "show", "_search")
        await update_or_send_message(
            update,
            context,
            f"🔍 Найдено {len(results)} сниппетов по запросу '{text}':",
            reply_markup=keyboard
        )
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
    elif text.startswith("🏗️ WordPress"):
        filtered = storage.filter_by_tag("WordPress")
        await show_filtered_results(update, context, filtered, "тегу WordPress")
    elif text.startswith("🏗️ Bitrix"):
        filtered = storage.filter_by_tag("Bitrix")
        await show_filtered_results(update, context, filtered, "тегу Bitrix")
    elif text.startswith("🏗️ Общее"):
        filtered = storage.filter_by_tag("Общее")
        await show_filtered_results(update, context, filtered, "тегу Общее")
    else:
        await update_or_send_message(
            update,
            context,
            "❓ Не понимаю команду. Используйте меню ниже:",
            reply_markup=get_main_keyboard(is_admin)
        )

async def show_filtered_results(update: Update, context: ContextTypes.DEFAULT_TYPE, filtered_snippets, filter_name):
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if not filtered_snippets:
        await update_or_send_message(
            update,
            context,
            f"❌ Сниппеты по фильтру {filter_name} не найдены.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    context.user_data['snippets_map'] = context.user_data.get('snippets_map', {})
    for name in filtered_snippets.keys():
        snippet_id = hashlib.md5(name.encode()).hexdigest()[:16]
        context.user_data['snippets_map'][snippet_id] = name
    context.user_data['navigation'] = context.user_data.get('navigation', {})
    context.user_data['navigation']['current_list'] = 'filtered'
    context.user_data['navigation']['current_snippets'] = filtered_snippets
    context.user_data['navigation']['current_page'] = 0
    context.user_data['navigation']['filter_name'] = filter_name
    keyboard, total_pages = create_snippets_keyboard(filtered_snippets, 0, "show", "_filtered")
    await update_or_send_message(
        update,
        context,
        f"🎯 Найдено {len(filtered_snippets)} сниппетов по {filter_name}:",
        reply_markup=keyboard
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.debug(f"Обработка callback_data: {data}")
    is_admin = admin_manager.is_admin(update.effective_user.id)
    if data.startswith("show_"):
        snippet_id = data.replace("show_", "").replace("_search", "").replace("_fav", "").replace("_filtered", "")
        await show_snippet(update, context, snippet_id)
    elif data.startswith("copy_"):
        snippet_id = data.replace("copy_", "")
        snippet_name = context.user_data.get('snippets_map', {}).get(snippet_id)
        if snippet_name and snippet_name in storage.snippets:
            snippet = storage.snippets[snippet_name]
            await query.answer("📖 Код скопирован!")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"```{snippet['language'].lower()}\n{snippet['code']}\n```",
                parse_mode='Markdown'
            )
            if random.random() < 0.3:
                await send_random_meme(update, context, query.from_user.id)
    elif data.startswith("fav_"):
        snippet_id = data.replace("fav_", "")
        snippet_name = context.user_data.get('snippets_map', {}).get(snippet_id)
        if snippet_name:
            if await user_manager.add_to_favorites(query.from_user.id, snippet_name):
                await query.answer("❤️ Добавлено в избранное!")
                snippet = storage.snippets.get(snippet_name)
                if snippet:
                    is_author = snippet['author'] == (query.from_user.username or query.from_user.full_name)
                    keyboard = get_quick_actions_keyboard(snippet_name, query.from_user.id, is_author)
                    await update_or_send_message(update, context, query.message.text, reply_markup=keyboard, parse_mode='Markdown')
            else:
                await query.answer("⚠️ Уже в избранном!")
    elif data.startswith("unfav_"):
        snippet_id = data.replace("unfav_", "")
        snippet_name = context.user_data.get('snippets_map', {}).get(snippet_id)
        if snippet_name:
            if await user_manager.remove_from_favorites(query.from_user.id, snippet_name):
                await query.answer("💔 Удалено из избранного!")
                snippet = storage.snippets.get(snippet_name)
                if snippet:
                    is_author = snippet['author'] == (query.from_user.username or query.from_user.full_name)
                    keyboard = get_quick_actions_keyboard(snippet_name, query.from_user.id, is_author)
                    await update_or_send_message(update, context, query.message.text, reply_markup=keyboard, parse_mode='Markdown')
            else:
                await query.answer("⚠️ Не было в избранном!")
    elif data.startswith("delete_"):
        snippet_id = data.replace("delete_", "")
        snippet_name = context.user_data.get('snippets_map', {}).get(snippet_id)
        if snippet_name:
            snippet = storage.snippets.get(snippet_name)
            if snippet and snippet['author'] == (query.from_user.username or query.from_user.full_name):
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{snippet_id}"),
                        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete")
                    ]
                ])
                await update_or_send_message(
                    update,
                    context,
                    f"⚠️ Вы уверены, что хотите удалить '{snippet_name}'?\n"
                    f"Это действие нельзя отменить!",
                    reply_markup=keyboard
                )
            else:
                await query.answer("❌ Вы можете удалять только свои сниппеты!")
    elif data.startswith("confirm_delete_"):
        snippet_id = data.replace("confirm_delete_", "")
        snippet_name = context.user_data.get('snippets_map', {}).get(snippet_id)
        if snippet_name:
            if await storage.delete_snippet(snippet_name):
                logger.info(f"Сниппет '{snippet_name}' удалён пользователем {query.from_user.id}")
                for user_id, user_data in user_manager.users.items():
                    if snippet_name in user_data['favorites']:
                        user_data['favorites'].remove(snippet_name)
                await user_manager.save_users()
                await update_or_send_message(update, context, f"✅ Сниппет '{snippet_name}' удалён!")
                context.user_data['snippets_map'].pop(snippet_id, None)
                if random.random() < 0.3:
                    await send_random_meme(update, context, query.from_user.id)
            else:
                await query.answer("❌ Ошибка при удалении!")
    elif data == "cancel_delete":
        await update_or_send_message(update, context, "❌ Удаление отменено")
    elif data == "back_to_list":
        navigation = context.user_data.get('navigation', {})
        current_list = navigation.get('current_list')
        page = navigation.get('current_page', 0)
        if current_list == 'all':
            await show_all_snippets(update, context, page)
        elif current_list == 'favorites':
            await show_favorites(update, context, page)
        elif current_list == 'search':
            search_query = navigation.get('search_query', '')
            results = navigation.get('current_snippets', {})
            keyboard, total_pages = create_snippets_keyboard(results, page, "show", "_search")
            await update_or_send_message(
                update,
                context,
                f"🔍 Найдено {len(results)} сниппетов по запросу '{search_query}' (стр. {page+1}/{total_pages}):",
                reply_markup=keyboard
            )
        elif current_list == 'filtered':
            filter_name = navigation.get('filter_name', 'фильтру')
            results = navigation.get('current_snippets', {})
            keyboard, total_pages = create_snippets_keyboard(results, page, "show", "_filtered")
            await update_or_send_message(
                update,
                context,
                f"🎯 Найдено {len(results)} сниппетов по {filter_name} (стр. {page+1}/{total_pages}):",
                reply_markup=keyboard
            )
        else:
            await show_all_snippets(update, context, 0)
    elif data.startswith("page_"):
        parts = data.split("_")
        if len(parts) >= 3:
            action = parts[1]
            page = int(parts[2])
            navigation = context.user_data.get('navigation', {})
            results = navigation.get('current_snippets', {})
            if not results:
                await update_or_send_message(update, context, "❌ Сниппеты не найдены")
                return
            if "_fav" in data or navigation.get('current_list') == 'favorites':
                await show_favorites(update, context, page)
            elif "_search" in data or navigation.get('current_list') == 'search':
                search_query = navigation.get('search_query', '')
                navigation['current_page'] = page
                keyboard, total_pages = create_snippets_keyboard(results, page, "show", "_search")
                await update_or_send_message(
                    update,
                    context,
                    f"🔍 Найдено {len(results)} сниппетов по запросу '{search_query}' (стр. {page+1}/{total_pages}):",
                    reply_markup=keyboard
                )
            elif "_filtered" in data or navigation.get('current_list') == 'filtered':
                filter_name = navigation.get('filter_name', 'фильтру')
                navigation['current_page'] = page
                keyboard, total_pages = create_snippets_keyboard(results, page, "show", "_filtered")
                await update_or_send_message(
                    update,
                    context,
                    f"🎯 Найдено {len(results)} сниппетов по {filter_name} (стр. {page+1}/{total_pages}):",
                    reply_markup=keyboard
                )
            elif action == "pending":
                navigation['current_page'] = page
                keyboard, total_pages = get_pending_snippets_keyboard(page)
                await update_or_send_message(
                    update,
                    context,
                    f"🖋 Сниппеты на модерации (стр. {page+1}/{total_pages}):",
                    reply_markup=keyboard
                )
            else:
                await show_all_snippets(update, context, page)
    elif data.startswith("review_"):
        snippet_id = data.replace("review_", "")
        await review_snippet(update, context, snippet_id)
    elif data.startswith("approve_"):
        await approve_snippet(update, context)
    elif data.startswith("reject_"):
        await reject_snippet(update, context)
    elif data == "cancel_reject":
        await update_or_send_message(update, context, "❌ Отклонение отменено")
        context.user_data.pop('waiting_for_reject_reason', None)
        context.user_data.pop('reject_snippet_id', None)
    elif data == "back_to_pending":
        keyboard, total_pages = get_pending_snippets_keyboard(page=0)
        await update_or_send_message(update, context, f"🖋 Сниппеты на модерации (стр. 1/{total_pages}):", reply_markup=keyboard)
    elif data == "admin_pending":
        await pending_snippets(update, context)
    elif data == "admin_menu":
        await admin_menu(update, context)
    elif data == "back_to_admin":
        await update_or_send_message(
            update,
            context,
            "🔧 Админ-меню:\nВыберите действие:",
            reply_markup=get_admin_keyboard()
        )
    elif data == "back_to_main":
        await update_or_send_message(
            update,
            context,
            "🏠 Главное меню",
            reply_markup=get_main_keyboard(is_admin)
        )
        context.user_data.pop('last_message_id', None)
    elif data == "admin_users":
        await list_users(update, context)
    elif data.startswith("page_users_"):
        page = int(data.replace("page_users_", ""))
        await list_users(update, context, page)
    elif data.startswith("view_user_"):
        user_id = data.replace("view_user_", "")
        await show_user_profile(update, context, user_id)
    elif data == "back_to_users":
        navigation = context.user_data.get('navigation', {})
        page = navigation.get('current_page', 0)
        await list_users(update, context, page)
    elif data == "noop":
        pass
    else:
        logger.warning(f"Неизвестный callback_data: {data}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=True)
    if update and (update.message or update.callback_query):
        try:
            is_admin = admin_manager.is_admin(update.effective_user.id)
            await update_or_send_message(
                update,
                context,
                "❌ Произошла ошибка. Пожалуйста, попробуйте снова.",
                reply_markup=get_main_keyboard(is_admin)
            )
            context.user_data.clear()
        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}", exc_info=True)

def main():
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("📥 Добавить"), add_snippet_start)],
            states={
                GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_name)],
                GET_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_language)],
                GET_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_tags)],
                GET_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_snippet_code)],
            },
            fallbacks=[MessageHandler(filters.Regex("↩️ Отмена"), cancel)],
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("admin", admin_menu))
        application.add_handler(CommandHandler("addadmin", add_admin))
        application.add_handler(CommandHandler("pending", pending_snippets))
        application.add_handler(CommandHandler("search", search_snippets))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(conv_handler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(handle_callback))
        application.add_error_handler(error_handler)

        # Асинхронная инициализация перед запуском
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(
            storage.initialize(),
            user_manager.initialize(),
            admin_manager.initialize()
        ))

        print("🚀 Бот запущен!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    import asyncio
    main()