FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/taq.jar /app/taq.jar
ENTRYPOINT ["sh","-c","exec java $JAVA_OPTS -jar /app/taq.jar"]
