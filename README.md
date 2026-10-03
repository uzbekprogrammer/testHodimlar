# Toshkent EM — «Обращение бот» + веб-панель

Telegram-бот обращений сотрудников (aiogram 3) и веб-панель администраторов (FastAPI) в одном процессе и с одной базой SQLite.

## Что есть

**Бот «Обращение бот»** (для сотрудников — на узбекском, для администраторов — на русском):
сообщение о коррупции (анонимно), личный вопрос, предложение, запись на приём к руководителю, редактирование данных.
Администраторам в меню доступна кнопка **🛠 Панель администратора** (или `/admin`): статистика и мониторинг сроков, обращения
(просмотр, «взять в работу», ответ), приёмы (подтверждение/отклонение), история действий, рассылка и — для суперадмина —
управление администраторами (добавить по Telegram ID / пересланному сообщению, сменить роль, отключить, удалить, выдать доступ на сайт).

**Сайт Toshkent EM** (`http://127.0.0.1:8000`): вход по логину/паролю → обзор (KPI, график, типы, live-обновление), обращения
(поиск, фильтры, вложения, ответ в Telegram, статусы, CSV), приём руководителя, сотрудники, **мониторинг** (статус бота, SLA, исполнители,
активность по часам, отделы, просрочки), **история действий** (бот + сайт, фильтры, CSV), рассылка, **администраторы**, профиль (смена пароля, сессии).
Светлая/тёмная тема, адаптив под телефон.

**Роли:** суперадмин (мониторинг и управление; текст обращений скрыт — прежняя политика конфиденциальности, включается `SUPERADMIN_SEE_APPEAL_TEXT=1`),
руководитель и юрист (обращения и ответы; решение по приёму — только руководитель), секретарь (только подтверждённые приёмы).

## Безопасность и скорость

- Токен бота — только в `.env` (файл в `.gitignore`), не в коде. Пароли — scrypt; сессии на сервере (в cookie только случайный токен, хранится его хэш), HttpOnly + SameSite=Strict, тайм-аут простоя 8 ч / жизни 24 ч.
- CSRF-токены на всех POST, блокировка подбора паролей (по IP и логину), строгий CSP (без inline-скриптов/стилей), X-Frame-Options, nosniff, HSTS за HTTPS.
- Все SQL-запросы параметризованы, сортировки — по белому списку; экспорт CSV защищён от формул; вложения отдаются только как attachment (кроме фото).
- Пользовательский текст экранируется перед отправкой в Telegram (раньше ломал разметку); антифлуд в боте; защита от двойного подтверждения приёма и от двойной записи на одно время.
- Нельзя удалить/отключить/понизить последнего суперадмина. Каждое действие (бот и сайт) пишется в историю.
- Скорость: одно постоянное соединение SQLite с WAL, индексы, кэш ролей в памяти, кэш статистики (5–30 с), gzip, кэш статических файлов, параллельные уведомления и рассылка с ограничением скорости.

## O'rnatish

1. Python 3.10+ o'rnatilgan bo'lishi kerak.
2. Kerakli kutubxonalarni o'rnating:
   ```bash
   pip install -r requirements.txt
   ```
3. `.env` faylida `BOT_TOKEN=...` ni to'ldiring (@BotFather). Boshqa sozlamalar (`WEB_HOST`, `WEB_PORT`, `WEB_SECURE_COOKIES`, `TRUST_PROXY`,
   `WEB_ADMIN_USER`, `WEB_ADMIN_PASSWORD`, `SUPERADMIN_SEE_APPEAL_TEXT`) ham `.env` da.
4. `config.py` dagi `SUPERADMIN_IDS`, `DIRECTOR_ID`, `LAWYER_ID`, `SECRETARY_ID` faqat **birinchi ishga tushirishda** bazaga ko'chiriladi;
   keyin adminlar bot paneli yoki sayt orqali boshqariladi.

5. Botni va saytni ishga tushiring (bitta buyruq):
   ```bash
   python main.py
   ```
   Birinchi ishga tushirishda konsolda superadmin uchun sayt logini (`admin`) va **bir martalik parol** chiqadi (yoki `WEB_ADMIN_PASSWORD` ni `.env` da bering).
   Internetga chiqarishda sayt oldiga HTTPS reverse-proxy (nginx/Caddy) qo'ying va `.env` da `WEB_SECURE_COOKIES=1`, `TRUST_PROXY=1` qiling.

## Admin buyruqlari

- `/admin` — admin paneli; `/broadcast` — barcha xodimlarga xabar (barcha admin turlari).
- `/cleardb` — **faqat superadmin** uchun. Ma'lumotlar bazasidagi barcha foydalanuvchi, murojaat va qabul yozuvlarini butunlay o'chiradi (tasdiqlash so'raladi, qaytarib bo'lmaydi).
- Har bir murojaat ostida chiqadigan **"💬 Javob yozish"** tugmasi orqali xodimga javob yozish mumkin (korrupsiya, shaxsiy va taklif murojaatlariga faqat direktor yoki yurist javob bera oladi).

## Loyiha tuzilishi

```
xodimlar_bot/
├── main.py                  # Botni ishga tushirish nuqtasi
├── config.py                # Token va admin ID'lar
├── requirements.txt
├── database/
│   ├── db.py                 # Jadvallarni yaratish (SQLite)
│   └── models.py              # CRUD funksiyalar
├── keyboards/
│   ├── reply.py               # Oddiy klaviaturalar (menyu, bekor qilish)
│   └── inline.py               # Inline klaviaturalar (sana/vaqt, admin tugmalari)
├── handlers/
│   ├── start.py               # /start va umumiy bekor qilish
│   ├── corruption.py          # Korrupsiya bo'limi
│   ├── personal.py            # Shaxsiy masalalar bo'limi
│   ├── reception.py           # Direktor qabuliga yozilish
│   └── admin.py                # Javob yozish, broadcast
└── utils/
    ├── states.py                # FSM holatlari
    ├── roles.py                 # Admin rollarini tekshirish
    ├── working_days.py          # Ish kunlari / vaqt slotlari hisoblash
    └── notifications.py          # Superadminlarga avtomatik xabar
```

## Ma'lumotlar bazasi (SQLite, `database/bot.db`)

- **users** — ro'yxatdan o'tgan barcha xodimlar (shaxsiy masala yoki qabulga yozilish orqali)
- **appeals** — korrupsiya va shaxsiy murojaatlar, holati va admin javoblari bilan
- **appointments** — direktor qabuliga yozilish so'rovlari, holati va sana/vaqti bilan

## Keyingi qadamlar (tavsiya)

- Botni doimiy ishlaydigan serverga (VPS) joylashtirish, masalan `systemd` yoki `screen`/`tmux` orqali.
- Katta yuklamalar uchun `aiogram` FSM storage'ni `MemoryStorage` o'rniga `RedisStorage` ga o'zgartirish (bot qayta ishga tushganda holatlar saqlanib qolishi uchun).
- Admin panelga statistik hisobot (nechta murojaat, o'rtacha javob vaqti) qo'shish.
