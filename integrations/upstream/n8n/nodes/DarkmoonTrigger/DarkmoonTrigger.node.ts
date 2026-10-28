import { eventProjection } from '../Darkmoon/EventProjection';
import { testDarkmoonCredential } from '../Darkmoon/CredentialTest';
import { createHmac, timingSafeEqual } from 'node:crypto';
import type {
	IDataObject,
	IHookFunctions,
	INodeExecutionData,
	INodeType,
	INodeTypeDescription,
	IPollFunctions,
	IWebhookFunctions,
	IWebhookResponseData,
	NodeConnectionType,
} from 'n8n-workflow';

import { authorize, dm, dmDelete, normalizeCampaignStatus } from '../Darkmoon/GenericFunctions';

/**
 * Darkmoon Trigger.
 *
 * Fires an n8n workflow on Darkmoon events (campaign.* / finding.* / pr.*).
 *
 * Two modes:
 *   - Poll (default, recommended): a polling trigger that reproduces the
 *     `streamEvents` taxonomy with a cloud-safe synthetic poll-and-diff. Each
 *     poll reads campaigns / findings / pull-requests, diffs them against a
 *     durable cursor kept in the workflow static data, and emits the resulting
 *     events. Works behind NAT and uses only n8n's own HTTP helper (no timers,
 *     no restricted globals).
 *   - Webhook: registers a Darkmoon Pro webhook that POSTs signed events to this
 *     node; the HMAC `X-Darkmoon-Signature` is verified.
 *
 * Events carry SAFE FIELDS ONLY (ids, severity, status, counts, timestamps).
 */

const EVENT_OPTIONS = [
	{ name: 'Campaign — Aborted', value: 'campaign.aborted' },
	{ name: 'Campaign — Completed', value: 'campaign.completed' },
	{ name: 'Campaign — Started', value: 'campaign.started' },
	{ name: 'Campaign — Stopped', value: 'campaign.stopped' },
	{ name: 'Finding — Confirmed', value: 'finding.confirmed' },
	{ name: 'Finding — Discovered', value: 'finding.discovered' },
	{ name: 'Finding — Exploited', value: 'finding.exploited' },
	{ name: 'Finding — Remediated', value: 'finding.remediated' },
	{
		name: 'Remediation — Updated (Local Proposal)',
		value: 'remediation.updated',
	},
	{ name: 'PR — Opened', value: 'pr.opened' },
	{ name: 'PR — Updated', value: 'pr.updated' },
];

const asArray = (v: unknown): IDataObject[] => (Array.isArray(v) ? (v as IDataObject[]) : []);

function acknowledge(
	ctx: IWebhookFunctions,
	status: number,
	message: string,
): IWebhookResponseData {
	ctx.getResponseObject().status(status).json({ message });
	return { noWebhookResponse: true };
}

export class DarkmoonTrigger implements INodeType {
	methods = {
		credentialTest: { darkmoonCredentialTest: testDarkmoonCredential },
	};
	description: INodeTypeDescription = {
		displayName: 'Darkmoon Trigger',
		name: 'darkmoonTrigger',
		icon: { light: 'file:darkmoon.svg', dark: 'file:darkmoon.svg' },
		group: ['trigger'],
		version: 1,
		subtitle: '={{$parameter["mode"]}}',
		description: 'Starts a workflow when Darkmoon emits campaign, finding or PR events',
		defaults: {
			name: 'Darkmoon Trigger',
		},
		polling: true,
		inputs: [],
		outputs: ['main'] as NodeConnectionType[],
		credentials: [
			{
				name: 'darkmoonApi',
				testedBy: 'darkmoonCredentialTest',
				required: true,
			},
		],
		webhooks: [
			{
				name: 'default',
				httpMethod: 'POST',
				responseMode: 'onReceived',
				path: 'darkmoon',
			},
		],
		properties: [
			{
				displayName: 'Mode',
				name: 'mode',
				type: 'options',
				default: 'poll',
				description: 'How this trigger receives events',
				options: [
					{
						name: 'Poll (Recommended)',
						value: 'poll',
						description:
							'Poll the Darkmoon API on a schedule and diff for new events. Works behind NAT.',
					},
					{
						name: 'Webhook',
						value: 'webhook',
						description: 'Register a Darkmoon Pro webhook that posts signed events to this node',
					},
				],
			},
			{
				displayName: 'Events',
				name: 'events',
				type: 'multiOptions',
				default: [],
				description: 'Event types to react to. Leave empty for all events.',
				options: EVENT_OPTIONS,
			},
		],
	};

