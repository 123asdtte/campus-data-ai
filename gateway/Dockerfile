# PR-B 网关镜像：运行宿主机构建好的 RuoYi 精简后端
#
# 构建前置（JDK 21 + Maven，首次需下载依赖）：
#   cd gateway
#   mvn -B -DskipTests -pl ruoyi-admin -am package
#
# 说明：沿用 POC 的“宿主构建、容器运行”方式，避免在容器内重复下载 Maven 依赖；
#       如需完全自包含，可改为 maven:3.9-eclipse-temurin-21 多阶段构建。
FROM eclipse-temurin:21-jre

# 以非 root 账号运行；/app 需可写日志
RUN groupadd -r ruoyi \
    && useradd -r -g ruoyi -s /usr/sbin/nologin ruoyi

WORKDIR /app
COPY ruoyi-admin/target/ruoyi-admin.jar /app/app.jar
RUN chown -R ruoyi:ruoyi /app
USER ruoyi

EXPOSE 9180
ENV TZ=Asia/Shanghai
ENTRYPOINT ["java", "-Xms256m", "-Xmx1024m", "-jar", "/app/app.jar"]
