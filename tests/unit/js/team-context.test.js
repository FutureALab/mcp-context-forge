import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { switchTeamContext } from "../../../mcpgateway/admin_ui/teamContext.js";
import { teamSelector } from "../../../mcpgateway/admin_ui/components/team-selector.js";

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("location", { href: "http://localhost/admin/?include_inactive=true#gateways", assign: vi.fn() });
  window.__teamSwitchingInProgress = false;
  delete window.updateTeamContext;
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

test("switches after creation without relying on an inline global function", () => {
  switchTeamContext("team-a");
  expect(window.location.assign).toHaveBeenCalledWith("http://localhost/admin/?include_inactive=true&team_id=team-a#gateways");
  switchTeamContext("team-a");
  expect(window.location.assign).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(2000);
  expect(window.__teamSwitchingInProgress).toBe(false);
});

test("All Teams removes scope and closes the menu", () => {
  window.location.href = "http://localhost/admin/?team_id=team-a#gateways";
  const selector = teamSelector();
  selector.open = true;
  selector.selectAllTeams();
  expect(selector.open).toBe(false);
  expect(window.location.assign).toHaveBeenCalledWith("http://localhost/admin/#gateways");
});

test("selecting the current team does not reload", () => {
  window.location.href = "http://localhost/admin/?team_id=team-a#gateways";
  switchTeamContext("team-a");
  expect(window.location.assign).not.toHaveBeenCalled();
});
