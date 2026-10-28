FROM jenkins/inbound-agent:jdk21
USER root
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY engine-standin.sh /opt/engine-standin.sh
RUN mkdir -p '/home/jenkins/agent workspace' '/opt/synthetic data/campaigns' \
    '/opt/synthetic data/vulnerabilities' '/opt/synthetic reports' && \
    chmod 755 /opt/engine-standin.sh && \
    chown -R jenkins:jenkins '/home/jenkins/agent workspace' '/opt/synthetic data' '/opt/synthetic reports'
USER jenkins
