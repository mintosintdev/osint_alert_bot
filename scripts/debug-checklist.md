# Border Sentinel — Debug Checklist

## "Sidecar not found"

```bash
# 1. Дізнайся свій target triple
rustc -Vv | grep host
# Приклад: x86_64-unknown-linux-gnu

# 2. Перевір що бінарник названий ПРАВИЛЬНО
ls -la backend/dist/
# Має бути: backend-x86_64-unknown-linux-gnu
# НЕ просто: backend

# 3. Якщо назва неправильна — перейменуй
TARGET=$(rustc -Vv | grep host | cut -d' ' -f2)
cp backend/dist/backend "backend/dist/backend-$TARGET"

# 4. Перевір що шлях в tauri.conf.json правильний
# "externalBin": ["../backend/dist/backend"]
# (без target triple — Tauri додає сам)
```

## "Permission denied"

```bash
# Зроби бінарник виконуваним
chmod +x backend/dist/backend-x86_64-unknown-linux-gnu

# Перевір що він взагалі запускається
./backend/dist/backend-x86_64-unknown-linux-gnu
# Має стартувати FastAPI на порту 8000
```

## "webkit2gtk not found" при cargo tauri dev

```bash
sudo pacman -S webkit2gtk-4.1 javascriptcoregtk-4.1
```

## "APPINDICATOR" помилка (трей не працює)

```bash
sudo pacman -S libayatana-appindicator
# або
sudo pacman -S libappindicator-gtk3
```

## Перевірка що backend відповідає

```bash
# Запусти бекенд вручну
cd backend && python backend.py &

# Перевір
curl http://127.0.0.1:8000/api/stats
# Має повернути JSON зі статистикою
```

## Загальний dev запуск

```bash
# Варіант 1: Все разом (Tauri запускає sidecar автоматично)
npm run dev

# Варіант 2: Debug (backend окремо щоб бачити логи)
cd backend && source .venv/bin/activate && python backend.py &
cd .. && npm run dev

# Release build (.AppImage + .deb)
npm run build
# Результат: src-tauri/target/release/bundle/appimage/
```

## Змінні середовища для dev

```bash
# Якщо Groq ключ не в keychain — встав в .env
echo "GROQ_API_KEY=gsk_xxx" > .env
echo "SEARXNG_URL=http://localhost:8304/search" >> .env
```
