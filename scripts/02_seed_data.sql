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