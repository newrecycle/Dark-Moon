#!/usr/bin/env python3
"""Create a small owned synthetic cohort through normal application producers.

Run inside a disposable configured runtime with its normal module paths. No
assessment/model is executed. Keep the returned IDs with private captures.
"""
import json
import secrets


def create_cohort():
    from api import live_push
    prefix = 'capture_' + secrets.token_hex(8)
    rows = []
    for index in range(3):
        row = live_push.init_live_campaign(prefix + '_' + str(index), prefix + '.owned.invalid',
                                          '192.0.2.10', project_name='Synthetic capture cohort')
        for n in range(index + 1):
            live_push.push_finding(row['campaign_id'], {'id': prefix + '_finding_' + str(n),
                'title': 'Synthetic producer fixture', 'severity': 'low', 'status': 'confirmed',
                'category': 'fixture', 'description': 'Controlled producer observation, not an assessment.'})
        live_push.finalize_campaign(row['campaign_id'], executive_summary='Synthetic capture fixture; no scan executed.')
        rows.append(row)
    return {'fixture_kind': 'synthetic_normal_producer', 'assessment_executed': False,
            'namespace': prefix, 'target_id': rows[-1]['target_id'],
            'campaign_ids': [r['campaign_id'] for r in rows]}


if __name__ == '__main__':
    print(json.dumps(create_cohort()))
