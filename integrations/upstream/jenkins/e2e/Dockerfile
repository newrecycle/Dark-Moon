FROM jenkins/jenkins:lts-jdk21
# A disposable controller. Node is deliberately not installed here: it must
# be available on the separate agent that receives the HPI resource.
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
ENV CASC_JENKINS_CONFIG=/var/jenkins_home/casc.yaml
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY .native/darkmoon-scan.hpi /usr/share/jenkins/ref/plugins/darkmoon-scan.jpi
COPY casc.yaml /usr/share/jenkins/ref/casc.yaml
COPY init-agent.groovy /usr/share/jenkins/ref/init.groovy.d/init-agent.groovy
