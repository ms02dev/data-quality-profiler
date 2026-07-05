-- Таблицы для хранения снэпшотов качества данных

CREATE TABLE IF NOT EXISTS data_quality_column_report (
    id            serial PRIMARY KEY,
    snapshot_date timestamp NOT NULL DEFAULT now(),
    table_name    text NOT NULL,
    column_name   text NOT NULL,
    data_type     text NOT NULL,
    null_count    bigint,
    null_pct      numeric,
    distinct_count bigint,
    min_value     text,
    max_value     text,
    avg_value     numeric
);

CREATE TABLE IF NOT EXISTS data_quality_table_report (
    id                  serial PRIMARY KEY,
    snapshot_date       timestamp NOT NULL DEFAULT now(),
    table_name          text NOT NULL,
    row_count           bigint,
    duplicate_row_count bigint
);