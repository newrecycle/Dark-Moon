import * as assert from 'assert';
import { exactCampaignIdentity } from '../../src/darkmoon/realAdapter';

describe('Native consumer run/campaign correlation', () => {
  it('retains the exact campaign identity distinct from run identity', () => {
    assert.equal(exactCampaignIdentity({campaignId:'campaign_A',runId:'job_B'}),
      'campaign_A');
    assert.equal(exactCampaignIdentity({campaignId:null,runId:'job_B',
      correlation:{campaignId:'campaign_C',runId:'job_B'}}), 'campaign_C');
  });
  it('rejects launches that return only a run id or malformed campaign id', () => {
    for (const response of [
      {campaignId:null,runId:'job_only'},
      {campaignId:'',runId:'job_only'},
      {campaignId:'../../etc/passwd',runId:'job_only'},
      {campaignId:'TOKEN: PRIVATE',runId:'job_only'},
      {runId:'job_only'},
    ]) {
      assert.throws(() => exactCampaignIdentity(response),
        /Campaign identity was not returned/);
    }
  });
});
