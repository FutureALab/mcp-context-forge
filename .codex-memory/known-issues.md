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
