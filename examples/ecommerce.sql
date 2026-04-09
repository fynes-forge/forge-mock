-- forge-mock example schema: e-commerce platform
-- Run: forge generate examples/ecommerce.sql --rows 1000 --config examples/ecommerce_config.yaml

CREATE TABLE customers (
    customer_id   BIGINT        NOT NULL,
    first_name    VARCHAR(50)   NOT NULL,
    last_name     VARCHAR(50)   NOT NULL,
    email         VARCHAR(255)  NOT NULL,
    phone         VARCHAR(20),
    created_at    TIMESTAMP     NOT NULL,
    is_verified   BOOLEAN       NOT NULL DEFAULT FALSE,
    PRIMARY KEY (customer_id)
);

CREATE TABLE categories (
    category_id   INT           NOT NULL,
    category_name VARCHAR(100)  NOT NULL,
    description   TEXT,
    PRIMARY KEY (category_id)
);

CREATE TABLE products (
    product_id    BIGINT        NOT NULL,
    category_id   INT           NOT NULL REFERENCES categories(category_id),
    product_name  VARCHAR(255)  NOT NULL,
    sku           VARCHAR(50)   NOT NULL,
    price         DECIMAL(10,2) NOT NULL,
    stock_qty     INT           NOT NULL DEFAULT 0,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP     NOT NULL,
    PRIMARY KEY (product_id)
);

CREATE TABLE orders (
    order_id      BIGINT        NOT NULL,
    customer_id   BIGINT        NOT NULL REFERENCES customers(customer_id),
    status        VARCHAR(20)   NOT NULL,
    total_amount  DECIMAL(12,2) NOT NULL,
    order_date    TIMESTAMP     NOT NULL,
    shipped_date  TIMESTAMP,
    notes         TEXT,
    PRIMARY KEY (order_id)
);

CREATE TABLE order_items (
    item_id       BIGINT        NOT NULL,
    order_id      BIGINT        NOT NULL REFERENCES orders(order_id),
    product_id    BIGINT        NOT NULL REFERENCES products(product_id),
    quantity      INT           NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (item_id)
);
