# Letta Code в Yorimiyu

Источник: https://github.com/letta-ai/letta-code (Apache-2.0).

## Перенос исходников
Workflow `.github/workflows/import-letta-code.yml` клонирует исходный репозиторий и создаёт отдельный Pull Request с полным снимком в `vendor/letta-code/`, сохраняя `LICENSE` и `UPSTREAM_COMMIT`. Workflow не исполняет исходный код Letta.

Сначала необходимо проверить созданный PR и слить его в `main`. Наличие workflow **не означает**, что файлы уже перенесены.

## Архитектура
- `vendor/graphiti/` — Graphiti, графовая память.
- `vendor/letta-code/` — независимый исходный код Letta Code после импорта.
- `web/` — отдельная чёрно-золотая панель Yorimiyu.

Letta Code и Graphiti **не подключены друг к другу**. Запуск Letta требует отдельной установки и настройки LLM/провайдера. Не храните ключи в репозитории и не выставляйте API без авторизации.
