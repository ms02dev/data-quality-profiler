-- Пересоздаём таблицы при повторном запуске seed вручную
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

-- Таблица customers — грязные данные
CREATE TABLE customers (
    id        bigint,
    name      text,
    email     text,
    age       integer,
    country   text,
    created_at timestamp
);

INSERT INTO customers
SELECT
    gs AS id,

    -- 5% строк без имени
    CASE WHEN random() < 0.05 THEN NULL
         ELSE 'User_' || gs::text
    END AS name,

    -- 8% строк без email
    CASE WHEN random() < 0.08 THEN NULL
         ELSE 'user' || floor(random() * 100000)::text || '@example.com'
    END AS email,

    -- 3% строк без возраста
    CASE WHEN random() < 0.03 THEN NULL
         ELSE (18 + floor(random() * 60))::integer
    END AS age,

    -- NULL встроен в массив — это ~17% NULL в country
    (ARRAY['RU', 'US', 'DE', 'FR', 'NL', NULL])[floor(random() * 6 + 1)] AS country,

    now() - (random() * interval '730 days') AS created_at

FROM generate_series(1, 100000) gs;

-- Добавляем ~2% дублей (строки полностью совпадают)
INSERT INTO customers
SELECT * FROM customers ORDER BY random() LIMIT 2000;


-- Таблица orders
CREATE TABLE orders (
    order_id    bigint,
    customer_id bigint,
    product_name text,
    amount      numeric,
    status      text,
    ordered_at  timestamp
);

INSERT INTO orders
SELECT
    gs AS order_id,
    floor(random() * 100000 + 1)::bigint AS customer_id,

    CASE WHEN random() < 0.02 THEN NULL
         ELSE (ARRAY['Laptop','Phone','Tablet','Monitor','Keyboard'])[floor(random() * 5 + 1)]
    END AS product_name,

    CASE WHEN random() < 0.04 THEN NULL
         ELSE round((random() * 5000 + 10)::numeric, 2)
    END AS amount,

    (ARRAY['pending','shipped','delivered','cancelled'])[floor(random() * 4 + 1)] AS status,
    now() - (random() * interval '365 days') AS ordered_at

FROM generate_series(1, 50000) gs;

ANALYZE customers;
ANALYZE orders;


-- Big table для тестирования ветки pg_stats
-- На M5 вставка 10 млн строк займёт ~1-2 минуты при первом запуске
DROP TABLE IF EXISTS big_table;
CREATE TABLE big_table (
    id         bigint,
    category   text,
    amount     numeric,
    created_at timestamp,
    email      text
);

INSERT INTO big_table
SELECT
    gs,
    CASE WHEN random() < 0.1 THEN NULL
         ELSE (ARRAY['a','b','c','d'])[floor(random()*4+1)]
    END,
    CASE WHEN random() < 0.05 THEN NULL
         ELSE round((random()*1000)::numeric, 2)
    END,
    now() - (random() * interval '365 days'),
    CASE WHEN random() < 0.02 THEN NULL
         ELSE 'user' || floor(random()*1000000)::text || '@test.com'
    END
FROM generate_series(1, 10000000) gs;

-- Добавляем 100к дублей
INSERT INTO big_table
SELECT * FROM big_table ORDER BY random() LIMIT 100000;

-- КРИТИЧЕСКИ ВАЖНО!
ANALYZE big_table;