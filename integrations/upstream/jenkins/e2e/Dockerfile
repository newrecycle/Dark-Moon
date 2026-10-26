# --- stage 1: install the real darkmoon-ci CLI with its runtime deps (zod) ---
FROM node:20-bookworm-slim AS cli
WORKDIR /opt/darkmoon-ci
COPY darkmoon-client-0.1.0.tgz /tmp/darkmoon-client.tgz
RUN npm init -y >/dev/null 2>&1 && npm install /tmp/darkmoon-client.tgz --omit=dev

# --- stage 2: Jenkins with the produced HPI + real CLI ---
FROM jenkins/jenkins:lts-jdk21
USER root
COPY --from=cli /usr/local/bin/node /usr/local/bin/node
COPY --from=cli /opt/darkmoon-ci /opt/darkmoon-ci
COPY engine-standin.sh /opt/engine-standin.sh
COPY fixtures /opt/darkmoon-fixtures
RUN ln -sf /opt/darkmoon-ci/node_modules/.bin/darkmoon-ci /usr/local/bin/darkmoon-ci && \
    chmod +x /opt/engine-standin.sh && \
    mkdir -p /var/darkmoon/data/campaigns /var/darkmoon/data/vulnerabilities /var/darkmoon/data/reports && \
    chown -R jenkins:jenkins /var/darkmoon /opt/darkmoon-ci && \
    /usr/local/bin/node --version && darkmoon-ci --help >/dev/null 2>&1; echo "cli help exit=$?"
USER jenkins
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
ENV CASC_JENKINS_CONFIG=/var/jenkins_home/casc.yaml
COPY casc.yaml /var/jenkins_home/casc.yaml
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY darkmoon-scan.hpi /usr/share/jenkins/ref/plugins/darkmoon-scan.jpi
