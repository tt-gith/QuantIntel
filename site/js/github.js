// Yönetim panelinin GitHub bağlantısı. Site durağan olduğu için panel bir şeyi doğrudan değiştiremez;
// şifreli komutu günlük iş akışına girdi olarak yollar (workflow_dispatch) ve çalışmanın durumunu izler.
// Anahtar (ADMIN_TOKEN) yalnızca bu deponun "Actions" iznini taşır ve admin.bin içinde şifreli durur.
const API = "https://api.github.com";

export class GitHubError extends Error {
  constructor(status, message) {
    super(message || `GitHub ${status}`);
    this.status = status;
  }
}

async function call(info, path, init = {}) {
  const res = await fetch(`${API}/repos/${info.repo}/actions/workflows/${info.workflow}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      Authorization: `Bearer ${info.token}`,
      Accept: "application/vnd.github+json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!res.ok) {
    let message = "";
    try { message = (await res.json()).message ?? ""; } catch { /* gövde yok */ }
    throw new GitHubError(res.status, message);
  }
  return res.status === 204 ? null : res.json().catch(() => null);
}

const runs = async (info) => (await call(info, "/runs?event=workflow_dispatch&per_page=5"))?.workflow_runs ?? [];

// Komut gönderilmeden önceki en yeni çalışmanın kimliği (yenisini ondan ayırmak için).
export async function latestRunId(info) {
  return (await runs(info))[0]?.id ?? 0;
}

// Şifreli komutu iş akışına yollar.
export function dispatch(info, payload) {
  return call(info, "/dispatches", { method: "POST", body: JSON.stringify({ ref: info.ref, inputs: { komut: payload } }) });
}

// `after` kimliğinden sonra başlamış çalışma: { status, conclusion, url } ya da null (henüz görünmüyor).
export async function findRun(info, after) {
  const fresh = (await runs(info)).filter((r) => r.id > after);
  const run = fresh[fresh.length - 1];                 // komuttan sonraki ilk çalışma
  return run ? { status: run.status, conclusion: run.conclusion, url: run.html_url } : null;
}

export const actionsUrl = (info) => `https://github.com/${info.repo}/actions/workflows/${info.workflow}`;
