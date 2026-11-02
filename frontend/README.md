# Yorimiyu Visual Studio

Отдельный React-интерфейс для локального проекта. Использует `@xyflow/react` для графа, `echarts` и `echarts-for-react` для статистики, `three`, `@react-three/fiber`, `@react-three/drei` для трёхмерной карты.

На Windows из корня проекта:

```bat
cd frontend
npm.cmd install
npm.cmd run check
npm.cmd run build
```

Сборка создаётся в `web/studio/`, затем запустите `Yorimiyu.bat` и откройте `http://127.0.0.1:<порт>/studio/` (порт показывает BAT). Старый интерфейс сохранён как безопасный резервный вариант. `npm.cmd` используется для обхода ограничения PowerShell на `npm.ps1`. Для разработки Vite proxy настраивается отдельно на актуальный порт локального Python API.

Визуализация использует реальные `/api/agents`, `/api/sqlite-graph/graph`, `/api/chat` и `/api/memories`, а не демонстрационные данные. Все сетевые обращения идут к тому же локальному origin. Не вставляйте ключ Cloud.ru в код React: он хранится только на Python-сервере.
