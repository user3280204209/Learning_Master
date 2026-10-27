# 第 13 课：Nginx 反向代理 + 负载均衡（等价替换 Tomcat 集群）

> **日期**：2026-10-26
> **目标**：用 Nginx 把多个 uvicorn 实例做成"集群"，等价替换分块一的 Tomcat 集群

---

## 一、为什么 Python 栈用 Nginx，而不是 Tomcat

分块一第 3 条要求"Tomcat 集群 + Nginx"。但 **Tomcat 是 Java 的 Servlet 容器，跑不了 FastAPI**。Python 栈的等价物是：

| Java 栈 | Python 栈等价物 |
|---|---|
| Tomcat（Servlet 容器） | uvicorn / gunicorn（ASGI 服务器） |
| Tomcat 集群（多实例） | 多个 uvicorn 实例（不同端口） |
| Nginx（反向代理 + 负载均衡） | **Nginx（完全一样）** |

**Nginx 是通用的**——它只是 HTTP 反向代理，不管后端是 Java 还是 Python，照单全收。所以"集群 + Nginx"这部分，Python 栈照做即可。

---

## 二、反向代理 vs 负载均衡

- **反向代理**：客户端只和 Nginx 说话，Nginx 替它去找后端，再原样返回。客户端不知道后端在哪、有几台。
- **负载均衡**：Nginx 背后有**多个**后端，把请求**轮流**分给它们（默认轮询 round-robin）。

```
客户端 → Nginx(8088) → 后端1(uvicorn 8001)
                     → 后端2(uvicorn 8002)   ← 轮流
```

---

## 三、核心配置

```nginx
http {
    # 定义"后端集群"
    upstream backend {
        server 127.0.0.1:8001;
        server 127.0.0.1:8002;
    }

    server {
        listen 8088;
        location / {
            proxy_pass http://backend;          # 转发给集群
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

**关键两行**：
- `upstream` = 声明后端列表，Nginx 默认**轮询**分配
- `proxy_pass http://backend` = 把请求转给这个列表

---

## 四、验证结果（真实）

启动两个 uvicorn（8001、8002）+ Nginx（8088），连续发请求：

- `curl 8088/` 正确返回 FastAPI 的响应（反向代理通）
- 统计两个后端的访问日志：**8001 收到 4 次、8002 收到 4 次**（负载均衡轮询均匀）

---

## 五、踩的坑

**8080 端口被 `java.exe` 占用**（10013 错误）——本机之前就有 Java 服务占着 8080。换 8088 解决。

> 通用教训：Windows 下查端口占用用 `netstat -ano | findstr :端口` 拿到 PID，再 `tasklist | findstr PID` 看是谁。别猜。

---

## 六、我的理解（你自己填）

- 我最大的收获：
- 还没弄明白的：
- 踩的坑：

---

## 备忘

- Nginx 位置：`C:\Users\lijun\tools\nginx-1.24.0`，启动 `nginx.exe`，停止 `nginx.exe -s stop`
- 配置：`conf/nginx.conf`，改完 `nginx.exe -s reload` 热加载（或 `-t` 先测语法）
- Nginx 监听 **8088**，后端 **8001/8002**，默认轮询
- 反向代理：客户端只认 Nginx；负载均衡：多后端轮流接
- 8080 被 java.exe 占、8000 被 C-Lodop 占，8088 是干净的
