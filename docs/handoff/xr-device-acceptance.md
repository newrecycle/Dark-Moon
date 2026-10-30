# XR acceptance

Automated lifecycle check (no headset required): from the repository root run
`node tests/community/xr_lifecycle.cjs`. This executes the production startVR
function against a controlled device interface. It checks pre-aborted views,
permission requests that finish after navigation, session termination, absence
of post-end frame scheduling, and graphics-resource cleanup on shader failure.
The browser workflow separately checks policy-denied XR and ordinary graph
navigation. These checks do not establish physical rendering or comfort.

For physical acceptance, use an operator-owned WebXR-capable headset/browser
and an HTTPS deployment of this checkout. Record commit, headset, OS, browser,
GPU, and result for each step. Use an owned fixture assessment containing linked
infrastructure nodes; authenticate with an account allowed to read it.

1. Open Attack surface, select the fixture, select nodes and inspect their
   metadata. Confirm the ordinary graph works before entering immersive mode.
2. Select Enter VR. Deny permission once: the ordinary graph must remain usable
   and the error must not expose protected evidence. Reload and grant permission.
3. Confirm both eyes render the same fixture topology, head movement changes the
   view correctly, and recorded links join their nodes. Check against the ordinary
   graph; do not infer exploitation merely from a displayed connection.
4. Exit with the device/browser control. Enter again, then change assessment and
   navigate away. Confirm the session ends each time and normal navigation works.
5. Navigate away while permission is pending, then accept it. No stale immersive
   view may remain. Sign out during a session; no protected scene may remain.
6. Capture browser errors and observed failures, excluding tokens/raw evidence.
   Treat unavailable capabilities as unavailable, never as a passed headset test.

Physical acceptance is unavailable in this environment. Exact commercial
visuals and independently demonstrated exploitation are separate evidence gaps.


Initialization cancellation is also checked during makeXRCompatible and
requestReferenceSpace, including an external end event while setup is pending.
No graphics objects or frame loop may be created after cleanup. Abort releases
resources even if session.end rejects; shader link failure is surfaced and
cleaned up. These are production-code lifecycle checks, not a device emulator.
