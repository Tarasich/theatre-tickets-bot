# Бот для билетов в театр «Свободное пространство» (Орёл)

Раз в несколько минут проверяет [страницу театра на quicktickets.ru](https://quicktickets.ru/orel-teatr-svobodnoe-prostranstvo)
и присылает уведомление в Telegram, когда на сеанс, где мест не было, появляются билеты
(или выкладывают новый сеанс с билетами). В уведомлении есть название, дата и время,
минимальная цена и ссылка на покупку. Покупать билеты бот не умеет и не пытается — только сообщает.

## Как это работает

- За одну проверку бот делает один запрос к странице театра. Сеансы без мест помечены там
  классом `quick-tickets-session-option--sold` (надпись «(мест нет)»).
- Если билеты появились, бот дополнительно открывает страницу этого сеанса, чтобы узнать цену.
- Состояние хранится в `state.json`, поэтому после перезапуска повторных уведомлений не будет.
- Если на странице не нашлось ни одного сеанса (скорее всего, сайт поменял вёрстку),
  бот присылает предупреждение, не чаще раза в сутки. Чинить парсер нужно в `theatre_bot/parser.py`.

## 1. Создать бота в Telegram

1. Напишите [@BotFather](https://t.me/BotFather) команду `/newbot`, придумайте имя и логин.
2. BotFather пришлёт токен вида `123456789:AA...` — это `TELEGRAM_BOT_TOKEN`.

## 2. Узнать свой chat_id

Запустите бота с пустым `TELEGRAM_CHAT_ID` и отправьте ему `/start` — он ответит вашим chat_id.
Впишите его в `.env` и перезапустите бота: после этого бот будет отвечать только вам.

## 3. Запуск на Windows

```powershell
cd путь\к\папке\бота
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
notepad .env
.venv\Scripts\python -m theatre_bot
```

Бот работает, пока открыто окно и включён компьютер. Чтобы он запускался сам,
добавьте последнюю команду в Планировщик заданий Windows (триггер «При входе в систему»).

## 4. Запуск на VPS (Linux, systemd)

```bash
sudo useradd -r -s /usr/sbin/nologin theatrebot
sudo mkdir -p /opt/theatre-bot && sudo cp -r theatre_bot requirements.txt .env /opt/theatre-bot/
cd /opt/theatre-bot
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo chown -R theatrebot: /opt/theatre-bot
sudo cp theatre-bot.service /etc/systemd/system/
sudo systemctl enable --now theatre-bot
journalctl -u theatre-bot -f
```

## 5. Запуск в Docker

```bash
docker build -t theatre-bot .
docker run -d --name theatre-bot --restart unless-stopped --env-file .env -v theatre-bot-data:/app/data theatre-bot
```

## 6. Запуск в GitHub Actions (без своего сервера и ПК)

Workflow [.github/workflows/check-tickets.yml](.github/workflows/check-tickets.yml) запускает
`python -m theatre_bot --once`. Каждый запуск проверяет сайт, рассылает уведомления
и отвечает на команды, пришедшие с прошлого запуска. Состояние (`state.json`) хранится
в кэше Actions между запусками.

Запускает workflow внешний сервис [cron-job.org](https://cron-job.org) раз в 5 минут через
API GitHub. Встроенное расписание GitHub (`schedule`) не используется: для небольших
репозиториев оно срабатывает раз в несколько часов, а через 60 дней без коммитов
GitHub отключает такой workflow целиком.

Команды в Telegram работают, но ответ приходит только при следующем запуске — в пределах
5 минут.

**Настройка**

1. Создайте на github.com репозиторий. Лучше **публичный**: для публичных репозиториев
   минуты Actions бесплатны без ограничений. Код будет виден всем, но токен и chat_id
   хранятся в секретах и не видны никому, а `.env` и `state.json` в репозиторий не попадают
   (они в `.gitignore`).
   В приватном репозитории бесплатно 2000 минут в месяц, а каждый запуск считается минимум
   за минуту — тогда запускайте проверку в cron-job.org не чаще раза в 25 минут.
2. Загрузите в репозиторий файлы проекта (всё, кроме `.env`, `.venv`, `state.json`, `bot.log`).
3. В репозитории: **Settings → Secrets and variables → Actions → New repository secret**,
   создайте два секрета: `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.
4. Необязательно: там же на вкладке **Variables** можно задать `WATCH_TITLES`, `DATE_FROM`,
   `DATE_TO`, `FIRST_RUN_SUMMARY`.
5. **Остановите бота на ПК** (и удалите задачу из планировщика, если создавали):
   с одним токеном Telegram отдаёт команды только одной копии.
6. Вкладка **Actions** → «Проверка билетов» → **Run workflow**, чтобы проверить, что всё работает.
7. Создайте токен GitHub для запуска: https://github.com/settings/personal-access-tokens/new →
   Repository access: **Only select repositories** → этот репозиторий;
   Permissions: **Actions: Read and write** (Metadata: Read-only добавится сам).
8. На [cron-job.org](https://cron-job.org) создайте задание:
   - URL: `https://api.github.com/repos/<логин>/<репозиторий>/actions/workflows/check-tickets.yml/dispatches`
   - расписание: каждые 5 минут;
   - Advanced → метод `POST`, заголовки `Authorization: Bearer <токен>` и
     `Accept: application/vnd.github+json`, тело `{"ref":"main"}`;
   - Notifications → уведомлять о сбоях.

   **Test run** должен вернуть код 204.

**Если что-то сломалось.** Если сайт или Telegram недоступны, запуск завершается с ошибкой,
и GitHub присылает письмо на почту аккаунта. Подробности — в логе запуска на вкладке Actions.
Если запуски вообще перестали появляться — смотрите историю задания на cron-job.org:
чаще всего это истёк срок токена (код 401). Создайте новый токен и замените его в задании.

## Команды бота

| Команда | Что делает |
|---|---|
| `/start` | подписаться на уведомления, показать chat_id |
| `/status` | все сеансы и наличие билетов (по последней проверке) |
| `/check` | проверить сайт прямо сейчас (не чаще раза в 2 минуты) |
| `/watch Онегин` | следить только за спектаклями, в названии которых есть «Онегин» (можно несколько) |
| `/unwatch Онегин`, `/unwatch all` | убрать спектакль из списка / снова следить за всеми |

## Настройки (`.env`)

| Параметр | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | токен от BotFather (обязательно) |
| `TELEGRAM_CHAT_ID` | пусто | если задан — бот только для этого чата |
| `CHECK_INTERVAL_MIN` | 5 | интервал проверки, минимум 2; к нему добавляется случайный разброс ±15 % |
| `WATCH_TITLES` | пусто | начальный список спектаклей через запятую; дальше — `/watch`, `/unwatch` |
| `DATE_FROM`, `DATE_TO` | пусто | диапазон дат сеансов, `ГГГГ-ММ-ДД` |
| `FIRST_RUN_SUMMARY` | false | при первом запуске прислать сводку вместо молчаливого запоминания |

## Тесты

```bash
.venv\Scripts\python -m pytest   # Windows
.venv/bin/python -m pytest       # Linux
```

Тесты парсера идут на сохранённых страницах сайта из `tests/fixtures`. Если сайт поменяет
вёрстку, сохраните свежую страницу театра в `tests/fixtures/theatre.html`, поправьте
селекторы в `theatre_bot/parser.py` и ожидаемые значения в `tests/test_parser.py`.
