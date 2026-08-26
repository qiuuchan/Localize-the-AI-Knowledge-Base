# KB-AI v1.4.0 · 多阶段构建范式样本
# 目的:为未来 backend / frontend 容器化预留可复用的多阶段模板
# 现状:dify-db-init 仅需 alpine + sqlite;builder 与 runtime 共享 base,多阶段用作范式示例
# 边界:runtime 阶段仍需 `apk add sqlite`(为共享库 libreadline.so.8 等);
#       builder 阶段预装用于验证 cache 与多阶段语法,生产环境可保留或删除均可

# === Stage 1: builder ===
# 在独立阶段装 sqlite,验证 apk cache + layer 复用
FROM alpine:3.19 AS builder
RUN apk add --no-cache sqlite

# === Stage 2: runtime ===
# 装 sqlite 同时安装二进制 + 共享库(libreadline.so.8 / libsqlite3.so.0 / libncurses 等);
# COPY --from=builder /usr/bin/sqlite3 单独用会因缺共享库而运行失败(post-review fix)
FROM alpine:3.19
RUN apk add --no-cache sqlite
