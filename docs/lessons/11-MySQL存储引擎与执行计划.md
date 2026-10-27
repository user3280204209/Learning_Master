# 第 11 课：存储引擎、执行计划与存储结构（分块二）

> **日期**：2026-10-26
> **目标**：把分块二（存储引擎 / 执行计划 / 存储结构 / 参数配置）在真实 MySQL 上演示并记录

---

## 一、存储引擎：InnoDB vs MyISAM

**存储引擎 = 表的存储方式**，是表级属性。`show engines` 看到 InnoDB 标 DEFAULT。

### 实验：事务回滚差异（真实结果）

```sql
create table test_innodb (id int primary key) engine=InnoDB;
create table test_myisam  (id int primary key) engine=MyISAM;
-- 各自：start transaction; insert; rollback;
```

| 表 | 回滚后行数 | 结论 |
|---|---|---|
| InnoDB | **0** | 回滚生效，有事务 |
| MyISAM | **1** | 回滚无效，**数据照样进去了** |

### 实验：外键差异（真实结果）

给 MyISAM 表写 `foreign key`，建表**不报错**，但查 `information_schema` 外键数为 **0**——被**静默忽略**。这是 MyISAM 最危险的地方：你以为有外键约束，实际没有。

### 两类引擎对比

| | InnoDB（默认） | MyISAM（旧） |
|---|---|---|
| 事务 | ✅ | ❌ |
| 外键 | ✅ | ❌（静默忽略） |
| 锁 | 行级锁 | 表级锁 |
| 崩溃恢复 | ✅ redo log | ❌ 要 repair table |
| 适用 | 所有业务表 | 已淘汰 |

> **关键点**：项目业务表必须 InnoDB。你的 `schema.sql` 有 6 个外键，这本身就决定了只能用 InnoDB。

---

## 二、存储引擎参数配置（真实值）

| 参数 | 值 | 含义 |
|---|---|---|
| `default_storage_engine` | InnoDB | 建表不写 engine 时的默认值 |
| `innodb_buffer_pool_size` | 134217728（128M） | InnoDB 内存缓冲池，**最重要的性能参数** |
| `innodb_flush_log_at_trx_commit` | 1 | 每次提交都刷日志，最安全（丢数据风险最低） |
| `innodb_page_size` | 16384（16K） | InnoDB 一页的大小 |
| `innodb_file_per_table` | ON | 每表一个 `.ibd` 文件 |
| `key_buffer_size` | 8388608（8M） | MyISAM 的索引缓冲（InnoDB 用不上） |

**怎么配置**：写进 `my.ini` 的 `[mysqld]` 段，或运行时 `set global 参数=值`。改 `buffer_pool_size` 这种大参数要重启才生效。

> **关键点**：`innodb_flush_log_at_trx_commit=1` 是"要安全还是要快"的经典权衡——1 最安全但慢，0/2 快但可能丢最近几笔。金融类业务必须 1。

---

## 三、执行计划 EXPLAIN

`explain select ...` 告诉你数据库**打算怎么执行**这条查询。重点看三个字段：**type、key、rows**。

### 实验：索引对执行计划的影响（真实结果，1002 行数据）

```sql
-- 无索引时按 name 查
explain select * from student where name = 'stu500';
-- type=ALL  key=NULL  rows=1002   ← 全表扫描

-- 加索引后
create index idx_student_name on student(name);
explain select * from student where name = 'stu500';
-- type=ref  key=idx_student_name  rows=1  ← 索引查询
```

### 关键字段速查

| 字段 | 含义 | 好坏 |
|---|---|---|
| `type` | 访问类型 | `ALL`（全表扫）最差 → `index` → `range` → `ref` → `eq_ref` → `const` 最好 |
| `key` | 实际用的索引 | `NULL` = 没用到索引 |
| `rows` | 预估扫描行数 | 越少越好 |
| `Extra` | 补充信息 | `Using where` / `Using index`（覆盖索引）等 |

> **关键点**：看执行计划就一句话——**`type` 是不是 `ALL`，`rows` 大不大**。`type=ALL` 且 `rows` 上万，基本就是要加索引了。这是定位"慢查询"的第一招。

---

## 四、存储结构

### InnoDB 的物理存储（真实结果）

- 数据目录里，`learning` 库每张表一个 **`.ibd` 文件**（因为 `innodb_file_per_table=ON`）
- `student.ibd` 最大（1002 行），`data_length=81920`（数据 80K）+ `index_length=49152`（索引 48K）——**数据单独占空间，索引也单独占空间**

### 层次结构（概念）

```
表空间 tablespace
 └─ 段 segment（数据段 / 索引段）
     └─ 区 extent（1M = 64 页）
         └─ 页 page（16K，InnoDB 读写的最小单位）
             └─ 行 row
```

### 索引为什么快：B+ 树

InnoDB 用 **B+ 树**组织索引：数据按主键排序存在叶子节点，树高很低（几十万行也就 3 层），所以查一行只需几次磁盘 IO，而不是全表扫几百页。

**关键点**：InnoDB 的**主键索引是"聚簇索引"**——叶子节点直接存整行数据（数据即索引）。所以主键要短、要自增，否则插入会频繁页分裂、树会变胖。

---

## 五、查询计划可视化（分块二第 5 条）

- 命令行 `explain` 就是"计划"的文本版（本课已演示）
- **图形化**：MySQL Workbench 的 **Visual Explain** 能把上面的表画成树状图
- ⚠️ Workbench 还没装（winget 网络失败），装上后用 Reverse/Visual Explain 补这一步

---

## 六、我的理解（你自己填）

- 我最大的收获：
- 还没弄明白的：
- 踩的坑：

---

## 备忘

- 存储引擎是表级属性；业务表用 InnoDB（事务+外键）
- MyISAM 外键会**静默忽略**，回滚**无效**
- 看执行计划：`type` + `key` + `rows`，`type=ALL` 且 rows 大 = 要加索引
- `innodb_buffer_pool_size`、`innodb_flush_log_at_trx_commit` 是 InnoDB 两大关键参数
- 主键要短且自增（聚簇索引 + 页分裂）
