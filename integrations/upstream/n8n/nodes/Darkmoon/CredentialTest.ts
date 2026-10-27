import type { ICredentialTestFunction } from 'n8n-workflow';

// Public system/info proves reachability, but cannot validate a login.
// n8n supplies this request helper to custom credential test functions.
export const testDarkmoonCredential: ICredentialTestFunction = async function (credential) {
	try {
		const data = credential.data || {};
		const base = String(data.baseUrl || '').trim().replace(/\/+$/, '');
		const api = /\/api\/v1$/.test(base) ? base : `${base}/api/v1`;
		const parsed = new URL(api);
		if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash)
			return { status: 'Error', message: 'Choose a DarkMoon base URL without embedded credentials, query or fragment.' };
		let token = String(data.token || '').trim();
		if (data.authMethod === 'password' || (!data.authMethod && !token)) {
			const login = await this.helpers.request({ method: 'POST', uri: `${api}/auth/login`, body: { username: String(data.username || ''), password: String(data.password || '') }, json: true, resolveWithFullResponse: true, simple: false, followRedirect: false, followAllRedirects: false });
			token = login.statusCode === 200 ? String(login.body?.token || '') : '';
		}
		if (!token) return { status: 'Error', message: 'DarkMoon login failed. Check the credentials.' };
		const result = await this.helpers.request({ method: 'GET', uri: `${api}/campaigns?limit=1`, headers: { Authorization: `Bearer ${token}` }, json: true, resolveWithFullResponse: true, simple: false, followRedirect: false, followAllRedirects: false });
		return result.statusCode === 200 && Array.isArray(result.body?.data)
			? { status: 'OK', message: 'DarkMoon accepted the credentials on an authenticated API endpoint.' }
			: { status: 'Error', message: 'DarkMoon rejected the credentials or denied campaign access.' };
	} catch {
		return { status: 'Error', message: 'DarkMoon credential check failed. Verify the URL, TLS connection and credentials.' };
	}
};
