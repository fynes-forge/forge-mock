"""Shared SQL DDL fixtures for tests."""

SIMPLE_DDL = """
CREATE TABLE users (
    user_id     BIGINT       NOT NULL,
    username    VARCHAR(50)  NOT NULL,
    email       VARCHAR(255) NOT NULL,
    age         INT,
    score       DECIMAL(10, 2),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL,
    PRIMARY KEY (user_id)
);
"""

FK_DDL = """
CREATE TABLE departments (
    dept_id   INT          NOT NULL,
    dept_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (dept_id)
);

CREATE TABLE employees (
    emp_id    BIGINT       NOT NULL,
    dept_id   INT          NOT NULL REFERENCES departments(dept_id),
    full_name VARCHAR(255) NOT NULL,
    salary    DECIMAL(12, 2),
    hired_on  DATE,
    PRIMARY KEY (emp_id)
);
"""

MULTI_TYPE_DDL = """
CREATE TABLE events (
    event_id    UUID         NOT NULL,
    event_name  TEXT,
    event_date  DATE,
    event_time  TIME,
    event_ts    TIMESTAMP,
    payload     JSON,
    is_public   BOOLEAN,
    amount      FLOAT,
    big_num     BIGINT,
    small_num   SMALLINT,
    PRIMARY KEY (event_id)
);
"""

CIRCULAR_WARNING_DDL = """
CREATE TABLE a (
    id INT NOT NULL PRIMARY KEY,
    name VARCHAR(50)
);
"""
