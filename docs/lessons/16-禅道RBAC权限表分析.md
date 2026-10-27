# 第 16 课：禅道 RBAC 权限表分析（分块三第 1 条）

> **日期**：2026-10-26
> **目标**：分析禅道（ZenTao）角色权限控制的后台表结构、设置逻辑、存储内容

---

## 一、先讲通用的 RBAC（这是核心，任何系统都一样）

**RBAC = Role-Based Access Control（基于角色的访问控制）**。

核心思想一句话：**权限不直接给用户，而是给"角色"，用户再挂到角色上。**

```
用户(user) ──多对多── 角色/组(group) ──多对多── 权限(priv)
```

为什么要中间加一层"角色"？因为用户会变、权限会变，但**角色是稳定的**。新来个测试，不用一个个配权限，把他挂到"测试"角色就完事。

> **关键点**：几乎所有权限系统都是 RBAC 这套。你以后项目里做权限，也是这三层 + 两张关联表。

---

## 二、禅道的 RBAC 表结构（`zt_` 前缀）

禅道的权限模型完全遵循 RBAC，核心是这 5 张表：

| 表 | 作用 | 属于哪一层 |
|---|---|---|
| `zt_user` | 用户（账号、密码、姓名、部门） | 用户 |
| `zt_group` | 用户组/角色（管理员、研发、测试…） | 角色 |
| `zt_usergroup` | **用户 ↔ 组** 关联（多对多中间表） | 关联 |
| `zt_grouppriv` | **组 ↔ 权限** 关联（组有哪些权限） | 关联 |
| `zt_module` | 功能模块（产品、项目、Bug、测试…） | 权限载体 |

### 关系图

```
zt_user ──< zt_usergroup >── zt_group ──< zt_grouppriv >── (module + method)
 (用户)     (谁属于哪个组)      (角色)      (组能做什么)
```

**禅道权限的粒度是「模块 + 方法」**：一个权限点 = 某个模块下的某个动作。比如：
- `product` 模块的 `index` 方法 = 查看产品列表
- `bug` 模块的 `create` 方法 = 新建 Bug

这就是 `zt_grouppriv` 里存 `module` 和 `method` 两个字段的原因。

---

## 三、表的存储内容（示例数据）

### `zt_group`（角色）

| id | name | role |
|---|---|---|
| 1 | 管理员 | admin |
| 2 | 研发 | dev |
| 3 | 测试 | qa |

### `zt_user`（用户）

| id | account | realname | dept |
|---|---|---|---|
| 1 | admin | 管理员 | 总部 |
| 2 | zhangsan | 张三 | 研发部 |

### `zt_usergroup`（用户属于哪个组）

| account | group |
|---|---|
| admin | 1 |
| zhangsan | 2 |

→ 含义：admin 属于「管理员」组，张三属于「研发」组。

### `zt_grouppriv`（组有什么权限）

| group | module | method |
|---|---|---|
| 1 | product | index |
| 1 | product | create |
| 2 | bug | index |

→ 含义：管理员组能「查看/新建产品」，研发组能「查看 Bug」。

---

## 四、权限检查的逻辑（怎么判断"你能不能干这件事"）

判断「用户 X 能不能执行 module=M 的 method=H」：

```sql
-- 查 X 所属的组里，有没有哪个组拥有 (M, H) 这个权限点
select count(*)
from zt_usergroup ug
join zt_grouppriv gp on ug.group = gp.group
where ug.account = 'X'
  and gp.module = 'M'
  and gp.method = 'H';
```

**返回 >0 就有权限，=0 就没权限。** 就这么简单——两层关联表 join 一下。

> **关键点**：这就是 RBAC 的本质——**鉴权 = 顺着"用户→组→权限"这条链查一次**。你理解了这一条 SQL，就理解了所有 RBAC 系统。

---

## 五、你课后要做的操作（网络好时）

> **2026-10-27 更新**：本节步骤已经实际完成，安装与验证记录见文末「七、实际安装与验证记录」。

禅道下载走官网 `www.zentao.net`，步骤留给你：

1. 官网下 **Windows 一键安装包**（开源版，内置 Apache+MySQL+PHP）
2. 解压到无中文无空格的目录（如 `D:\ZenTao`）
3. 运行 `ZenTao.exe` 启动，浏览器开 `http://127.0.0.1:80`，默认 **admin / 123456**
4. **建一个自定义角色**：组织 → 权限 → 维护用户组，新建"测试组"，勾选几个权限点
5. 建一个用户，挂到这个组
6. **打开禅道的 MySQL**（一键包内置），查 `zt_usergroup` 和 `zt_grouppriv`，看你刚才勾的权限是怎么存的

> 做完第 6 步，你就能亲眼验证本课讲的表结构——**看到"勾选权限"这个动作，底层就是往 `zt_grouppriv` 插了一行 `(group, module, method)`**。

---

## 六、我的理解（你自己填）

- 我最大的收获：
- 还没弄明白的：
- 踩的坑：

---

## 七、实际安装与验证记录（2026-10-27）

### 1. 安装

