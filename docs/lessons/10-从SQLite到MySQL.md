# 第 10 课：从 SQLite 换到 MySQL

> **日期**：2026-10-26
> **前置**：第 8 课（with/上下文管理）、第 9 课（任务盘点 + 数据模型设计）
> **目标**：装好 MySQL、物理建表、把后端从 SQLite 切到 MySQL，理解"换数据库要改什么"

---

## 一、这一轮做了什么

1. **装 MySQL**（本机免安装版 8.0.29）：winget 因网络失败 → 华为云镜像下 zip → 解压 → `mysqld --initialize-insecure` 初始化 → 启动 → 设密码 → 配 `my.ini`（utf8mb4）
2. **物理建表**：`backend/schema.sql` 里 6 张表，`mysql < schema.sql` 建库建表
3. **换驱动**：`db.py` 从 `sqlite3` 改成 `pymysql`，`main.py` 跟着改
4. **验证**：英文 + 中文都能写入 MySQL 并读回

---

## 二、核心：SQLite → MySQL，代码到底改了哪 4 处

这是**面试必问**的点——"从 SQLite 换到 MySQL 要改什么"。记住这 4 处：

### ① 建表方式变了：从"代码建表"到"脚本建表"

```python
# 旧：启动时用代码建表
db.init_db()   # 每次启动都执行 create table if not exists

# 新：删掉 init_db()，表用 schema.sql 手动建好
```

**为什么变**：SQLite 时代表只有一张，代码里建表方便。现在 6 张表、带外键，用 `schema.sql`（建模工具导出）建表更清晰，也满足分块三.3"用建模工具建表"。**建表从"程序启动的副作用"变成了"独立的交付物"。**

### ② 连接方式变了：从"连文件"到"连服务"

```python
# 旧：SQLite 是一个文件
sqlite3.connect("student.db")

# 新：MySQL 是一个服务，要地址 + 账号 + 密码
pymysql.connect(host="127.0.0.1", port=3306, user="root",
                password="root123456", database="learning", charset="utf8mb4")
```

**关键认知**：SQLite 是"文件数据库"，MySQL 是"服务数据库"（客户端通过网络连到服务器进程）。这就是为什么 MySQL 需要"启动服务"、需要"端口 3306"。

### ③ SQL 占位符变了：`?` → `%s`

```python
# SQLite
cur.execute("select ... where id = ?", (student_id,))

# MySQL（pymysql）
cur.execute("select ... where id = %s", (student_id,))
```

**为什么不一样**：占位符是**每个驱动自己定的语法**，不是 SQL 标准的一部分。sqlite3 用 `?`，pymysql 用 `%s`（注意：无论值是 int 还是 str，都写 `%s`，它**不是** Python 的 `%` 字符串格式化，是 pymysql 的占位符）。

> ⚠️ 最容易犯的错：把 `%s` 当成 Python 的 `%` 格式化，写成 `"... where id = %d" % student_id`。
> 那就又回到 SQL 注入的老路了。占位符的第二参数**永远**是单独传给 `execute` 的，不是拼进字符串。

### ④ 取值方式变了：`row[0]` → `row["name"]`

```python
# 旧：fetchone() 返回 tuple，按位置取
row[0], row[1], row[2]

# 新：用了 DictCursor，返回 dict，按列名取
row["id"], row["name"], row["major"]
```

**为什么改**：第 7 课就提过"select 列顺序一改，`row[0]` 就崩"。pymysql 提供了 `cursorclass=DictCursor`，让每行变成 dict，按**列名**取值。列名是稳定的，列顺序不是——这是更稳的写法。

---

## 三、调试案例：中文乱码怎么定位（值得你记住这个方法）

现象：POST 写入中文成功，GET 读出来是 `����`。

**不要瞎猜，用 hex 一步步缩小范围：**

| 检查 | 命令/做法 | 结果 |
|---|---|---|
| 存储层对不对 | `select hex(name) from student` | `E5BCA0E4B889` ✅（"张三"的 UTF-8） |
| mysql 命令行读 | `--default-character-set=utf8mb4` | 显示"张三" ✅ |
| Python 读到啥 | `name.encode('utf-8').hex()` | `e5bca0e4b889` ✅ |

**结论**：三层都是对的，只有**终端显示**乱码——Windows 的 Git Bash 终端用 GBK 解码 UTF-8 字节，导致 `print` 中文变 `����`。数据本身没坏。

> **方法论**：遇到"乱码"，第一步永远是问"**数据到底坏没坏**"——用 hex 看原始字节。字节对，就是显示问题（换终端编码 / 前端用 UTF-8）；字节错，才是数据问题（查连接字符集、存储字符集）。**别一上来就到处改配置。**

---

## 四、环境备忘（以后你自己能开）

| 东西 | 位置 / 命令 |
|---|---|
| MySQL 目录 | `C:\Users\lijun\tools\mysql-8.0.29-winx64` |
| 启动 / 停止 | 双击 `start_mysql.bat` / `stop_mysql.bat` |
| 账号密码 | `root` / `root123456`，端口 3306 |
| 建表脚本 | `backend/schema.sql` |
| 数据库 | `learning`（6 张表） |
| pip 源 | 已设阿里云（`~/.pip` 里） |

> ⚠️ 现在是后台进程跑 MySQL，不是 Windows 服务，重启电脑后要手动 `start_mysql.bat`。做成开机自启服务需要管理员权限，放到分块一.3（服务器/部署）一起做。

---

## 五、我的理解（这一节由你自己填）

- 这节课我最大的收获是：
- 我还没完全弄明白的地方是：
- 我踩到的坑 / 犯的错：

---

## 六、备忘

- 换数据库改 4 处：建表方式 / 连接方式 / 占位符 `?`→`%s` / 取值 `row[0]`→`row["name"]`
- `%s` 是 pymysql 占位符，不是 Python 的 `%` 格式化
- MySQL 是服务数据库（要地址+账号+端口），SQLite 是文件数据库
- 乱码先查 hex，判断"数据坏没坏"，再决定改什么
- 建表用 `schema.sql`，不再用代码里的 `init_db()`
