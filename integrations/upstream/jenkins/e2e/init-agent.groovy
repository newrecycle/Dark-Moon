import hudson.model.Node
import hudson.slaves.DumbSlave
import hudson.slaves.JNLPLauncher
import hudson.slaves.RetentionStrategy
import jenkins.model.Jenkins
def server = Jenkins.get()
if (server.getNode('dm-agent') == null) {
    server.addNode(new DumbSlave(
        'dm-agent', 'Disposable native test agent', '/home/jenkins/agent workspace',
        '1', Node.Mode.NORMAL, 'dm-agent',
        new JNLPLauncher(), new RetentionStrategy.Always(), Collections.emptyList()
    ))
}