	webhookMethods = {
		default: {
			async checkExists(this: IHookFunctions): Promise<boolean> {
				if ((this.getNodeParameter('mode', 'poll') as string) !== 'webhook') return true;
				const staticData = this.getWorkflowStaticData('node');
				const webhookId = staticData.webhookId as string | undefined;
				const credentials = await this.getCredentials('darkmoonApi');
				if (
					!webhookId ||
					staticData.webhookSecret ||
					typeof credentials.webhookSecret !== 'string' ||
					credentials.webhookSecret.length < 24
				)
					return false;
				const session = await authorize(this, (await this.getCredentials('darkmoonApi')) as never);
				const body = await dm(this, this.getNode(), session, 'GET', '/webhooks');
				return asArray(body.data).some((h) => String(h.id) === webhookId);
			},
			async create(this: IHookFunctions): Promise<boolean> {
				if ((this.getNodeParameter('mode', 'poll') as string) !== 'webhook') return true;
				const credentials = await this.getCredentials('darkmoonApi');
				const secret = credentials.webhookSecret;
				if (typeof secret !== 'string' || secret.length < 24)
					throw new Error(
						'Set a Webhook Signing Secret of at least 24 characters in the encrypted Darkmoon credential.',
					);
				const session = await authorize(this, (await this.getCredentials('darkmoonApi')) as never);
				const state = this.getWorkflowStaticData('node');
				if (state.webhookId) {
					await dmDelete(
						this,
						this.getNode(),
						session,
						`/webhooks/${encodeURIComponent(String(state.webhookId))}`,
					);
					delete state.webhookId;
					delete state.webhookSecret;
				}
				const url = this.getNodeWebhookUrl('default') as string;
				const events = this.getNodeParameter('events', []) as string[];
				const body = await dm(this, this.getNode(), session, 'POST', '/webhooks', {
					body: { url, events, secret, format: 'darkmoon' },
					okStatuses: [200, 201],
				});
				const reg = (body.data ?? body) as IDataObject;
				const staticData = this.getWorkflowStaticData('node');
				if (typeof reg.id !== 'string' || !reg.id)
					throw new Error('Webhook registration needs an identity.');
				staticData.webhookId = reg.id;
				// The secret remains only in n8n's encrypted credential.
				delete staticData.webhookSecret;
				return true;
			},
			async delete(this: IHookFunctions): Promise<boolean> {
				const staticData = this.getWorkflowStaticData('node');
				const webhookId = staticData.webhookId as string | undefined;
				if (!webhookId) return true;
				try {
					const session = await authorize(
						this,
						(await this.getCredentials('darkmoonApi')) as never,
					);
					await dmDelete(
						this,
						this.getNode(),
						session,
						`/webhooks/${encodeURIComponent(webhookId)}`,
					);
				} catch (error) {
					// Preserve the registration if cleanup fails so deactivation can be retried.
					throw new Error('Darkmoon webhook cleanup failed; registration is retained for retry.');
				}
				delete staticData.webhookId;
				delete staticData.webhookSecret;
				return true;
			},
		},
	};

	async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
		const req = this.getRequestObject();
		const staticData = this.getWorkflowStaticData('node');
		const credentials = await this.getCredentials('darkmoonApi');
		const secret =
			typeof credentials.webhookSecret === 'string' ? credentials.webhookSecret : undefined;
		const body = (req.body ?? {}) as IDataObject;

