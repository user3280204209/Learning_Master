-- 学习多智能体系统 · 完整建表脚本（MySQL 8.0）
-- 新环境：mysql -u root -proot123456 < schema.sql
-- 已有环境：python init_db.py（会做非破坏性增量迁移并写入演示数据）

CREATE DATABASE IF NOT EXISTS learning
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_general_ci;

USE learning;

-- 1. 学生
CREATE TABLE IF NOT EXISTS student (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(50)  NOT NULL,
    major      VARCHAR(100),
    age        INT          DEFAULT 0,
    goal       VARCHAR(300),
    email      VARCHAR(120),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 画像维度（长表：一个维度一行，新增维度无需改表）
CREATE TABLE IF NOT EXISTS profile_dimension (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT          NOT NULL,
    dimension  VARCHAR(50)  NOT NULL,
    value      TEXT,
    confidence FLOAT        DEFAULT 0.5,
    source     VARCHAR(20)  DEFAULT 'dialogue',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_student_dimension (student_id, dimension),
    CONSTRAINT fk_profile_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 对话记录（session_id 把多轮对话串起来）
CREATE TABLE IF NOT EXISTS dialogue (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id INT         NOT NULL,
    session_id VARCHAR(64),
    role       VARCHAR(20) NOT NULL,
    content    TEXT,
    meta       JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_dialogue_student (student_id, created_at),
    CONSTRAINT fk_dialogue_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 学习资源（6 种类型用 type 区分；大文件只存路径）
CREATE TABLE IF NOT EXISTS resource (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    student_id    INT          NOT NULL,
    task_id       VARCHAR(64),
    type          VARCHAR(30)  NOT NULL,
    title         VARCHAR(200),
    summary       TEXT,
    content       LONGTEXT,
    file_path     VARCHAR(500),
    meta          JSON,
    agent         VARCHAR(50),
    status        VARCHAR(20)  DEFAULT 'ready',
    quality_score FLOAT        DEFAULT 0,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_resource_student_type (student_id, type),
    KEY idx_resource_task (task_id),
    CONSTRAINT fk_resource_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 学习路径（步骤 JSON 存，整条重算方便）
CREATE TABLE IF NOT EXISTS learning_path (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT          NOT NULL,
    title      VARCHAR(200),
    rationale  TEXT,
    steps      LONGTEXT,
    status     VARCHAR(20)  DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_path_student (student_id, created_at),
    CONSTRAINT fk_path_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 学习行为 / 评估原始数据
CREATE TABLE IF NOT EXISTS learning_record (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    resource_id  INT,
    action       VARCHAR(20),
    score        FLOAT,
    duration_sec INT DEFAULT 0,
    detail       TEXT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_record_student (student_id, created_at),
    CONSTRAINT fk_record_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE,
    CONSTRAINT fk_record_resource FOREIGN KEY (resource_id)
        REFERENCES resource (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 智能体运行追踪（可观测性：每个 Agent 一次运行一行）
CREATE TABLE IF NOT EXISTS agent_run (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id        VARCHAR(64) NOT NULL,
    student_id     INT         NOT NULL,
    agent          VARCHAR(50) NOT NULL,
    role           VARCHAR(50),
    status         VARCHAR(20) NOT NULL,
    model          VARCHAR(60),
    input_summary  TEXT,
    output_summary TEXT,
    error          TEXT,
    duration_ms    INT DEFAULT 0,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_agent_task (task_id),
    KEY idx_agent_student (student_id, created_at),
    CONSTRAINT fk_agent_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 学习效果评估报告
CREATE TABLE IF NOT EXISTS assessment_report (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    student_id    INT NOT NULL,
    overall_score FLOAT,
    dimensions    JSON,
    strengths     TEXT,
    weaknesses    TEXT,
    suggestions   TEXT,
    summary       TEXT,
    source        VARCHAR(20) DEFAULT 'agent',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_assessment_student (student_id, created_at),
    CONSTRAINT fk_assessment_student FOREIGN KEY (student_id)
        REFERENCES student (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
