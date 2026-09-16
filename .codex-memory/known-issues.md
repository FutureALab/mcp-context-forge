# Known Issues

## Windows JavaScript MIME mapping

Windows MIME configuration classified `.js` as `text/plain` on this machine.
Browsers rejected the Admin UI module, leaving overview and A2A panels loading.
`mcpgateway/main.py` now registers `.js` as `text/javascript` before mounting static files.
Restart existing gateway processes after updating this code.

Run `python -m unittest tests.live_gateway.test_static_javascript` against a running gateway.
Set `GATEWAY_URL` when testing a port other than 4444.

### Resource service reinitialization

The startup override alone was insufficient. `ResourceService.__init__` called `mimetypes.init()` unconditionally.
New resource services reloaded Windows mappings and changed JavaScript back to `text/plain` after MCP registration.
Resource services now initialize MIME mappings only when the registry is uninitialized.
Regression tests cover repeated construction, custom mappings, and initial registry setup.

## 2026-09-16 Team-scoped token page rendering
- Resolved: admin.html and tokens_partial.html assigned dict.update() to `_`, masking the Jinja translation callable with None.
- Team selection and token search could fail with HTTP 500 during pagination rendering.
- Use query_params_updated for ignored update results; preserve `_` for translations.
- Live member-session checks cover dashboard, token search, HTMX list, and pagination controls. Browser confirms team-scoped form and loaded list.
- Restart existing gateway processes to clear cached templates. Temporary validation server was stopped.
