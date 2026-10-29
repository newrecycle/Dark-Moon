import json
import unittest
from server_acceptance import pipeline_config
from verify_ingestion import artifact_report
import yaml

class ServerAcceptance(unittest.TestCase):
    def test_server_config_uses_actual_local_component_and_typed_allowed_failures(self):
        for case in ('passing', 'empty', 'blocking', 'nonblocking', 'read_error'):
            with self.subTest(case=case):
                config = yaml.safe_load(pipeline_config(case))
                item = config['include'][0]
                self.assertEqual(item['local'], '/templates/scan/template.yml')
                self.assertEqual(item['inputs']['allow_failure_exit_codes'], [2] if case in ('nonblocking', 'read_error') else [250])
                self.assertNotIn('script', config)
    def test_artifact_response_must_be_actual_darkmoon_sast_json(self):
        valid = {'scan': {'type':'sast','status':'success','scanner':{'id':'darkmoon'}},'vulnerabilities':[]}
        self.assertEqual(artifact_report(json.dumps(valid)),valid)
        for invalid in (b'PK\x03\x04zip', b'[]', b'{}', json.dumps(valid | {'scan': {'scanner':{'id':'other'}}})):
            with self.subTest(invalid=invalid):
                with self.assertRaises((ValueError,TypeError)):
                    artifact_report(invalid)
if __name__ == '__main__': unittest.main()
