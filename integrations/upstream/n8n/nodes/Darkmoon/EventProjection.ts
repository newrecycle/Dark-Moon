import type { IDataObject } from 'n8n-workflow';

/** Event metadata is allowlisted independently of API/producer redaction. */
export function eventProjection(
	event: string,
	raw: IDataObject,
	envelope: IDataObject = {},
): IDataObject {
	if (!/^(campaign|finding|pr|retest|remediation)\.[a-z_]+$/.test(event))
		throw new Error('Invalid Darkmoon event type.');
	const data: IDataObject = {};
	for (const key of [
		'campaign_id',
		'run_id',
		'finding_id',
		'severity',
		'status',
		'category',
		'mitre_attack_id',
		'iso27001_control',
		'retest_id',
		'pr_id',
		'state',
		'provider',
		'overall_risk',
	]) {
		if (typeof raw[key] === 'string') data[key] = raw[key];
	}
	const counts = raw.stats;
	if (counts && typeof counts === 'object' && !Array.isArray(counts)) {
		const safe: IDataObject = {};
		for (const key of [
			'total_findings',
			'critical',
			'high',
			'medium',
			'low',
			'info',
			'confirmed',
			'exploited',
			'unconfirmed',
		]) {
			const value = (counts as IDataObject)[key];
			if (typeof value === 'number' && Number.isFinite(value) && value >= 0) safe[key] = value;
		}
		data.stats = safe;
	}
	const result: IDataObject = { event, data };
	for (const key of ['id', 'timestamp', 'ts', 'contract_version'])
		if (typeof envelope[key] === 'string') result[key] = envelope[key];
	if (typeof envelope.seq === 'number' && Number.isSafeInteger(envelope.seq) && envelope.seq >= 0)
		result.seq = envelope.seq;
	return result;
}