		if (secret) {
			const header = String(this.getHeaderData()['x-darkmoon-signature'] ?? '').replace(
				/^sha256=/,
				'',
			);
			const raw = (req as unknown as { rawBody?: Buffer }).rawBody;
			const payload = raw ? raw.toString('utf8') : JSON.stringify(body);
			const expected = createHmac('sha256', secret).update(payload).digest('hex');
			const ok =
				/^[a-f0-9]{64}$/i.test(header) &&
				timingSafeEqual(Buffer.from(header), Buffer.from(expected));
			if (!ok) {
				return acknowledge(this, 401, 'invalid signature');
			}
		}

		// Community receiver adaptation: require the replay-resistant v2
		// signature emitted by our backend, in addition to the legacy HMAC.
		const headers = this.getHeaderData();
		const stamp = String(headers['x-darkmoon-timestamp'] ?? '');
		const eventId = String(headers['x-darkmoon-event-id'] ?? '');
		const signatureV2 = String(headers['x-darkmoon-signature-v2'] ?? '').replace(/^sha256=/, '');
		const timestamp = Number(stamp);
		if (
			!secret ||
			!Number.isFinite(timestamp) ||
			Math.abs(Date.now() / 1000 - timestamp) > 300 ||
			!/^[A-Za-z0-9_-]{1,200}$/.test(eventId)
		) {
			return acknowledge(this, 401, 'invalid event timestamp or identity');
		}
		const rawBody = (req as unknown as { rawBody?: Buffer }).rawBody;
		const payloadV2 = rawBody ? rawBody.toString('utf8') : JSON.stringify(body);
		const expectedV2 = createHmac('sha256', secret)
			.update(`${stamp}.${eventId}.${payloadV2}`)
			.digest('hex');
		if (
			!/^[a-f0-9]{64}$/i.test(signatureV2) ||
			!timingSafeEqual(Buffer.from(signatureV2), Buffer.from(expectedV2))
		) {
			return acknowledge(this, 401, 'invalid v2 signature');
		}
		if (body.id !== undefined && body.id !== eventId)
			return acknowledge(this, 401, 'event identity mismatch');
		let projected: IDataObject;
		try {
			projected = eventProjection(String(body.event ?? ''), (body.data ?? {}) as IDataObject, {
				...body,
				id: eventId,
			});
		} catch {
			return acknowledge(this, 400, 'invalid event');
		}
		const current = Date.now() / 1000;
		const seenEvents = new Map(
			Object.entries((staticData.communitySeenEvents ?? {}) as Record<string, number>).filter(
				([, received]) => typeof received === 'number' && received >= current - 86400,
			),
		);
		if (seenEvents.has(eventId)) return acknowledge(this, 200, 'duplicate ignored');
		seenEvents.set(eventId, current);
		const ordered = [...seenEvents].sort((a, b) => a[1] - b[1]);
		staticData.communitySeenEvents = Object.fromEntries(ordered.slice(-5000));
		const selected = this.getNodeParameter('events', []) as string[];
		if (selected.length && !selected.includes(String(body.event)))
			return acknowledge(this, 200, 'event ignored');
		return { workflowData: [[{ json: projected }]] };
	}

	async poll(this: IPollFunctions): Promise<INodeExecutionData[][] | null> {
		if ((this.getNodeParameter('mode', 'poll') as string) !== 'poll') return null;

		const node = this.getNode();
		const session = await authorize(this, (await this.getCredentials('darkmoonApi')) as never);
		const selected = this.getNodeParameter('events', []) as string[];
		const staticData = this.getWorkflowStaticData('node');
		const firstRun =
			!staticData.primed ||
			staticData.communityCursorVersion !== 2 ||
			staticData.communityCursorSource !== session.apiBase;
		const previous = (firstRun ? {} : (staticData.seen ?? {})) as Record<
			string,
			Record<string, string>
		>;
		const seen = {
			f: Object.assign(Object.create(null), previous.f),
			c: Object.assign(Object.create(null), previous.c),
			p: Object.assign(Object.create(null), previous.p),
		} as {
			f: Record<string, string>;
			c: Record<string, string>;
			p: Record<string, string>;
		};
		const isManual = this.getMode() === 'manual';
		// Fetch the entire input set before changing durable state. Failures retry all transitions.
		const findingBody = await dm(this, node, session, 'GET', '/vulnerabilities');
		const campaignBody = await dm(this, node, session, 'GET', '/campaigns');
		const prBody = await dm(this, node, session, 'GET', '/pull-requests', {
			okStatuses: [200, 404],
		});
		if (!Array.isArray(findingBody.data) || !Array.isArray(campaignBody.data))
			throw new Error('Darkmoon poll response needs a data array.');

		const events: IDataObject[] = [];
		const want = (e: string) => !selected.length || selected.includes(e);
		const emit = (event: string, data: IDataObject) => {
			if (want(event)) events.push(eventProjection(event, data, { ts: new Date().toISOString() }));
		};

		// Findings → finding.discovered / .confirmed / .exploited / .remediated
		const findings = asArray(findingBody.data);
		for (const f of findings) {
			const id = String(f.id);
			const status = String(f.status ?? 'unconfirmed').toLowerCase();
			const data: IDataObject = {
				finding_id: id,
				severity: f.severity ?? null,
				status,
				category: f.category ?? null,
				endpoint: f.endpoint ?? null,
				campaign_id: f.campaign_id ?? null,
			};
			const key = JSON.stringify([String(f.campaign_id ?? ''), id]);
			const prev = seen.f[key];
			if (prev === undefined) emit('finding.discovered', data);
			if (prev !== status) {
				if (status === 'exploited') emit('finding.exploited', data);
				else if (status === 'confirmed') emit('finding.confirmed', data);
				else if (status === 'remediated') emit('finding.remediated', data);
			}
			seen.f[key] = status;
		}

		// Campaigns → campaign.started / .completed / .stopped / .aborted
		const campaigns = asArray(campaignBody.data);
		for (const c of campaigns) {
			const id = String(c.id);
			const rawStatus = String(c.status ?? '')
				.trim()
				.toLowerCase();
			const status = ['aborted', 'interrupted', 'timed_out'].includes(rawStatus)
				? 'failed'
				: normalizeCampaignStatus(rawStatus);
			const prev = seen.c[id];
			if (prev !== status) {
				const map: Record<string, string> = {
					completed: 'campaign.completed',
					stopped: 'campaign.stopped',
					failed: 'campaign.aborted',
					running: 'campaign.started',
				};
				const ev = map[status];
				if (ev)
					emit(ev, {
						campaign_id: id,
						status,
						overall_risk: c.overall_risk ?? null,
						stats: c.stats ?? {},
					});
			}
			seen.c[id] = status;
		}

		// Pull-requests → pr.opened / pr.updated (best effort; 404 when unavailable)
		for (const p of asArray(prBody.data)) {
			const id = String(p.id);
			const state = String(p.state ?? 'proposed').toLowerCase();
			const data: IDataObject = {
				pr_id: id,
				state,
				campaign_id: p.campaign_id ?? null,
				provider: p.provider ?? null,
			};
			const prev = seen.p[id];
			const published =
				p.published === true ||
				(p.published !== false &&
					typeof p.provider === 'string' &&
					typeof p.number === 'number' &&
					p.number > 0);
			const disposition = JSON.stringify([published, state]);
			if (published && (prev === undefined || JSON.parse(prev)[0] !== true))
				emit('pr.opened', data);
			else if (prev !== disposition) emit(published ? 'pr.updated' : 'remediation.updated', data);
			seen.p[id] = disposition;
		}

		staticData.seen = seen;
		staticData.communityCursorVersion = 2;
		staticData.communityCursorSource = session.apiBase;
		staticData.primed = true;

		// First activation only primes the cursor (no historical replay storm),
		// unless the user is manually testing and wants to see a sample.
		if (firstRun && !isManual) return null;
		if (!events.length) return null;
		return [events.map((e) => ({ json: e }))];
	}
}
