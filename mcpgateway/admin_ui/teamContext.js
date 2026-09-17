/** Navigate once while preserving the active tab and unrelated filters. */
export function switchTeamContext(teamId) {
  if (window.__teamSwitchingInProgress) return;
  const url = new URL(window.location.href);
  if (teamId) url.searchParams.set("team_id", teamId);
  else url.searchParams.delete("team_id");
  if (url.href === window.location.href) return;
  window.__teamSwitchingInProgress = true;
  try {
    window.location.assign(url.href);
  } finally {
    setTimeout(() => { window.__teamSwitchingInProgress = false; }, 2000);
  }
}
