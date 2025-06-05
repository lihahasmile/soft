sqlite3 database.db
.quit/.exit

## 登录注册的用户表

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL,
  role TEXT NOT NULL
);

-- 添加测试用户
INSERT INTO users (username, password, role) VALUES ('admin', '123', 'admin');
INSERT INTO users (username, password, role) VALUES ('driver', '123', 'driver');
INSERT INTO users (username, password, role) VALUES ('pass', '123', 'passenger');

## 交互日志表

CREATE TABLE log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT
    role TEXT,
    type TEXT,
    action TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

## 习惯记录表

CREATE TABLE habit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    temperature int,
    music int,
    media int
);