- 安装包：`zentao-22.6-amd64-setup.exe`（约 173 MB），来自 `https://dl.zentao.net/zentao/22.6/`。
- 安装路径：`C:\ZenTao`。
- 一键包内置：Apache 2.4.25、PHP 7.4.30、MariaDB 10.4.14、Redis 6.2.16。
- 控制面板启动后显示 Apache / MySQL「未安装」，是因为没有走它的「安装服务」流程；改为直接以进程方式启动，效果相同。

### 2. 端口规划（重点：避免和课程项目冲突）

| 服务 | 端口 | 说明 |
|---|---|---|
| Apache（禅道 Web） | 80 | 原 80 空闲 |
| 禅道自带 MySQL | **3308** | 课程项目 MySQL 占 3306，故改到 3308 |
| 课程项目 MySQL 主/从 | 3306 / 3307 | 不变 |

同步改了三处，缺一不可：

1. `C:\ZenTao\zbox\config.yml` → `service.mysql.port: 3308`、`autoPorts: [3308, 3999]`
2. `C:\ZenTao\bin\mysql\my.ini` → 两处 `port = 3308`
3. `C:\ZenTao\app\zentao\config\mysql.php` → `$config->db->port = '3308';`

启动 / 停止脚本（仓库外）：

```
C:\Users\lijun\tools\zentao-start.bat
C:\Users\lijun\tools\zentao-stop.bat
```

访问入口：`http://127.0.0.1/`（欢迎页）或 `http://127.0.0.1/zentao/`（登录页）。

### 3. 账号

| 账号 | 密码 | 说明 |
|---|---|---|
| admin | `Zentao@12345` | 默认 123456 太弱，首次登录被强制改密；`zt_user.password` 存的是 `md5(明文)` |
| zhangsan（张三） | `User@12345` | 新建的测试用户，role=qa，挂在「测试组」 |
| 禅道数据库 root | 123456 | 只在本机监听 |

### 4. 建角色、建用户

- 组织 → 权限 → 用户组 → 新建「测试组」（`zt_group.id = 24`）。
- 在「分配权限」里勾选：
  - `bug`：browse、create、resolve
  - `testcase`：browse、create
  - `testtask`：browse
- 保存后提示「权限及依赖权限保存成功」——`zt_grouppriv` 实际写入 10 行，多出来的 `bug-view`、`testcase-view`、`qa-index`、`index-index` 是系统自动补的**依赖权限**。
- 组织 → 用户 → 添加用户：账号 `zhangsan`、姓名 `张三`、职位 `qa`、所属组选「测试组」。
- `zt_usergroup` 实际写入一行：`(zhangsan, 24)`。

### 5. 用 SQL 验证（就是第四节课那条 join）

```sql
select gp.module, gp.method
from zt_usergroup ug
join zt_grouppriv gp on ug.group = gp.group
where ug.account = 'zhangsan'
order by gp.module, gp.method;
```

实际结果：

```
bug        browse
bug        create
bug        resolve
bug        view
index      index
qa         index
testcase   browse
testcase   create
testcase   view
testtask   browse
```

**结论：页面上「勾选权限」这个动作，底层就是往 `zt_grouppriv` 插入 `(group, module, method)` 行；鉴权就是顺着 `zt_usergroup → zt_grouppriv` join 一次。**

### 6. 实际访问验证权限

用 zhangsan 登录后：

| 访问地址 | 结果 |
|---|---|
| `/zentao/bug-browse.html` | 200，正常打开 Bug 页 |
| `/zentao/product-create.html` | 被重定向到 `user-deny-product-create`，回到首页 |
| `/zentao/company-browse.html` | 被重定向到 `user-deny-company-browse`，回到首页 |

有权限 → 正常渲染；无权限 → 重定向到 `user-deny-<模块>-<方法>`。这就是第四节课那条 join 在实际系统里的落点。

### 7. 本次踩的坑（HTTP 调试向，可跳过）

- 禅道开启了 `filterCSRF`：POST 必须带 `Referer`，且要匹配 `http://127.0.0.1`，否则 `$_POST` 会被整个清空（表现为「XX 不能为空」）。
- 改密 / 建用户表单里的 `verifyRand` 在每次 GET 时都会重新生成；必须「先 GET 拿 rand，立刻 POST」，中间再访问一次页面 rand 就变了。
- 字段加密规则：
  - 新密码：`password1 = md5(新明文) + rand`，服务端只取前 32 位；同时传 `passwordPlain` 供服务端重算强度。
  - 校验管理员身份（原密码 / verifyPassword）：`md5(管理员密码哈希 + rand)`。
- 中文参数用 `curl --data-urlencode` 在 Windows 下会被终端编码影响；改用 UTF-8 文件 + `--data-binary @file` 才稳定。

---

## 备忘

- RBAC 三层：用户 → 角色 → 权限，中间两张关联表
- 禅道核心权限表：`zt_user` / `zt_group` / `zt_usergroup` / `zt_grouppriv` / `zt_module`
- 禅道权限粒度 = 模块 + 方法（`module` + `method`）
- 鉴权 = 一条 join `zt_usergroup` + `zt_grouppriv` 的 SQL
- 禅道默认 admin/123456，端口 80；官网下载（本机网络暂不可达，课后补）
