sqlite3 database.db

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL,
  role TEXT NOT NULL
);

-- 添加测试用户（密码应加密，这里为简化使用明文）
INSERT INTO users (username, password, role) VALUES ('admin', '123', 'admin');
INSERT INTO users (username, password, role) VALUES ('driver', '123', 'driver');
INSERT INTO users (username, password, role) VALUES ('pass', '123', 'passenger');

CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    role TEXT,
    action TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

SELECT * FROM logs;

CREATE TABLE log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    role TEXT,
    type TEXT,
    action TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

.quit/.exit
