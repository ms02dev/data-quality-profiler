# Changelog

Формат по [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Версии по [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]
- Dockerfile копирует папку `tests` в образ для запуска pytest внутри контейнера

### Added
- Централизованная конфигурация через Pydantic Settings: валидация при старте (`Field(ge=, le=)`), `SecretStr` для пароля БД